Review the code changes on the current branch against the main branch. Follow these steps:

1. Run `git diff main...HEAD` to see all changes.
2. For each changed file, assess:
   - **Correctness** — does the logic do what it claims?
   - **Security** — any injection, XSS, auth bypass, or secrets-in-code issues?
   - **Performance** — obvious N+1 queries, blocking calls, or memory leaks?
   - **Readability** — confusing names, missing context, overly complex logic?
   - **Tests** — are the changes covered? Are existing tests likely to break?
3. Summarise findings as:
   - **Must fix** — blockers that should prevent merge
   - **Should fix** — non-blocking improvements worth addressing
   - **Nit** — style or minor quality observations (low priority)
4. If there are no issues in a category, state "None found."
5. End with an overall recommendation: **Approve**, **Request changes**, or **Needs discussion**.

Keep the review concise and actionable. Reference specific file paths and line numbers where relevant.
