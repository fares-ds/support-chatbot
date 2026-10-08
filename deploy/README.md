# The install bundle

What the vendor copies to a business's server to install or upgrade Support Chatbot (OPS-1). Every release publishes it as `support-chatbot-<version>.tar.gz`, with a SHA-256 checksum, on the release's GitHub page.

| File | What |
| --- | --- |
| `compose.yaml` | The stack. Every image is pinned: ours to the release, the others to fixed tags. |
| `Caddyfile` | HTTPS for the install's domain, and the API behind it |
| `env.template` | The install's settings, which `sc install` writes to `.env` |
| `sc` | The server CLI (ADR-0029): `install` now; `upgrade`, `backup`, `restore` and `status` follow |
| `README.md` | This file |

This directory also holds development files that stay out of the bundle:
- `compose.dev.yaml` and `dev.env`, for the development stack;
- `tei.dev.Dockerfile`;
- `caddy/`, the Caddy image, with the dashboard's and widget's files;
- `build_bundle.py`, `tests/` and `pyproject.toml`, which configures their checks.

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
4. pushes them to GitHub Container Registry as `ghcr.io/fares-ds/support-chatbot-backend:1.4.0` and `ghcr.io/fares-ds/support-chatbot-caddy:1.4.0`;
5. builds the bundle with `python3 deploy/build_bundle.py 1.4.0 dist/`, and attaches it and its checksum to a GitHub release named after the tag.

`build_bundle.py` refuses to build when an image is not pinned, or when `compose.yaml` reads a setting that `env.template` does not list. Every pull request that touches the backend or `deploy/` runs the same build without publishing, and starts the bundle on the CI runner.

ARM64 images wait for the minimum specs (OPS-2).

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
4. Note the expiry date. Before it, generate a new token, log in again as the service account (`sudo runuser --login supportchatbot --shell /bin/sh --command 'docker login ghcr.io --username fares-ds-installs --password-stdin'`), and delete the old one.

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
- the complete bundle.

Then it:
1. creates the service account, `supportchatbot`, and copies the bundle to `/opt/support-chatbot` (ADR-0032);
2. writes `.env` there, readable only by that account, with new random secrets: the Postgres password and the encryption key (SEC-6). It never prints them;
3. logs in to the registry, pulls the pinned images, runs the migration job, starts the stack, and waits for every health check;
4. checks `https://<domain>/api/health` through Caddy.

A setting from `env.template` can be changed with `--set`, such as `--set SC_EMBEDDING_MODEL=…`. Secrets can't be passed that way, since shell history and `ps` would keep them.

If a step fails, fix the cause and run `sc install` again: it keeps the secrets it wrote. Once an install has finished, `sc install` refuses to run again rather than replace its secrets.
