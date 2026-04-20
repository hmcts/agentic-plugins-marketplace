# Skill Plugins

Skills are prompt templates that give Claude a structured playbook for a task, triggered by a `/slash-command`.

## Available skills

| Plugin | Trigger | Description |
|--------|---------|-------------|
| [marketplace](./marketplace/) | `/marketplace` | Browse and install plugins conversationally |
| [code-review](./code-review/) | `/review` | Structured PR review — security, correctness, performance |
| [conventional-commit](./conventional-commit/) | `/commit` | Conventional Commits message from staged changes |
| [explain-codebase](./explain-codebase/) | `/explain` | Onboarding guide for new developers |

## Installation

```bash
/plugin install <name>@agentic-plugins-marketplace
```

## Adding a new skill

See [CONTRIBUTING.md](../../CONTRIBUTING.md#adding-a-skill).
