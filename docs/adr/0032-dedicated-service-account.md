# ADR-0032: An install runs as a dedicated service account

- Status: Accepted
- Date: 2026-10-08
- Deciders: Fares
- Refines: SEC-6, [ADR-0029](0029-server-cli-in-standard-library-python.md)

## Context

SEC-6 keeps an install's secrets in an environment file "readable only by the service account", without saying who that is. Building `sc install` (#8) needed an answer. The secrets include the Postgres password, the key that decrypts the identity secret and provider API keys, and the install's registry token ([ADR-0031](0031-pull-tokens-from-a-machine-account.md)). Whoever can run Docker on the server can read all of them anyway: membership of the docker group is as good as root.

## Decision

1. `sudo ./sc install` creates a system user, `supportchatbot`: no password, no login shell, in the docker group.
2. The install lives in `/opt/support-chatbot`, the account's home, which the account owns. `sc install` copies the bundle there.
3. `.env` there is mode 600, owned by the account.
4. `sc` runs every Docker command as the account. Its registry login is therefore stored in the account's home, and #9's cron runs as the account too.

## Consequences

- The vendor's own SSH login holds neither the secrets nor Docker access. The vendor reaches them through `sudo`.
- `sc` commands run with `sudo`. `install` checks for it before changing anything.
- One install per server, at a fixed path, which matches [ADR-0006](0006-one-install-per-business.md).
