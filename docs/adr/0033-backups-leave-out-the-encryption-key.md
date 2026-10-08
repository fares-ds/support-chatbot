# ADR-0033: Backups leave out the encryption key

- Status: Accepted
- Date: 2026-10-08
- Deciders: Fares
- Refines: SEC-6, SEC-8, OPS-6, [ADR-0012](0012-vendor-operates-every-install.md)

## Context

`sc backup` (#9) sends a Postgres dump and the stored files to a restic repository off the server. From M1, the dump holds the identity secret and the provider API keys, encrypted with `SC_ENCRYPTION_KEY` (SEC-6), which lives in `.env`. A backup holding both the dump and the key would undo that encryption for anyone who can open the backup.

GitLab's backups handle the same problem the same way. Its backup task leaves out `gitlab-secrets.json`, which holds the database encryption key, because "storing encrypted information in the same location as its key defeats the purpose of using encryption in the first place" ([Back up GitLab](https://docs.gitlab.com/administration/backup_restore/backup_gitlab/)). The administrator backs that file up separately.

## Decision

1. A backup holds the database dump and the stored files, and nothing from `.env`.
2. The vendor keeps a copy of each install's `.env` in their password manager. That copy holds the encryption key, the restic repository and its password, and the S3 keys. The vendor needs it anyway: without the restic password, nobody can open the backup once the server is lost. `sc install` ends by saying so.
3. Each backup holds a SHA-256 fingerprint of the key. Before changing anything, `sc restore` compares it with the key in `.env`, and refuses on a mismatch.
4. A restore onto a new server runs in three steps:
   1. `sc install` on the new server;
   2. paste the old install's encryption key and restic settings from the password manager into `.env`;
   3. `sc restore`.

## Consequences

- Someone who obtains both the repository and its password still can't decrypt the stored secrets.
- Losing the password-manager entry loses the backups, since the restic password is in it. If only the key were lost, the Owner could re-enter the provider keys and the identity secret could be rotated.
- A restore needs one manual step: pasting the old settings. The fingerprint check turns a forgotten paste into a plain refusal, instead of an install whose secrets can't be decrypted.
- Backups and restores run the bundle's pinned restic image, so the server still needs only Docker ([ADR-0029](0029-server-cli-in-standard-library-python.md)).
- Every backup carries `sha256(SC_ENCRYPTION_KEY)`. M1's encryption must therefore never use that value as its working key, or every backup would carry the key. Derive working keys some other way, such as HKDF with a purpose label.

## Open

- Where the repository lives, how long snapshots are kept, and how often a restore is tested: open question 2 in the PRD. Until it's decided, every snapshot is kept.
