# ADR-0037: The repository is public; the product stays proprietary

- Status: Accepted
- Date: 2026-10-12
- Deciders: Fares
- Amends: [ADR-0010](0010-proprietary-closed-source.md), [ADR-0027](0027-repository-layout-and-git-workflow.md), [ADR-0036](0036-every-pull-request-gets-a-second-review.md)

## Context

The repository was private on a free personal account ([ADR-0027](0027-repository-layout-and-git-workflow.md)). That gave it 2,000 Actions minutes a month and no branch protection. October's first 12 days used 1,916 minutes. #46 cut the waste, but it left `main` without a CI run after merges ([ADR-0036](0036-every-pull-request-gets-a-second-review.md)).

GitHub-hosted runners are free and unlimited for public repositories, and public repositories get branch protection on a free account. On 2026-10-12 the vendor made the repository public.

Before that, gitleaks 8.24.3 scanned every commit on every branch, and a search covered tokens, private keys, `.env` files and the benchmark server's address. It found no live secret. Its three findings are test fixtures and the development key in `deploy/dev.env`, which says never to use it on a server; `sc install` generates each install's key.

## Decision

1. **The repository is public.** Anyone can read the code, the docs and the history.
2. **The product stays proprietary** ([ADR-0010](0010-proprietary-closed-source.md)). A `LICENSE` file reserves every right: no one may use, copy, modify, distribute or deploy the code without a written agreement with the vendor. Third-party code, data and models keep their own licenses.
3. **CI and Security run on `main` after each merge again,** since minutes no longer limit them. Drafts still skip CI, and the short run on x86-64 still runs only when the harness changes, or by hand; both save waiting time.
4. **Branch protection on `main` requires every review thread to be resolved** before a merge. It requires no status checks: a pull request that changes only docs skips CI, so a required check would never report and the pull request could never merge.

## Consequences

- Making the repository public can't be undone. Copies made while it is public stay public.
- Anyone can study what runs on each business's server, such as `deploy/sc` and the install, backup and upgrade code. Security can't rely on the code being hidden.
- The docs name OneClickDZ, and every commit carries the vendor's personal email address.
- Licensing is enforced by contract. A license check in public code could be removed, so ADR-0010's open question leans further towards contracts.
- Anyone can open a pull request from a fork, and that runs workflows. The vendor sets fork pull requests from outside contributors to need approval before their workflows run.
- The images on GitHub Container Registry keep their own visibility, which the repository's change doesn't alter. They stay private, so installs still pull with the machine account's tokens ([ADR-0031](0031-pull-tokens-from-a-machine-account.md)). The vendor confirms this in each package's settings.
- ADR-0036's "No GitHub Pro" rule now matters less: its main reason, branch protection, comes free with a public repository.

## Open

- None.
