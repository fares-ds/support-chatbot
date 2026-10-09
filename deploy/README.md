# The install bundle

What the vendor copies to a business's server to install or upgrade Support Chatbot (OPS-1). Every release publishes it as `support-chatbot-<version>.tar.gz`, with a SHA-256 checksum, on the release's GitHub page.

| File | What |
| --- | --- |
| `compose.yaml` | The stack. Every image is pinned: ours to the release, the others to fixed tags. |
| `Caddyfile` | HTTPS for the install's domain, and the API behind it |
| `env.template` | The install's settings, which `sc install` writes to `.env` |
| `sc` | The server CLI (ADR-0029): `install`, `upgrade`, `status`, `backup` and `restore` |
| `release.txt` | The release's version, and the release it upgrades from (ADR-0034) |
| `README.md` | This file |

This directory also holds development files that stay out of the bundle:
- `compose.dev.yaml` and `dev.env`, for the development stack;
- `tei.dev.Dockerfile`;
- `caddy/`, the Caddy image, with the dashboard's and widget's files. Until Docker republishes `caddy:2.11.7-alpine` with a fixed Go, it builds Caddy itself with a newer Go (see its Dockerfile);
- `build_bundle.py`, `upgrade_test.py`, `tests/` and `pyproject.toml`, which configures their checks.

## Releases

A `vX.Y.Z` tag on `main` is a release (ADR-0027):

```sh
git switch main && git pull --ff-only
git tag v1.4.0 && git push origin v1.4.0
```

The Release workflow (`.github/workflows/release.yml`) then:

1. checks that the tag is on `main`;
2. builds the backend image and the Caddy image for linux/amd64;
3. scans both, and stops on a high or critical vulnerability that has a fix;
4. runs the upgrade test from the previous release on those images (below), and stops if it fails;
5. pushes them to GitHub Container Registry as `ghcr.io/fares-ds/support-chatbot-backend:1.4.0` and `ghcr.io/fares-ds/support-chatbot-caddy:1.4.0`;
6. builds the bundle with `python3 deploy/build_bundle.py 1.4.0 dist/ --upgrades-from 1.3.0`, recording the release the upgrade test started from, and attaches it and its checksum to a GitHub release named after the tag.

`build_bundle.py` refuses to build when an image is not pinned, or when `compose.yaml` reads a setting that `env.template` does not list. Every pull request that touches the backend or `deploy/` runs the same build without publishing, and starts the bundle on the CI runner.

ARM64 images wait for the minimum specs (OPS-2).

### The upgrade test

On every pull request that touches `backend/` or `deploy/`, the Release workflow's `upgrade` job runs `upgrade_test.py` (OPS-4, ADR-0013). On a release tag, the publish job runs it on the images it built, after scanning them and before pushing them. It brings up the previous release (the newest published one) from its bundle and images, seeds its database (`backend/tests/upgrade_seeds/`), and runs the smoke test. Then it migrates the database with the candidate's image and runs the candidate's smoke test, and runs the previous release's smoke test once more on the migrated database, as after a rollback. Last, a negative control renames a column the previous release reads, and that release's smoke test must fail.

The smoke test: a release's migration job, API and worker start; Postgres and Valkey answer; and the worker writes a heartbeat after the start, which the API reads back.

To run it on a machine with Docker, build the candidate's image first:

```sh
docker build --tag ghcr.io/fares-ds/support-chatbot-backend:0.0.0 backend
python3 deploy/upgrade_test.py --candidate 0.0.0  # Python 3.10 or later
```

The previous release's images are private, so log in to the registry first, or build them from the release's tag: `git archive --format=tar v0.1.0:backend | docker build --tag ghcr.io/fares-ds/support-chatbot-backend:0.1.0 -`. `--previous none` tests a first release. The test runs as its own Compose project, `sc-upgrade-test`, and removes its volumes when it ends.

## Pulling the images: one read-only token per install

The packages are private, so each install logs in to GitHub Container Registry. The registry accepts only classic personal access tokens. A classic token can read every package its account can read, so the tokens come from a machine account that can read nothing but our two packages. One token per install means a leaked token is revoked without touching any other install.

### Once: the machine account

1. Create a GitHub account for this, such as `fares-ds-installs`, with its own email address and two-factor authentication. GitHub's terms allow a person one machine account, used only for automation.
2. After the first release, open each package, `support-chatbot-backend` and `support-chatbot-caddy`, from the vendor's profile under **Packages**. In **Package settings**, under **Manage access**, add the machine account with the **Read** role.

