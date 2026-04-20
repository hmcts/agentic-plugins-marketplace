# Conventional Commit Skill

Analyses staged changes and generates a [Conventional Commits](https://www.conventionalcommits.org/)-compliant commit message, then confirms with you before committing.

## Usage

Stage your changes first, then type in Claude Code:

```
/commit
```

Claude will propose a message like:

```
feat(auth): add OAuth2 login via GitHub

Implements the GitHub OAuth flow requested in #142. Users can now
sign in with their GitHub account in addition to email/password.
```

Type `yes` to confirm, or give feedback to refine the message.

## Commit types

| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes only |
| `style` | Formatting, no logic change |
| `refactor` | Code restructure, no behaviour change |
| `perf` | Performance improvement |
| `test` | Adding or updating tests |
| `chore` | Tooling, dependencies, build |
| `ci` | CI/CD configuration |
| `revert` | Reverting a previous commit |

## Installation

```bash
/plugin install conventional-commit@agentic-plugins-marketplace
```
