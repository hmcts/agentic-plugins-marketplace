# Explain Codebase Skill

Produces a structured onboarding guide for any repository — tech stack, directory map, request lifecycle, key abstractions, and gotchas — tailored for a developer making their first contribution.

## Usage

Open a project in Claude Code and type:

```
/explain
```

## Output sections

| Section | What you get |
|---------|-------------|
| Tech stack | One-line language/framework summary |
| Directory map | Annotated two-level tree |
| Execution lifecycle | Step-by-step request/startup flow |
| Key abstractions | The 5–10 concepts a new dev must understand |
| Gotchas | Non-obvious conventions, required setup steps |
| Where to start | 3–5 files to read first |

## Installation

```bash
./scripts/install.sh skills/explain-codebase
```
