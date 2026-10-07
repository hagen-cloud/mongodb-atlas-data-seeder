"""Entry point: ``python -m seeder``.

Per pod this process:
  1. loads config + shard info from env,
  2. enforces guardrails,
  3. (shard 0 only) creates target collections/indexes,
  4. spawns one monitor thread and ``procs`` worker processes,
  5. waits for the stop signal and emits a final report.

``--dry-run N`` generates N documents from the first template without any
MongoDB connection — useful to validate templates and measure generation rate.
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
import random
import sys
import threading
import time

from faker import Faker

from . import config, generator, guardrails, monitor, sizing, writer

log = logging.getLogger("seeder")


def setup_logging() -> None:
    """Configure structured INFO-level logging for the process."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def ensure_indexes(cfg: config.Config) -> None:
    """Create the configured indexes on every target collection (shard 0 only)."""
    client = writer.build_client(cfg)
    try:
        for database in cfg.databases:
            collection = client[database.name][database.collection]
            for index in database.indexes:
                keys = list(index["keys"].items())
                options = {k: v for k, v in index.items() if k != "keys"}
                collection.create_index(keys, **options)
                log.info("ensured index on %s.%s keys=%s", database.name, database.collection, keys)
    finally:
        client.close()


def dry_run(cfg: config.Config, count: int) -> None:
    """Generate ``count`` docs from the first template without any DB connection."""
    rng = random.Random(42)
    faker = Faker()
    faker.seed_instance(42)
    database = cfg.databases[0]

    sample = None
    start = time.time()
    for index in range(count):
        doc = generator.generate_document(database.schema, rng, faker)
        if index == 0:
            sample = doc
    elapsed = max(time.time() - start, 1e-9)

    print(json.dumps(sample, default=str, indent=2))
    print(
        f"\ngenerated {count} docs for {database.name}.{database.collection} "
        f"in {elapsed:.2f}s ({count / elapsed:,.0f} docs/s)"
    )


def main() -> None:
    """CLI entry point: parse args, then dry-run or start the seeding run."""
    parser = argparse.ArgumentParser(prog="seeder", description="MongoDB Atlas mock data seeder")
    parser.add_argument("--config", default=None, help="Path to config.yaml (defaults to $SEEDER_CONFIG)")
    parser.add_argument("--dry-run", type=int, default=0, metavar="N",
                        help="Generate N docs from the first template and exit (no DB connection)")
    args = parser.parse_args()

    setup_logging()
    cfg = config.load_config(args.config)

    if args.dry_run:
        dry_run(cfg, args.dry_run)
        return

    try:
        guardrails.check(cfg)
    except guardrails.GuardrailError as exc:
        log.error("guardrail failed: %s", exc)
        sys.exit(2)

    log.info(
        "starting shard=%d/%d env=%s target=%s metric=%s procs=%d threads=%d batch=%d",
        cfg.shard_index, cfg.shard_total, cfg.env, cfg.target.size, cfg.target.metric,
        cfg.write.procs, cfg.write.threads, cfg.write.batch_size,
    )

    if cfg.create_indexes and cfg.shard_index == 0:
        ensure_indexes(cfg)

    stop_event = mp.Event()
    monitor_thread = threading.Thread(
        target=monitor.run,
        args=(cfg, stop_event, lambda: writer.build_client(cfg)),
        name="monitor",
        daemon=True,
    )
    monitor_thread.start()

    processes = [
        mp.Process(target=writer.run_worker, args=(worker_id, cfg, stop_event), name=f"worker-{worker_id}")
        for worker_id in range(cfg.write.procs)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join()

    stop_event.set()

    client = writer.build_client(cfg)
    try:
        final = sizing.measure(client, [database.name for database in cfg.databases], cfg.target.metric)
    finally:
        client.close()
    log.info("shard=%d complete final_%s=%s", cfg.shard_index, cfg.target.metric, sizing.format_size(final))


if __name__ == "__main__":
    main()
