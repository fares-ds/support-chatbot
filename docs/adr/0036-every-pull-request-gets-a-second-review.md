# ADR-0036: Every pull request gets a second review, and the vendor's

- Status: Accepted
- Date: 2026-10-12
- Deciders: Fares
- Refines: [ADR-0027](0027-repository-layout-and-git-workflow.md), and settles its open point

## Context

One person builds Support Chatbot with Claude Code ([ADR-0027](0027-repository-layout-and-git-workflow.md)). Until 2026-10-11, the session that wrote a pull request also reviewed it, with `/code-review` before committing, and summed up its findings in the description. Four of those reviews found 36 issues, most of them real bugs, so reviewing pays. But the author was checking its own reasoning, and no pull request from #18 to #42 had a review on GitHub.

The vendor merged green pull requests without reading their diffs. Most ran to 500 to 1,400 lines; #35 had 3,365.

GitHub can't enforce a review here. A private repository on a free personal account has no branch protection ([ADR-0027](0027-repository-layout-and-git-workflow.md)). Claude Code opens pull requests as the vendor, and GitHub doesn't let a pull request's author approve it.

On 2026-10-12, reviews by a session that hadn't written them found 8 problems in #43 and 9 in #44. Both had already passed their author's review and CI.

## Decision

1. **A second review, by a session that didn't write the code.** Once CI is green, a Claude Code session or agent that starts without the author's context runs `/code-review <PR> --comment` at high. Its findings land as inline comments. The author answers each one, with the commit that fixes it or the reason it stands, and resolves it. The author's own review before committing stays.
2. **A deeper review for risky pull requests.** A pull request that touches `deploy/` (the server CLI and the install bundle), database migrations, the release pipeline, or secrets and sign-in also gets `/code-review ultra <PR> --post`. The vendor launches it; it is billed per run.
3. **A review guide for the vendor.** Each description opens with up to five items: the decisions the pull request makes, links to its riskiest lines, what wasn't tested, and what to try by hand. [`.github/pull_request_template.md`](../../.github/pull_request_template.md) holds the outline.
4. **Smaller pull requests.** About 400 lines of hand-written code at most. Generated code and data go in their own commits.
5. **The merge rule.** The vendor merges once CI is green, every review thread is resolved, and has left a review on the pull request.
6. **No GitHub Pro for now.** The author, the reviewers and the merger all act through one account, so GitHub's rules would enforce little. The vendor keeps the merge rule.

## Consequences

- A pull request waits a few minutes after CI for its second review, and longer when that review finds something to fix.
- Review findings and their answers sit on GitHub next to the lines, not only in the description.
- Formal approval isn't possible while Claude Code opens pull requests as the vendor. The vendor's review comment stands in for it.
- An automatic review on every push is not used. The `claude-code-action` workflow would spend the private repository's 2,000 Actions minutes a month, and Anthropic's managed Code Review needs a Team or Enterprise plan.

## Open

- Whether to move to GitHub Pro, or to give Claude Code an account of its own so that approvals become possible, once a second person works on the code.
