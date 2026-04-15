# Skill Plugins

Skills are reusable prompt templates that give Claude a structured playbook for common engineering tasks. They are invoked with a `/slash-command` inside Claude Code.

## Available skills

| Plugin | Trigger | Description |
|--------|---------|-------------|
| [marketplace](./marketplace/) | `/marketplace` | Browse and install plugins conversationally |
| [code-review](./code-review/) | `/review` | Structured PR review — security, correctness, performance |
| [conventional-commit](./conventional-commit/) | `/commit` | Generate Conventional Commits messages from staged changes |
| [explain-codebase](./explain-codebase/) | `/explain` | Onboarding guide for a new developer |

## How skills work

A skill is a Markdown file placed in `~/.claude/skills/`. When you type the trigger command, Claude Code loads the skill as context for that turn — effectively giving Claude a structured prompt to follow.

```
~/.claude/skills/
└── review.md       ← /review trigger reads this file
```

## Adding a new skill

See [CONTRIBUTING.md](../../../CONTRIBUTING.md#adding-a-skill).
