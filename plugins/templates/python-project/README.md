# Python Project Template

A `CLAUDE.md` starter template for Python projects that use `uv`, `pytest`, `ruff`, and `mypy`. Gives Claude accurate context about your toolchain, conventions, and guardrails from day one.

## What's included

- Tech stack declaration (Python 3.12+, uv, pytest, ruff, mypy)
- Project structure map
- Canonical dev commands Claude can run
- Coding conventions (type annotations, logging, pathlib, etc.)
- Testing guidelines
- Explicit "do not do" list to prevent common mistakes

## Installation

```
/plugin install python-project@agentic-plugins-marketplace
```

After installation, edit `CLAUDE.md` to fill in your project description and adjust any conventions that differ from the defaults.

## Customisation tips

- Replace the placeholder package name in the project structure section.
- Add project-specific environment variables Claude needs to know about.
- List any external services or APIs so Claude doesn't make unnecessary real calls.
- Add a "Key concepts" section if your domain has non-obvious terminology.
