# mongodb-atlas-data-seeder

Hagen Cloud Python tooling for synthetic MongoDB Atlas load and volume tests in approved non-production environments. Generate documents from JSON templates, distribute writes across processes and threads, and stop when the configured database-size metric reaches a target.

Run with local Python, Docker Compose, or an Indexed Job on a suitable Kubernetes cluster. No specific cloud, container registry, secret manager, or automation controller is required.

## Behavior

- Keep the existing `seeder` package and `python -m seeder` / `seeder` entry points.
- Generate the existing field types with seeded random choices and Faker providers.
- Select databases by configured weights; each worker process owns a MongoClient and launches its configured writer threads.
- Poll `dbStats` for the configured target databases and signal local workers at `target.size * target.overshoot`.
- Create declared indexes on shard zero when `create_indexes` is enabled.
- Obtain the connection URI from an environment variable and apply configurable environment and URI-token guards before a real run.

This adaptation preserves generation, weighted selection, process/thread orchestration, write options, retry/backoff, size measurement, and stop behavior. Insert-error logs now omit driver exception payloads. Seeded random streams are repeatable, but ObjectIds are not deterministic and parallel scheduling prevents a byte-identical replay.

## Repository layout

| Path | Purpose |
|---|---|
| `seeder/` | Existing Python package: CLI, config, generation, guards, partition, writer, monitor, sizing. |
| `config/` | Configuration examples and synthetic JSON templates. |
| `Dockerfile`, `docker-compose.yml` | Non-root image and local execution. |
| `k8s/` | Indexed Job, example ConfigMap, placeholder Secret. |
| `tests/` | Unit regressions and opt-in disposable loopback MongoDB test. |
| `docs/DESIGN.md` | Architecture, preserved limitations, and adaptation decisions. |

## Install and dry-run

Use Python 3.11 or newer. A virtual environment isolates the dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m seeder --config config/config.test.yaml --dry-run 2
```

On PowerShell, activate with `.venv\Scripts\Activate.ps1` instead. Dry-run generates documents from the first configured template and exits without connecting to MongoDB or checking URI guards. It does not validate database access or the real stop lifecycle.

## Configuration

Copy `config/config.example.yaml` to ignored `config/config.yaml` and adjust it for the approved target. Keep environment-specific configuration and credentials private.

| Setting | Meaning |
|---|---|
| `env`, `safety.require_env` | Matching environment labels; the default is `pre`, but the labels are configurable. An empty required label disables that check. |
| `safety.prod_host_blocklist` | Case-insensitive tokens checked anywhere in the URI. Add deployment-specific identifiers in private configuration. |
| `target.size` | Byte target such as `20MB` or `1GB`; units use powers of 1024. |
| `target.metric` | `storageSize`, `dataSize`, `totalSize` (storage plus indexes), or `fsUsedSize`. |
| `target.overshoot` | Fraction of the target at which the monitor signals stop; this is a margin, not a hard storage cap. |
| `target.check_interval_s` | Time between measurements. |
| `write.procs`, `write.threads`, `write.batch_size` | Processes, threads per process, and documents per insertion batch. |
| `write.ordered`, `write_concern_w`, `journal`, `compressors`, `max_pool_size` | Existing write/client throughput controls. |
| `connection.uri_env` | Environment variable containing the URI; defaults to `MONGODB_URI`. |
| `create_indexes` | Shard zero creates template indexes when enabled. |
| `databases[]` | Database name, collection, weight, and JSON template filename. |

`SEEDER_CONFIG` selects the YAML file when `--config` is absent. `SEEDER_TEMPLATES_DIR` overrides the template directory. `JOB_COMPLETION_INDEX` selects the shard; `SEEDER_SHARD_INDEX` is its fallback, and `SEEDER_SHARD_TOTAL` defaults to one.

Templates support `objectId`, `int`, `double`, `bool`, `enum`, `string`, `uuid`, `date`, `faker`, `object`, and `array`. See the supplied JSON templates for options. Faker outputs are synthetic, although generated emails, phone numbers, and addresses can resemble real values. Keep dry-run outputs out of published validation artifacts.

## Real execution

Provision a suitable non-production target separately, inject its URI through your runtime secret mechanism, review the configuration, and run:

```bash
python -m seeder --config config/config.yaml
```

Do not place secrets in shell arguments, source files, committed YAML, or Docker build arguments. The guards validate configured labels and URI tokens; they cannot independently prove that the target is non-production.

Examples retain the original volume and concurrency values: the general example targets 4TB, test/fast examples target 1GB, and the Kubernetes ConfigMap example targets 3TB. These are not resource/cost recommendations. Reduce the target and concurrency in private configuration before a small test. Never run the examples against a real cluster merely to verify this repository.

## Docker and Kubernetes

See [DOCKER.md](DOCKER.md) for local builds, Compose, and optional pushes to your chosen registry. See [KUBERNETES.md](KUBERNETES.md) for the supplied manifests. The Kubernetes image is a deliberately non-resolving placeholder and must be replaced with your own built image.

## Validation

```bash
python -m pip install -e '.[dev]' -c requirements-validation.txt
python -m pip check
ruff check .
python -m unittest discover -s tests -v
python -m pip wheel --no-deps --wheel-dir dist .
```

The local lifecycle test is skipped unless `HC_SEEDER_LOCAL_MONGODB_URI` identifies a disposable loopback MongoDB without authentication. CI supplies a fresh local MongoDB service, tests Python 3.11 and 3.12, builds the image, performs a network-disabled container dry-run, validates Compose, and scans secrets. It neither accesses Atlas nor publishes images or packages.

See [the adoption review](docs/ADOPTION-REVIEW.md) for evidence, behavior differences, and unverified areas. Repository visibility does not grant an open-source license; no public reuse license has been selected.

## Risks and recovery

The monitor observes database-size metrics rather than an exact document count or a strict maximum. In-flight batches can overshoot the target. If measurement fails, the current monitor can exit without stopping writers; monitor its health and terminate the run if progress reporting stops. Kubernetes has the existing run deadline, while a standalone process has no equivalent hard time cap.

Stop a local process/container or delete the specific Job to stop generating new data. Existing seeded data remains. Remove only the databases created for the test after independently verifying their names; the tool has no automatic database cleanup. Details are in the deployment guides.

Last reviewed: 2026-10-07.
