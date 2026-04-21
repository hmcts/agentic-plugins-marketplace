---
name: explain-codebase
description: Use when the user asks to explain the codebase, onboard a new developer, give an overview of the project, or describe the architecture and structure.
---

Give a clear, layered explanation of this codebase suitable for a developer who is new to the project.

Steps:
1. Read `README.md` and any `CLAUDE.md` files at the root and in subdirectories.
2. Identify the primary language(s) and framework(s) in use.
3. Map out the top-level directory structure and explain the purpose of each major directory.
4. Trace the main execution path or request lifecycle from entry point to output.
5. Highlight the key abstractions, data models, and interfaces a new developer needs to understand first.
6. Note any non-obvious conventions, environment requirements, or gotchas (e.g. monorepo tooling, code generation, required env vars).
7. Suggest which files to read first for a developer wanting to make their first contribution.

Format the response as:
- **Tech stack** — one-line summary
- **Directory map** — annotated tree (max two levels deep)
- **Request / execution lifecycle** — numbered steps
- **Key abstractions** — bulleted list with brief descriptions
- **Gotchas** — anything a new developer would wish they'd known earlier
- **Where to start** — 3–5 recommended files in order
