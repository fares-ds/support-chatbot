# ADR-0012: The vendor operates every install over server access

- Status: Accepted
- Date: 2026-10-05
- Deciders: Fares
- Supersedes: the maintenance part of [ADR-0009](0009-vendor-installs-business-operates.md)

## Context

[ADR-0009](0009-vendor-installs-business-operates.md) had the business maintain its install, with the vendor's support. In grilling round 4 the vendor chose to keep access to each install's server and maintain everything from there.

## Decision

Each business grants the vendor access to the server or host its install runs on. The vendor maintains the install from there: upgrades, monitoring and fixes.

## Consequences

- Operations are the vendor's job. The vendor is one person (Fares), so the number of installs is limited by what one person can operate.
- The vendor's access must be secured and revocable by the business, for example SSH keys only, one per vendor machine.
- No telemetry or phone-home feature is needed in V1, because the vendor inspects installs directly.

## Open

- Who owns routine backups. Round 3 said the business; "maintain everything" in round 4 suggests the vendor.

## Update, 2026-10-06 (grilling round 7)

The vendor owns backups. The vendor's tooling takes a daily database dump and an archive of uploaded files, copies them off the server, and the vendor tests a restore regularly. Still open: where the off-server copies go, and how long backups are kept.