Give the machine account nothing else: no access to the repository, and no other packages.

### For each install: a token

1. Signed in as the machine account, open **Settings**, **Developer settings**, **Personal access tokens**, **Tokens (classic)**, then **Generate new token (classic)**.
2. Name it after the install, such as `install-oneclickdz`, set an expiry, and tick only **read:packages**.
3. Give it to `sc install`, which logs in as the service account (below). Docker keeps the login in `/opt/support-chatbot/.docker/config.json`, readable only by that account.
4. Before it expires, generate a new token (`sc status` warns 14 days ahead), log in again as the service account (`sudo runuser --login supportchatbot --shell /bin/sh --command 'docker login ghcr.io --username fares-ds-installs --password-stdin'`), and delete the old one.

To cut an install off, delete its token under the machine account's tokens. The other installs keep working.

## Installing

On a fresh Ubuntu server with Docker Engine and its Compose plugin, Python 3.10 or later, and the business's domain pointing at it:

1. Download the bundle and its checksum from the release, check them with `sha256sum --check support-chatbot-1.4.0.tar.gz.sha256`, and unpack them.
2. In the unpacked directory, run:

   ```sh
   sudo ./sc install --domain chat.example.com --registry-user fares-ds-installs
   ```

   It asks for the install's registry token without echoing it; `--token-file` reads it from a file instead.

`sc install` checks everything first, and stops before changing anything if one is missing:
- sudo;
- Python 3.10;
- Docker, and Compose 2.22;
- 30 GB of free disk;
- ports 80 and 443;
- cron, which runs the daily backup;
- the complete bundle.

Then it:
1. creates the service account, `supportchatbot`, and copies the bundle to `/opt/support-chatbot` (ADR-0032);
2. writes `.env` there, readable only by that account, with new random secrets: the Postgres password and the encryption key (SEC-6). It never prints them;
3. logs in to the registry, pulls the pinned images, runs the migration job, starts the stack, and waits for every health check;
4. checks `https://<domain>/api/health` through Caddy;
5. schedules the daily backup in `/etc/cron.d/support-chatbot`;
6. reminds you to copy `.env` into your password manager. Do it now: a restore needs it (below).

A setting from `env.template` can be changed with `--set`, such as `--set SC_EMBEDDING_MODEL=…`. Secrets can't be passed that way, since shell history and `ps` would keep them.

If a step fails, fix the cause and run `sc install` again: it keeps the secrets it wrote. Once an install has finished, `sc install` refuses to run again rather than replace its secrets.

## Checking an install

`sudo /opt/support-chatbot/sc status` prints one line per part of the install, each ok, warning or problem, with names, counts and times only (OPS-7, SEC-10):

```
Support Chatbot 1.5.0 at https://chat.example.com (installed 2026-09-01; upgraded from 1.4.0 on 2026-10-09)
Services        ok       8 running and healthy; migrations done
Models          ok       tei_embed, tei_rerank and ollama answer
Health          ok       postgres, valkey and worker answer; schema 0002; the worker beat 12 s ago
Disk            ok       /opt/support-chatbot 41 GB free; /var/lib/docker 41 GB free
Queue           ok       0 jobs waiting
Last backup     ok       2026-10-09 03:17 (6 h ago), snapshot 3f2a9c1e
Registry token  warning  expires 2026-10-20, in 11 days: generate a new one
Status: 1 warning
```

It exits 0 when every line is ok, 1 when the worst is a warning, and 2 when something is a problem: the monitoring plugins' convention, so a monitor or a cron job can alert on it.

| Line | A problem | A warning |
| --- | --- | --- |
| Services | a container stopped or unhealthy, or the migration job failed | |
| Models, Health | `/api/health` says a check is down, or does not answer | |
| Disk | under 10 GB free, the minimum `sc upgrade` needs | |
| Queue | Valkey does not answer | |
| Last backup | no success in 26 hours, or ever | the latest run failed, but a success is recent |
| Registry token | expired, or refused by GitHub | it expires within 14 days, or GitHub cannot be asked (ADR-0031) |

## Upgrading

Copy the new release's bundle to the server as for an install, check it and unpack it, then run its `sc` with the version you mean:

```sh
sudo ./sc upgrade 1.5.0
```

A release upgrades only from the release CI tested it from, or a later one: its `release.txt` records which (ADR-0034). To cross several releases, upgrade through each in turn. Run upgrades at quiet hours: the API is down for the restart (OPS-5).

Before changing anything, `sc upgrade` checks:
- that the bundle is the version given;
- that it can upgrade from the installed version;
- that every service is healthy;
- that 10 GB is free for the backup and the new images, a placeholder until #17 sets the minimum specs.

