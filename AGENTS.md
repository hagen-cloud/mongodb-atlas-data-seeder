# AGENTS.md — mongodb-atlas-data-seeder

Hagen Cloud synthetic MongoDB data seeder. Keep code, comments, documentation, commit messages, and GitHub content in English.

- Preserve the package layout, CLI, generation and partition algorithms, process/thread orchestration, writes, and measured stop condition unless a behavior change is explicitly authorized.
- Never commit real URIs, credentials, deployment names, private network details, local manifests, or execution logs.
- Use existing nearby documentation before adding new documents.
- Keep tests isolated: no Atlas endpoints or external credentials. The opt-in integration test accepts only a disposable loopback MongoDB and removes only its own uniquely named database.
- Use conventional branch prefixes and incremental commits. Open a PR rather than merging adoption changes directly to main.
- Do not publish an image/package or select an open-source license without authorization.
- Do not claim Kubernetes/Vault/network controls that are not shipped.
- Keep preserved limitations explicit; tests do not establish production readiness.

Verification: install `.[dev]` with `requirements-validation.txt` constraints, run `pip check`, `ruff check .`, unit tests, all example dry-runs, wheel build, Compose validation, network-disabled container dry-run, and secret scanning. Run the loopback lifecycle test when a disposable MongoDB is available; otherwise report it as skipped and verify hosted CI results.
