# Design

Last reviewed: 2026-10-07. Hagen Cloud adaptation: 1.0.

## Goal and preserved architecture

Generate synthetic data in approved non-production MongoDB targets until a measured database-size target is reached. MongoDB Atlas is the intended managed target; local MongoDB is used for isolated testing. The adaptation retains the existing package modules and CLI.

```text
config + JSON templates + runtime URI
                |
         CLI / one shard
          /           \
  monitor thread    P worker processes
  poll dbStats       T writer threads per process
          \          / generate -> weighted database -> insert_many
           target MongoDB
```

Each process creates its own MongoClient. Every thread has its own RNG and Faker seed derived from shard, process, and thread indices. The client pool is configured per process. In Kubernetes, an Indexed Job provides shard indices; standalone and Compose default to one shard.

## Generation and partition

JSON schema generation retains ObjectId, numeric, boolean, enum, string, UUID, date, Faker, object, and array fields. Weighted selection remains proportional to configured database weights. RNG/Faker choices can be repeated with the same seed, while ObjectIds and concurrent ordering are not deterministic. Separate seeds do not mathematically guarantee that generated values never overlap.

No user records or database dumps are shipped. Templates are synthetic schema definitions, and generated personal-looking fields are fictional. Do not publish generated logs as if they were anonymized real data.

## Writes, measurement, and stop

Writer threads generate one batch at a time and call `insert_many` with the configured ordering. The driver retains the existing write options and `retryWrites=True`. The writer catches insertion exceptions, waits one second, and continues unless stopped. This adaptation changes only that warning's payload: log the exception class instead of the raw driver message.

Every shard's monitor polls `dbStats` for the unique configured database names. `totalSize` adds storage and index size; `fsUsedSize` reads the first database's server statistics once. The effective availability and scope of fields depend on server/deployment behavior and must be validated on the target. When the measured value reaches `target.size * target.overshoot`, the monitor signals its local workers.

The target is measured rather than converted to a fixed document count because compression and indexes affect storage. In-flight batches can overshoot; the factor is a margin, not an exact cap. Existing data contributes to the measurement, so a restarted run can stop quickly when the target is already reached; it is not a checkpointed exactly-once import.

## Generic execution and safety decisions

Decided for this adaptation on 2026-10-07:

- Use repository name `mongodb-atlas-data-seeder`, matching the Python distribution and the established lowercase hyphenated repository style. This is not a new organization-wide naming standard.
- Preserve the implementation, schemas, example target sizes, concurrency values, environment defaults, and control flow.
- Replace organization-specific URI blocklist tokens with generic examples; private operating policies must restore target-specific identifiers as appropriate. The blocklist algorithm is unchanged.
- Build the image locally by default rather than requiring a specific registry. Kubernetes uses a non-resolving registry placeholder until the operator provides an image.
- Keep standard Kubernetes Secret references; do not claim a Vault/CSI or cloud-specific integration that is not included.
- Replace the inherited pipeline with validation-only GitHub Actions. Tests use a disposable loopback MongoDB; CI does not require Atlas secrets or deploy/publish resources.
- Publish the sanitized code only after content/history review and the maintainer's confirmation of publication rights. No open-source license was selected by this adaptation.

## Preserved limitations

- Environment-label and URI-token guards are configurable heuristics. They do not independently verify the real target's environment; URI matching includes usernames, passwords, and query values as well as hosts.
- Config/schema numeric ranges and shard indices are not comprehensively validated. Review configuration before executing.
- A monitor measurement exception can terminate that thread without signaling writer stop. Standalone runs have no built-in hard deadline. Monitor progress and retain an external termination path.
- Writer exceptions are broadly retried and partial inserts can occur. There is no application-level exactly-once or explicit reconciliation of failed batches.
- Worker exit statuses and final health are not comprehensively aggregated; normal completion is not proof that every requested write succeeded.
- Default date bounds can mix timezone-aware and naive values when a maximum is omitted. The supplied templates use explicit bounds; this behavior is not changed.
- The size threshold does not measure whole-account storage or application resilience. Resource and connection estimates are operating guidance, not guarantees.
- Live Atlas behavior, managed-tier limits, network topology, Kubernetes admission/scheduling, and production readiness are unverified by local tests.

## Operational boundaries

Supply real URI credentials at runtime. Keep local configs, real Secret manifests, diagnostics, and database identifiers out of public source control. Other unhandled driver errors can still include deployment details despite the insert warning improvement; keep real execution logs private.

Provision network isolation, resource quotas, secret management, and scheduling controls separately where needed. The three supplied Kubernetes manifests do not create them. Recovery means stopping the specific test process/container/Job and separately cleaning up verified test databases; stopping generation cannot reverse writes.

## References

- [PyMongo MongoClient](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/mongoclient/)
- [Indexed Jobs](https://kubernetes.io/docs/tasks/job/indexed-parallel-processing-static/)
- [Docker Compose build specification](https://docs.docker.com/reference/compose-file/build/)
