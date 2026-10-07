# Docker execution

Last reviewed: 2026-10-07.

## Objective and prerequisites

Build and run the existing seeder in a non-root container without a pre-existing image registry. Install Docker with a Linux container engine. Real runs additionally require a reviewed non-production config, URI secret, network access, storage budget, and recovery ownership.

## Build and validate without a database

```bash
docker build -t mongodb-atlas-data-seeder:local .
docker run --rm --network none -v "$PWD/config:/etc/seeder:ro" \
  mongodb-atlas-data-seeder:local --config /etc/seeder/config.test.yaml --dry-run 2
```

The image keeps the original Python 3.12 slim multi-stage build and UID 10001. The build context excludes environment files, local config, manifests, tests, logs, and caches. No corporate proxy configuration is embedded. Use your Docker/build infrastructure's proxy settings when required; keep proxy credentials out of the Dockerfile.

## Compose

```bash
cp .env.example .env
docker compose build seeder
docker compose run --rm seeder --dry-run 2
```

The checked-in environment example has an empty URI and selects `config.test.yaml`. Compose builds the local image and mounts `config/` read-only; it does not need registry authentication. `.env` is ignored by Git and Docker. Do not print `docker compose config` output after filling real credentials; use `--quiet` to validate without displaying resolved values.

For a disposable local MongoDB, put `MONGODB_URI=mongodb://mongo:27017` in `.env`. Copy a config to ignored `config/local-test.yaml`, reduce its target to a small amount, and set `SEEDER_CONFIG_FILE=local-test.yaml` in `.env` before:

```bash
docker compose --profile local up -d mongo
docker compose up seeder
```

The optional database binds port 27018 only on loopback. A seeder container connects through the service name `mongo`; a host Python process uses `mongodb://127.0.0.1:27018`. Compose keeps one shard; concurrency comes from the configured processes and threads.

For Atlas, obtain the URI through your runtime secret source instead of putting it in command arguments. Validate feature limits, permissions, private/public networking, and intended volume for the target. Only execute after approval of the exact target.

## Optional registry publication

Build/push to a registry you control; there is no bundled registry account or published image:

```bash
# Replace these placeholders with an approved registry/repository and immutable tag.
docker login <registry>
docker tag mongodb-atlas-data-seeder:local <registry>/<repository>:<tag>
docker push <registry>/<repository>:<tag>
```

Update the Kubernetes image reference to that tag and configure pull authentication separately if necessary. CI validates images without publishing them.

## Validation, risks, and recovery

Confirm that dry-run completes with networking disabled, and that real test runs report progress, target reached, and the final measurement. A dry-run alone cannot verify database writes or recovery. Treat runtime logs as private: database/collection names and connection failures can reveal deployment details. Insert error messages omit driver payloads, but other unhandled errors can still expose connection details.

Terminate the seeder with `docker compose stop seeder` when needed. For a local disposable test:

```bash
docker compose --profile local down
```

This removes the Compose containers/network. It does not remove data from Atlas or external MongoDB targets. The optional local MongoDB has no configured persistent volume; remove only the disposable test resources you intentionally created.

## References

- [Docker Compose build specification](https://docs.docker.com/reference/compose-file/build/)
- [Docker Compose services](https://docs.docker.com/reference/compose-file/services/)
- [PyMongo MongoClient](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/mongoclient/)
