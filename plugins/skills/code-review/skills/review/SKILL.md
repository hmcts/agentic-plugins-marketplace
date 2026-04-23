---
name: review
description: Use when the user asks to review the current branch, check code quality, run a code review, or assess changes before merging.
---

Run a comprehensive review of the current branch by orchestrating three review passes in parallel, then aggregating their findings.

## Step 0 — check optional reviewers are installed

Run the following to check which plugins are available:

```bash
claude plugin list --json 2>/dev/null | python3 -c "
import json,sys
installed = {p['id'] for p in json.loads(sys.stdin.read()).get('installed', [])}
for pid in ['pr-review-toolkit@claude-plugins-official','code-review@claude-plugins-official']:
    print('ok' if pid in installed else 'missing', pid)
"
```

For any plugin reported as **missing**, tell the user:

> To get the full 3-reviewer report, install the missing plugin(s) and reload:
>
> ```
> /plugin install <name>@claude-plugins-official
> /reload-plugins
> ```
>
> Continuing with the reviewer(s) that are available.

Do not block the review — proceed with whichever reviewers are present. The diff review always runs regardless.

## Step 1 — run all three reviews in parallel

Invoke all three of the following simultaneously using the Agent tool (one agent per review), passing the same PR or branch context to each:

1. **Diff review** — run `git diff main...HEAD`, then for each changed file assess:
   - **Correctness** — does the logic do what it claims?
   - **Security** — injection, XSS, auth bypass, secrets-in-code?
   - **Performance** — N+1 queries, blocking calls, memory leaks?
   - **Readability** — confusing names, missing context, overly complex logic?
   - **Tests** — are changes covered? Are existing tests likely to break?

2. **PR Review Toolkit** — invoke the `pr-review-toolkit:review-pr` skill using the Skill tool. Skip if not installed (noted in Step 0).

3. **Official code-review** — invoke the `code-review:code-review` skill using the Skill tool. Skip if not installed (noted in Step 0).

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
