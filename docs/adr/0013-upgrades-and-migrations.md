# ADR-0013: How installs are upgraded

- Status: Accepted (approved in grilling round 6)
- Date: 2026-10-05
- Deciders: Fares

## Context

The vendor operates every install over server access ([ADR-0012](0012-vendor-operates-every-install.md)). Updates ship as new container images, and database migrations run automatically ([ADR-0009](0009-vendor-installs-business-operates.md)). Each install is a single server, so a failed migration without a backup can lose a business's conversations and knowledge base.

## Proposal

The vendor upgrades an install with one command on its server, for example `./sc upgrade 1.4.0`. The command:

1. **Checks first:** every service is healthy, there is enough free disk for a backup and the new images, and the target version can upgrade from the installed one.
2. **Backs up:** a Postgres dump and an archive of the uploaded files, kept on the server and copied off it. If the backup fails, the upgrade stops.
3. **Pulls** the target version's images, pinned by version, from the vendor's private registry.
4. **Migrates once:** a one-off container runs `alembic upgrade head` before the new version starts. Application containers never migrate on startup.
5. **Restarts and verifies:** starts the new version, waits for its health checks and runs a smoke test.
6. **Rolls back on failure:** puts the previous images back, and restores the step-2 backup only if the previous version cannot run on the migrated schema.

Migration rules that keep step 6 cheap:

- **Expand, then contract.** A release only adds tables, nullable columns and indexes, and backfills data in background jobs. Anything it removes is removed one release later, once no running version needs it. The previous version therefore keeps working on the new schema.
- **No downgrade migrations.** The rollback for a rare breaking change is the step-2 backup.
- **Every release is tested in CI** by upgrading a copy of the previous release's database, with seed data, to the new one.

## Consequences

- Each upgrade causes a short outage while services restart. The vendor schedules upgrades at quiet hours; the widget's retry and reconnect rules (RT-3, RT-5) cover messages sent during it.
- The vendor needs a private container registry, with pull credentials per install.
- Changing an install's embedding model is not an upgrade. It is a re-index job, and the old index serves until the new one is complete (KB-12).
- Postgres major-version upgrades get a separate runbook (dump and restore).

## Open

- Where the off-server backup copies go.
- Who owns routine daily backups, as distinct from the pre-upgrade backup ([ADR-0012](0012-vendor-operates-every-install.md)).

## Update, 2026-10-06 (grilling round 7)

Routine daily backups are also the vendor's, taken by the same tooling ([ADR-0012](0012-vendor-operates-every-install.md)).
