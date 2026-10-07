"""Worker process and thread loops that generate and insert documents.

Concurrency model (per pod):
  * ``cfg.write.procs`` worker processes  -> real CPU parallelism for document
    generation (bypasses the Python GIL),
  * ``cfg.write.threads`` threads per process -> I/O concurrency on
    ``insert_many`` (PyMongo releases the GIL while waiting on the socket).

A ``MongoClient`` is not fork-safe, so each worker process creates its own.
"""

from __future__ import annotations

import logging
import os
import random
import threading

from faker import Faker
from pymongo import MongoClient

from . import generator, partition
from .config import Config

log = logging.getLogger("seeder.writer")


def build_client(cfg: Config) -> MongoClient:
    """Create a MongoClient from the connection settings (one per process)."""
    uri = os.environ[cfg.connection.uri_env]
    return MongoClient(
        uri,
        maxPoolSize=cfg.write.max_pool_size or (cfg.write.threads + 1),
        compressors=cfg.write.compressors,
        w=cfg.write.write_concern_w,
        journal=cfg.write.journal,
        retryWrites=True,
        serverSelectionTimeoutMS=cfg.connection.server_selection_timeout_ms,
    )


def _seed_int(shard_index: int, worker_id: int, thread_id: int) -> int:
    """Deterministic per-thread seed (no cross-pod coordination needed)."""
    return ((shard_index * 1_000_003) + worker_id) * 1_000_003 + thread_id


def _thread_loop(client: MongoClient, cfg: Config, stop_event, seed: int) -> None:
    rng = random.Random(seed)
    faker = Faker()
    faker.seed_instance(seed)

    inserted = 0
    while not stop_event.is_set():
        database = partition.pick_weighted(cfg.databases, rng)
        docs = [generator.generate_document(database.schema, rng, faker) for _ in range(cfg.write.batch_size)]
        try:
            client[database.name][database.collection].insert_many(docs, ordered=cfg.write.ordered)
            inserted += len(docs)
        except Exception as exc:  # noqa: BLE001  # keep the run alive through transient cluster pressure
            # Driver exceptions can include connection details or document contents.
            log.warning("insert failed (%s); retrying after backoff", type(exc).__name__)
            stop_event.wait(1.0)

    log.info("thread seed=%s finished inserted=%d", seed, inserted)


def run_worker(worker_id: int, cfg: Config, stop_event) -> None:
    """Process entry point: start ``cfg.write.threads`` insert loops and join them."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    client = build_client(cfg)
    threads: list[threading.Thread] = []
    for thread_id in range(cfg.write.threads):
        seed = _seed_int(cfg.shard_index, worker_id, thread_id)
        thread = threading.Thread(
            target=_thread_loop,
            args=(client, cfg, stop_event, seed),
            name=f"shard{cfg.shard_index}-w{worker_id}-t{thread_id}",
        )
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()
    client.close()
