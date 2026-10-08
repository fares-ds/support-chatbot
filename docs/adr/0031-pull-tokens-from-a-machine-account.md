# ADR-0031: Install pull tokens come from a machine account

- Status: Accepted
- Date: 2026-10-08
- Deciders: Fares
- Refines: OPS-1, [ADR-0027](0027-repository-layout-and-git-workflow.md)

## Context

Installs pull our images from GitHub Container Registry, which is private, with a read-only token per install (OPS-1). Building the release pipeline (#6) showed what such a token can be:

- [GitHub Packages only accepts classic personal access tokens](https://docs.github.com/en/packages/learn-github-packages/about-permissions-for-github-packages), not fine-grained ones.
- A classic token with `read:packages` reads every package its account can read. It cannot be limited to one package, or to one install.
- The packages belong to the vendor's personal account, `fares-ds`.

A token from that account, leaked from one server, could read every package the account can see, now or later.

## Decision

1. **A machine account** holds the pull tokens, for example `fares-ds-installs`. GitHub's terms allow a person one machine account, used only for automation. It has the Read role on the two packages, `support-chatbot-backend` and `support-chatbot-caddy`, and access to nothing else: not the repository, not other packages.
2. **One classic token per install** on that account, with only the `read:packages` scope, named after the install, with an expiry date.
3. Revoking an install's access is deleting its token. The other installs keep working.

`deploy/README.md` holds the procedure.

## Consequences

- The vendor keeps a second GitHub login, with its own email address and two-factor authentication.
- A leaked token reads only our two packages: the code the install already runs.
- Tokens expire, so each install needs its token rotated before the expiry date. `sc install` (#8) and `sc status` (#11) should make the expiry visible.
- A new package, such as a future frontend image, needs the machine account added to it.

## Open

- How far ahead of expiry `sc status` warns.
