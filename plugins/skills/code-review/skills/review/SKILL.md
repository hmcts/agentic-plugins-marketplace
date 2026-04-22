---
name: review
description: Use when the user asks to review the current branch, check code quality, run a code review, or assess changes before merging.
---

Run a comprehensive review of the current branch by orchestrating three review passes in parallel, then aggregating their findings.

## Step 1 — run all three reviews in parallel

Invoke all three of the following simultaneously using the Agent tool (one agent per review), passing the same PR or branch context to each:

1. **Diff review** — run `git diff main...HEAD`, then for each changed file assess:
   - **Correctness** — does the logic do what it claims?
   - **Security** — injection, XSS, auth bypass, secrets-in-code?
   - **Performance** — N+1 queries, blocking calls, memory leaks?
   - **Readability** — confusing names, missing context, overly complex logic?
   - **Tests** — are changes covered? Are existing tests likely to break?

2. **PR Review Toolkit** — invoke the `pr-review-toolkit:review-pr` skill using the Skill tool.

3. **Official code-review** — invoke the `code-review:code-review` skill using the Skill tool.

## Step 2 — aggregate findings

Collect results from all three passes and deduplicate. Present a single unified report:

### Must fix
Blockers that should prevent merge (any finding rated critical/blocker across any reviewer).

### Should fix
Non-blocking improvements worth addressing before merge.

### Nit
Style or minor quality observations (low priority).

### Positive observations
What the reviewers agreed was well done.

If there are no issues in a category, state "None found."

## Step 3 — recommendation

End with a single overall recommendation: **Approve**, **Request changes**, or **Needs discussion**.

Note which reviewers agreed and which (if any) diverged.

Keep the final report concise and actionable. Reference specific file paths and line numbers.
