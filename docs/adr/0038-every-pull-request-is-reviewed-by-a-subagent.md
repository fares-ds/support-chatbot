# ADR-0038: Every pull request is reviewed by a local subagent

- Status: Accepted
- Date: 2026-10-13
- Deciders: Fares
- Amends: [ADR-0036](0036-every-pull-request-gets-a-second-review.md)

## Context

ADR-0036 sends every pull request to a second review by a session that did not write it, posted on GitHub with `/code-review <PR> --comment`. Risky pull requests also get `/code-review ultra <PR> --post`, which the vendor launches and which posts one comment.

Those commands are Claude Code. The same review can run in Cursor, on the checked-out branch, and the result stays in the chat. A subagent started with only the repository path and the diff does not carry the author's conversation.

## Decision

1. **Every pull request gets a Bugbot subagent review.** Before the pull request is marked ready, a new agent session checks out its branch and runs `/review-bugbot`. The subagent reviews the branch diff against `main`. The prompt is the repository path and the diff, and nothing of the author's reasoning.
2. **Risky pull requests also get a Security Review subagent.** The same session runs `/review-security` when the pull request touches `deploy/`, database migrations, `.github/` (CI and the release pipeline), `.gitattributes`, or secrets and sign-in. This replaces `/code-review ultra`.
3. **The outcome is written in the description.** The Reviews section records how many findings there were, which commit fixed each, and which stand and why. The session that wrote the code does not run either subagent.
4. **The rest of ADR-0036 stands.** The pull request stays a draft until those reviews are recorded, then it is marked ready and CI runs once. The vendor still reviews from the review guide and leaves a review. A merge still waits for green CI and for every GitHub review thread to be resolved.

## Consequences

- The second review no longer depends on posting `/code-review` to GitHub. A pull request can have no review threads. Branch protection still blocks a merge while a thread is open.
- The subagent review is not a GitHub approval. The vendor's review comment still stands in for one.
- Findings that are later posted on GitHub become threads, and each one is resolved before the merge.

## Open

- None.
