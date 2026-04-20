# Template Plugins

Templates are pre-written `CLAUDE.md` files for common project types. Claude Code reads `CLAUDE.md` automatically at the start of every session, so the conventions and commands in it apply without you having to repeat them.

## Available templates

| Plugin | Stack | Description |
|--------|-------|-------------|
| [python-project](./python-project/) | Python / uv | `CLAUDE.md` for Python with uv, pytest, ruff, mypy |
| [nodejs-project](./nodejs-project/) | Node.js / TypeScript | `CLAUDE.md` for TypeScript with Vitest and ESLint |

## Installation

```bash
/plugin install <name>@agentic-plugins-marketplace
```

After installation, open the `CLAUDE.md` that was added to your project root and fill in the placeholder sections specific to your project.

## Adding a new template

See [CONTRIBUTING.md](../../CONTRIBUTING.md#adding-a-template).
