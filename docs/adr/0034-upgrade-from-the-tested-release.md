# ADR-0034: A release upgrades from the release CI tested it from

- Status: Accepted
- Date: 2026-10-08
- Deciders: Fares
- Refines: OPS-3, OPS-4, [ADR-0013](0013-upgrades-and-migrations.md)

## Context

[ADR-0013](0013-upgrades-and-migrations.md) has `sc upgrade` check "that the target version can upgrade from the installed one", without saying which can. Two of its other rules decide it:
- A contract step drops what *the previous release* has stopped using.
- A rollback puts the previous release's images back on the migrated schema.

Skipping a release breaks that pairing. Say 1.6.0 drops a column that 1.5.0 stopped reading. If 1.4.0, which still reads it, upgrades straight to 1.6.0 and the upgrade fails, the rollback brings 1.4.0 back on a schema without the column.

The upgrade test (#7) shows that one path is safe: from the release it started from, which is the newest published release when the candidate is built.

## Decision

1. The release pipeline records in each bundle's `release.txt` the release its upgrade test started from, as `upgrades_from`. The first release records none.
2. `sc upgrade <version>` accepts an installed version from `upgrades_from` up to, but not including, the target. It refuses a skipped release, the same version, an older one, and any upgrade to a first release. Each refusal is a plain message, and nothing changes.
3. To cross several releases, the vendor upgrades through each one in turn.

## Consequences

- The only path `sc upgrade` allows is one CI has tested, so a rollback lands on a release that runs on the migrated schema, or one whose backup is restored.
- A patch on an older line, such as 1.4.1 built after 1.5.0 exists, records 1.5.0 if it's built from main. Releases from a maintenance branch would need their own rule; V1 releases only from main ([ADR-0027](0027-repository-layout-and-git-workflow.md)).
- Installs that fall several releases behind take several upgrades, each with its own backup.
