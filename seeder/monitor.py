"""Coordinator-free stop monitor.

Every pod runs one monitor thread. Because all pods observe the *same* cluster,
each one independently measures the total size and signals its local workers to
stop once the (overshoot-adjusted) target is reached. No leader, no shared
coordination state — pods only share the cluster they are filling.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from pymongo import MongoClient

from . import sizing
from .config import Config

log = logging.getLogger("seeder.monitor")


def run(cfg: Config, stop_event, client_factory: Callable[[], MongoClient]) -> None:
    """Poll the cluster size until the target is reached, then signal stop."""
    client = client_factory()
    target = int(sizing.parse_size(cfg.target.size) * cfg.target.overshoot)
    db_names = [database.name for database in cfg.databases]

    last_measured = 0
    last_time = time.time()
    try:
        while not stop_event.is_set():
            measured = sizing.measure(client, db_names, cfg.target.metric)
            now = time.time()
            elapsed = max(now - last_time, 1e-6)
            rate = (measured - last_measured) / elapsed
            pct = (100.0 * measured / target) if target else 0.0

            log.info(
                "progress metric=%s measured=%s target=%s pct=%.2f%% rate=%s/s",
                cfg.target.metric,
                sizing.format_size(measured),
                sizing.format_size(target),
                pct,
                sizing.format_size(int(max(rate, 0))),
            )

            if measured >= target:
                log.info("target reached (%s >= %s); signaling stop",
                         sizing.format_size(measured), sizing.format_size(target))
                stop_event.set()
                break

            last_measured, last_time = measured, now
            stop_event.wait(cfg.target.check_interval_s)
    finally:
        client.close()
