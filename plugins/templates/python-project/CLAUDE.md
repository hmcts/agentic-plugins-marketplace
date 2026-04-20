# Project instructions for Claude

## Overview

<!-- Replace this section with a one-paragraph description of your project. -->

This is a Python project. Follow the conventions below when making changes.

## Tech stack

- **Language**: Python 3.12+
- **Package manager**: uv (`uv run`, `uv add`, `uv sync`)
- **Testing**: pytest
- **Linting / formatting**: ruff
- **Type checking**: mypy (strict mode)

## Project structure

```
src/
  <package_name>/   ← main source package
    __init__.py
    ...
tests/
  unit/             ← fast, no I/O
  integration/      ← may hit real services; require explicit opt-in
pyproject.toml
```

## Development commands

```bash
uv sync                          # install dependencies
uv run pytest tests/unit         # run unit tests
uv run pytest tests/integration  # run integration tests (needs live services)
uv run ruff check .              # lint
uv run ruff format .             # format
uv run mypy src                  # type check
```

## Conventions

- Follow PEP 8. Ruff enforces line length ≤ 88 characters.
- Use type annotations on all public functions and class attributes.
- Prefer `pathlib.Path` over `os.path`.
- Never use `print()` for runtime output; use the `logging` module.
- Do not commit secrets or hardcoded credentials. Use environment variables.

## Testing guidelines

- All new behaviour must have a corresponding unit test.
- Tests must be deterministic — mock external I/O, clocks, and randomness.
- Name test functions `test_<what>_<expected_outcome>`.
- Keep each test focused on a single assertion or behaviour.

## What Claude should NOT do

- Do not run integration tests unless explicitly asked; they require external services.
- Do not modify `pyproject.toml` without discussing dependency changes first.
- Do not commit directly to `main`; create a branch and open a PR.