Then it:
1. backs up, as `sc backup` does, tagging the snapshot `pre-upgrade`, `from-<installed>` and `to-<target>`. If the backup fails, the upgrade stops;
2. copies the new files to `next/` and pulls the new images. If that fails, the upgrade stops and the install is unchanged;
3. keeps the current files in `previous/` (until the next upgrade), puts the new ones in place, and adds any new secrets to `.env`, keeping the others;
4. stops the API and the worker, runs the new migration job once, starts the stack, and waits for every health check and a fresh worker heartbeat;
5. records the new version in `.installed`.

If any of step 3 or 4 fails, it rolls back. It puts the previous files and images back; their migration job leaves the newer schema alone, and expand-then-contract keeps them working on it (ADR-0013). If the previous release can't run on the migrated database either, it restores the pre-upgrade snapshot. Either way it exits 1 and names the snapshot. If the rollback fails too, it says so: fix the cause, then run `sudo /opt/support-chatbot/sc restore --snapshot <ID>`.

## Backups

Every day at 03:17, server time, cron runs `sc backup` as the service account (OPS-6). One run makes one restic snapshot holding a dump of the database and the stored files (`/data/files`: uploads and their parsed text). restic encrypts the snapshot before it leaves the server, and runs in the bundle's pinned image, so the server needs nothing beyond Docker. Every snapshot is kept until open question 2 in the PRD sets a retention policy.

`.env` stays out of backups (ADR-0033). It holds the encryption key for the secrets in the database, and the repository's password, without which nobody can open the backups once the server is lost. Keep a copy of each install's `.env` in your password manager.

### Setting up an install's repository

The repository is a restic repository off the server: S3-compatible storage (`s3:`, for Backblaze B2, Hetzner, Cloudflare R2, Wasabi or AWS), a restic REST server (`rest:`), or an absolute path, such as a mounted disk. `sc` refuses anything else, such as a relative path, which restic would write inside its throwaway container.

1. Give `sc install` the repository with `--set SC_RESTIC_REPOSITORY=s3:https://<endpoint>/<bucket>/<install>`, or add it to `.env` later. A REST server's URL carries its password, so it goes in `.env` only.
2. For S3, add the keys with `sudoedit /opt/support-chatbot/.env`: `SC_RESTIC_AWS_ACCESS_KEY_ID` and `SC_RESTIC_AWS_SECRET_ACCESS_KEY`. `sc install` refuses the secret key in `--set`, because shell history would keep it.
3. Run the first backup by hand: `sudo /opt/support-chatbot/sc backup`. It creates the repository, which takes the password `sc install` generated.
4. Copy the finished `.env` into your password manager.

### Checking backups

- `/opt/support-chatbot/backup-status.json` records the last run (its time, result, message and snapshot) and the time of the last success. `sc status` reports it.
- `backup.log`, next to it, holds the last run's output.
- A failed run exits non-zero with a plain message naming the step that failed: dumping the database, or saving the snapshot to the repository.

To list the snapshots, run `sudo docker compose run --rm restic snapshots` in `/opt/support-chatbot`. For a repository on a local path, add `--volume <path>:<path>` after `--rm`.

## Restoring

`sudo /opt/support-chatbot/sc restore` brings back the database and the stored files as of the latest snapshot; `--snapshot <ID>` picks another. Before changing anything, it:
- names the snapshot and its time;
- checks that `.env` holds the encryption key the snapshot was made with;
- asks you to type `yes` (`--yes` skips the question).

Then it fetches the database dump, stops the API and the worker, empties the job queue, restores the files (removing any added since the snapshot), replaces the database, runs the migration job, starts the stack, and checks `https://<domain>/api/health`. If a step fails, fix the cause and run it again: it starts over from the snapshot. A backup, a restore and an upgrade never run at once: the second refuses to start.

### Onto a new server

1. Point the domain at the new server: `sc install` checks it over HTTPS.
2. Install the same release, or a newer one, with `sc install` (above). It generates new secrets.
3. With `sudoedit /opt/support-chatbot/.env`, replace them with the old install's from your password manager: `SC_ENCRYPTION_KEY`, `SC_RESTIC_REPOSITORY`, `SC_RESTIC_PASSWORD`, and the S3 keys. Keep the new `SC_POSTGRES_PASSWORD`: the dump doesn't carry it.
4. Run `sudo /opt/support-chatbot/sc restore`.

If you forget the key in step 3, the restore refuses and changes nothing.
