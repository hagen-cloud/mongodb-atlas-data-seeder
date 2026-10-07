"""Weighted random selection of a target database/collection.

Each worker uses its own seeded RNG (derived from the shard index, the worker
process id and the thread id), so the document distribution across databases is
weighted in expectation and reproducible for seeded random choices, with no shared state between pods.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from .config import DatabaseCfg


def pick_weighted(databases: Sequence[DatabaseCfg], rng: random.Random) -> DatabaseCfg:
    """Pick one database at random, weighted by each entry's ``weight``."""
    total = sum(database.weight for database in databases)
    threshold = rng.uniform(0.0, total)
    cumulative = 0.0
    for database in databases:
        cumulative += database.weight
        if threshold <= cumulative:
            return database
    return databases[-1]
