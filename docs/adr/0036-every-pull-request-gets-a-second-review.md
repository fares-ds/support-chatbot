# ADR-0036: Every pull request gets a second review, and the vendor's

- Status: Accepted
- Date: 2026-10-12
- Deciders: Fares
- Refines: [ADR-0027](0027-repository-layout-and-git-workflow.md), and settles its open point

## Context

One person builds Support Chatbot with Claude Code ([ADR-0027](0027-repository-layout-and-git-workflow.md)). Until 2026-10-11, the session that wrote a pull request also reviewed it, with `/code-review` before committing, and summed up its findings in the description. Four of those reviews found 36 issues, most of them real bugs, so reviewing pays. But the author was checking its own reasoning, and no pull request from #18 to #42 had a review on GitHub.

The vendor merged green pull requests without reading their diffs. Most feature pull requests added 600 to 1,450 lines; the benchmark harness (#21) added 5,611, and its datasets (#23) 15,729.

GitHub can't enforce a review here. A private repository on a free personal account has no branch protection ([ADR-0027](0027-repository-layout-and-git-workflow.md)). Claude Code opens pull requests as the vendor, and GitHub doesn't let a pull request's author approve it.

On 2026-10-12, reviews by a session that hadn't written them found 8 problems in #43 and 9 in #44. Both had already passed their author's review and CI.

## Decision

1. **A second review, by a session that didn't write the code.** The author opens the pull request as a draft, which CI skips. A Claude Code session or agent that starts without the author's context runs `/code-review <PR> --comment` at high. Its findings land as inline comments. The author answers each one, with the commit that fixes it or the reason it stands, and resolves it. Then the author marks the pull request ready, and CI runs once. The author's own review before committing stays.
2. **A deeper review for risky pull requests.** A pull request that touches `deploy/` (the server CLI and the install bundle), database migrations, `.github/` (CI and the release pipeline), `.gitattributes`, or secrets and sign-in also gets `/code-review ultra <PR> --post`. The vendor launches it; it is billed per run. It posts one comment rather than threads, so the author answers each of its findings in the description's Reviews section.
3. **A review guide for the vendor.** After its issue line, each description starts with a review guide of up to five items: the decisions the pull request makes, links to its riskiest lines, what wasn't tested, and what to try by hand. [`.github/pull_request_template.md`](../../.github/pull_request_template.md) holds the outline.
4. **Smaller pull requests.** About 400 lines of hand-written code at most. Generated files are marked `linguist-generated` in `.gitattributes`, so GitHub folds them away in the diff, and they don't count toward the 400.
5. **The merge rule.** The vendor merges once CI is green, the second review has posted and each of its threads is resolved, any ultra review's findings are answered, and the vendor has left a review on the pull request.
6. **No GitHub Pro for now.** For $4 a month, Pro's branch protection would block a merge while CI is red or a thread is open. It couldn't require the vendor's review, since a pull request's author can't approve it, or tell whether the second review ran, or whether a thread was answered before being resolved. The vendor keeps the merge rule.

## Consequences

- A pull request runs CI once, after its second review and fixes, rather than before them and again after. That matters on GitHub Free: October's first 12 days used 1,846 of its 2,000 Actions minutes, and the account's Actions budget is $0 (#46).
- Review findings and their answers sit on GitHub next to the lines, not only in the description.
- Formal approval isn't possible while Claude Code opens pull requests as the vendor. The vendor's review comment stands in for it.
- An automatic review on every push is not used. The `claude-code-action` workflow would spend the private repository's 2,000 Actions minutes a month, and Anthropic's managed Code Review needs a Team or Enterprise plan.

## Open

- Whether to move to GitHub Pro, or to give Claude Code an account of its own so that approvals become possible, once a second person works on the code.
