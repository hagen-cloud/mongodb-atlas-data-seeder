"""Configuration loading for the seeder.

Configuration comes from two places:
  * a YAML file (path from --config or the SEEDER_CONFIG env var), and
  * environment variables injected by the Kubernetes (Indexed) Job, namely
    ``JOB_COMPLETION_INDEX`` (the shard index) and ``SEEDER_SHARD_TOTAL``.

JSON field schemas live in separate template files referenced by each database
entry so the data model is decoupled from the run configuration.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class TargetCfg:
    """Stop condition for the run."""

    size: str  # e.g. "4TB", "500GB"
    metric: str = "storageSize"  # storageSize | dataSize | totalSize | fsUsedSize
    overshoot: float = 0.99  # stop at this fraction of the target to absorb in-flight batches
    check_interval_s: int = 30


@dataclass
class WriteCfg:  # pylint: disable=too-many-instance-attributes
    """Write/concurrency tuning."""

    procs: int = 2  # worker processes per pod (real CPU parallelism, bypasses the GIL)
    threads: int = 4  # threads per process (I/O concurrency on bulk_write)
    batch_size: int = 5000
    ordered: bool = False
    write_concern_w: int = 1
    journal: bool = False
    compressors: str = "zstd"
    max_pool_size: int | None = None  # defaults to threads + 1 when None


@dataclass
class ConnectionCfg:
    """MongoDB connection settings."""

    uri_env: str = "MONGODB_URI"
    server_selection_timeout_ms: int = 30000


@dataclass
class SafetyCfg:
    """Guardrails to avoid running against the wrong cluster."""

    require_env: str = "pre"  # refuse to run unless Config.env matches (empty disables)
    prod_host_blocklist: list[str] = field(default_factory=lambda: ["prod"])


@dataclass
class DatabaseCfg:
    """A target database/collection and the document schema to fill it with."""

    name: str
    collection: str
    weight: float
    template: str
    schema: dict[str, Any] = field(default_factory=dict)
    indexes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Config:  # pylint: disable=too-many-instance-attributes
    """Fully resolved run configuration."""

    env: str
    target: TargetCfg
    write: WriteCfg
    connection: ConnectionCfg
    safety: SafetyCfg
    databases: list[DatabaseCfg]
    templates_dir: str
    create_indexes: bool = True
    shard_index: int = 0
    shard_total: int = 1


def _shard_index() -> int:
    # Kubernetes Indexed Jobs expose JOB_COMPLETION_INDEX; SEEDER_SHARD_INDEX is a manual fallback.
    raw = os.environ.get("JOB_COMPLETION_INDEX", os.environ.get("SEEDER_SHARD_INDEX", "0"))
    return int(raw)


def load_config(path: str | None = None) -> Config:
    """Load and resolve the YAML config plus the per-shard env variables."""
    path = path or os.environ.get("SEEDER_CONFIG", "config/config.yaml")
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    templates_dir = (
        os.environ.get("SEEDER_TEMPLATES_DIR")
        or raw.get("templates_dir")
        or os.path.join(os.path.dirname(os.path.abspath(path)), "templates")
    )

    databases: list[DatabaseCfg] = []
    for entry in raw["databases"]:
        template_path = os.path.join(templates_dir, entry["template"])
        with open(template_path, encoding="utf-8") as tpl_handle:
            template = json.load(tpl_handle)
        databases.append(
            DatabaseCfg(
                name=entry["name"],
                collection=entry["collection"],
                weight=float(entry.get("weight", 1)),
                template=entry["template"],
                schema=template["schema"],
                indexes=template.get("indexes", entry.get("indexes", [])),
            )
        )

    return Config(
        env=str(raw.get("env", "pre")),
        target=TargetCfg(**raw["target"]),
        write=WriteCfg(**raw.get("write", {})),
        connection=ConnectionCfg(**raw.get("connection", {})),
        safety=SafetyCfg(**raw.get("safety", {})),
        databases=databases,
        templates_dir=templates_dir,
        create_indexes=bool(raw.get("create_indexes", True)),
        shard_index=_shard_index(),
        shard_total=int(os.environ.get("SEEDER_SHARD_TOTAL", "1")),
    )
