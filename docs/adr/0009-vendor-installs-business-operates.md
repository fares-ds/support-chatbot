# ADR-0009: The vendor installs; the business runs the install

- Status: Accepted; the maintenance part is superseded by [ADR-0012](0012-vendor-operates-every-install.md)
- Date: 2026-10-05
- Deciders: Fares

## Context

Each business runs its own copy ([ADR-0006](0006-one-install-per-business.md)), and the product is proprietary ([ADR-0010](0010-proprietary-closed-source.md)). Someone has to install each copy, keep it running, upgrade it and back it up.

## Decision

- The vendor installs each copy on the business's own infrastructure: a business-owned VPS in V1, cloud providers later.
- The business then maintains the install and its infrastructure, including backups, with the vendor's support when needed.
- Updates ship as new container images, and database migrations run automatically.
- The vendor provides installation and operations documentation, backup and restore procedures, and the operational requirements.

## Consequences

- Install docs, operational requirements, and tested backup and restore procedures are V1 deliverables.
- Migrations must be safe to run unattended, because nobody from the vendor is necessarily present when they run.
- Minimum CPU, RAM and disk must be measured and published before the first install.

## Open

- Minimum CPU, RAM and disk; the recommended VPS configuration; whether any VPS provider is required or excluded.
- The exact update mechanism, who triggers an upgrade, and whether an upgrade requires a fresh backup first.
- How the vendor diagnoses a problem on an install it does not operate.
