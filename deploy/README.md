# The install bundle

What the vendor copies to a business's server to install or upgrade Support Chatbot (OPS-1). Every release publishes it as `support-chatbot-<version>.tar.gz`, with a SHA-256 checksum, on the release's GitHub page.

| File | What |
| --- | --- |
| `compose.yaml` | The stack. Every image is pinned: ours to the release, the others to fixed tags. |
| `Caddyfile` | HTTPS for the install's domain, and the API behind it |
| `env.template` | The install's settings, copied to `.env` next to `compose.yaml` |
| `README.md` | This file |

The server CLI, `sc`, joins the bundle in #8.

This directory also holds development files that stay out of the bundle: `compose.dev.yaml` and `dev.env` for the development stack, `tei.dev.Dockerfile`, `caddy/` (the Caddy image, with the dashboard's and widget's files), and `build_bundle.py` and its tests.

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
3. On the server, log in once as the user that runs Docker:

   ```sh
   docker login ghcr.io --username fares-ds-installs --password-stdin
   ```

   Paste the token and press Ctrl-D. Docker keeps it in that user's `~/.docker/config.json`; keep the file readable by that user only.
4. Note the expiry date. Before it, generate a new token, log in again, and delete the old one.

To cut an install off, delete its token under the machine account's tokens. The other installs keep working.

## Installing by hand, until `sc install`

1. Download the bundle and its checksum from the release, check them with `sha256sum --check support-chatbot-1.4.0.tar.gz.sha256`, and unpack them on the server.
2. Copy `env.template` to `.env`, and set at least `SC_DOMAIN` and `SC_POSTGRES_PASSWORD`.
3. Log in to the registry, as above.
4. Run `docker compose up --detach --wait` in the bundle's directory. The migration job runs first, then the rest of the stack.
5. Check `https://<domain>/api/health`.
