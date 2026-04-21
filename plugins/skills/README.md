# Skill Plugins

Skills are prompt templates that give Claude a structured playbook for a task. They are **auto-triggered** — Claude detects from each skill's description when to invoke it, rather than the user typing a slash command.

## Available skills

| Plugin | Description |
|--------|-------------|
| [marketplace-skill](./marketplace-skill/) | Browse and install plugins conversationally |
| [code-review](./code-review/) | Structured PR review — security, correctness, performance |
| [conventional-commit](./conventional-commit/) | Conventional Commits message from staged changes |
| [explain-codebase](./explain-codebase/) | Onboarding guide for new developers |

## Installation

```bash
/plugin install <name>@agentic-plugins-marketplace
```

## Adding a new skill

See [CONTRIBUTING.md](../../CONTRIBUTING.md#adding-a-skill).
