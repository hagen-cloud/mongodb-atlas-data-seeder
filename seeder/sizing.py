"""Size parsing/formatting and live cluster size measurement via ``dbStats``.

The stop condition is measured (not estimated) because WiredTiger compression
makes a byte target impossible to derive from a document count: random data
barely compresses while realistic data compresses a lot. We therefore poll
``dbStats`` and keep going until the real size reaches the target.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from pymongo import MongoClient

_UNITS = {
    "B": 1,
    "KB": 1024,
    "MB": 1024 ** 2,
    "GB": 1024 ** 3,
    "TB": 1024 ** 4,
    "PB": 1024 ** 5,
}

_SIZE_RE = re.compile(r"^\s*([0-9.]+)\s*([KMGTP]?B)\s*$")


def parse_size(value: str | float) -> int:
    """Parse a human size like ``"4TB"`` / ``"500MB"`` into a byte count."""
    if isinstance(value, (int, float)):
        return int(value)
    match = _SIZE_RE.match(str(value).upper())
    if not match:
        raise ValueError(f"Invalid size: {value!r}")
    return int(float(match.group(1)) * _UNITS[match.group(2)])


def format_size(num_bytes: int) -> str:
    """Format a byte count into a compact human-readable string."""
    for unit in ("PB", "TB", "GB", "MB", "KB"):
        if num_bytes >= _UNITS[unit]:
            return f"{num_bytes / _UNITS[unit]:.2f}{unit}"
    return f"{int(num_bytes)}B"


def measure(client: MongoClient, db_names: Sequence[str], metric: str) -> int:
    """Return the current size (in bytes) of the target databases for ``metric``.

    ``fsUsedSize`` is node-level (the whole disk), so it is read once. The other
    metrics are per-database and summed across the unique target databases.
    """

    unique_names = list(dict.fromkeys(db_names))

    if metric == "fsUsedSize":
        stats = client[unique_names[0]].command("dbStats")
        return int(stats.get("fsUsedSize", 0))

    total = 0
    for name in unique_names:
        stats = client[name].command("dbStats")
        if metric == "totalSize":
            total += stats.get("storageSize", 0) + stats.get("indexSize", 0)
        else:
            total += stats.get(metric, 0)
    return int(total)
