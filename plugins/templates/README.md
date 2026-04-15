# Template Plugins

Templates are pre-written `CLAUDE.md` files for common project types. A `CLAUDE.md` at the root of a project gives Claude persistent context about the codebase — its tech stack, conventions, commands, and guardrails — so you don't have to repeat yourself every session.

## Available templates

| Plugin | Stack | Description |
|--------|-------|-------------|
| [python-project](./python-project/) | Python / uv / pytest / ruff | Python projects with uv and strict typing |
| [nodejs-project](./nodejs-project/) | Node.js / TypeScript / Vitest | TypeScript projects with Vitest and ESLint |

## How CLAUDE.md works

Claude Code automatically reads `CLAUDE.md` (and any nested `CLAUDE.md` files in subdirectories) at the start of every session. The contents become part of Claude's system prompt, so every instruction in the file applies without the user having to re-state it.

A good `CLAUDE.md` typically covers:
- Project overview and tech stack
- How to run tests, linting, and the build
- Coding conventions and style rules
- What Claude should *not* do (guardrails)

## Adding a new template

See [CONTRIBUTING.md](../../../CONTRIBUTING.md#adding-a-template).
