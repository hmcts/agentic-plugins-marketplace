---
name: commit
description: Use when the user asks to commit staged changes, create a conventional commit, or format a commit message. Follows the Conventional Commits specification.
---

Create a git commit following the Conventional Commits specification.

Steps:
1. Run `git diff --staged` to see what is staged. If nothing is staged, run `git status` and ask the user which files to include.
2. Analyse the staged changes and determine:
   - **type**: feat | fix | docs | style | refactor | perf | test | chore | ci | build | revert
   - **scope** (optional): the component or module affected (e.g. `auth`, `api`, `ui`)
   - **breaking**: whether this is a breaking change (BREAKING CHANGE footer required)
   - **description**: short imperative-mood summary (≤72 chars, no trailing period)
   - **body** (optional): longer explanation of *why*, not *what*
3. Format the commit message:
   ```
   <type>[optional scope]: <description>

   [optional body]

   [optional footers]
   ```
4. Show the proposed commit message to the user and ask for confirmation before running `git commit`.
5. Once confirmed, commit with the message. Do not use `--no-verify`.

Examples of well-formed messages:
- `feat(auth): add OAuth2 login via GitHub`
- `fix(api): handle null response from payment provider`
- `refactor!: rename UserService to AccountService` (breaking change)
