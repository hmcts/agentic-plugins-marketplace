# Plugin Catalog

## Plugins in this marketplace

Install any plugin with:

```bash
/plugin install <name>@agentic-plugins-marketplace
```

### MCP Servers

| Plugin | Description |
|--------|-------------|
| [marketplace](plugins/mcp-servers/marketplace/) | Browse and search marketplace plugins via Claude tools |
| [filesystem](plugins/mcp-servers/filesystem/) | Sandboxed read/write access to local directories |
| [postgres](plugins/mcp-servers/postgres/) | Read-only SQL queries against PostgreSQL |

> **GitHub** — use the official plugin at [claude.com/plugins/github](https://claude.com/plugins/github) (172k+ installs, maintained by GitHub).
> **Slack** — use the official plugin at [claude.com/plugins/slack](https://claude.com/plugins/slack) (40k+ installs, verified by Slack/Anthropic).

### Skills

| Plugin | Description |
|--------|-------------|
| [accessibility-check](plugins/skills/accessibility-check/) | WCAG 2.1 AA checks — axe-core automation plus manual test requirements |
| [adr-template](plugins/skills/adr-template/) | Architecture Decision Records in a consistent format |
| [bdd-workflow](plugins/skills/bdd-workflow/) | Write acceptance criteria and turn them into Gherkin feature files |
| [code-review](plugins/skills/code-review/) | Structured PR review — security, correctness, performance |
| [conventional-commit](plugins/skills/conventional-commit/) | Conventional Commits message from staged changes |
| [explain-codebase](plugins/skills/explain-codebase/) | Onboarding guide for new developers |
| [marketplace-skill](plugins/skills/marketplace/) | Browse and install plugins conversationally |
| [openspec](plugins/skills/openspec/) | OpenSpec workflow — explore, propose, apply, archive (bundles 4 skills, requires openspec CLI) |
| [review-checklist](plugins/skills/review-checklist/) | Structured pass/fail PR checklist — correctness, tests, security, quality, deps, docs |

### Agents

No agents yet — want to contribute the first one? See [Adding an agent](CONTRIBUTING.md#adding-an-agent).

### Hooks

| Plugin | Event | Description |
|--------|-------|-------------|
| [notify-on-stop](plugins/hooks/notify-on-stop/) | `Stop` | Desktop notification when Claude finishes |
| [audit-log](plugins/hooks/audit-log/) | `PostToolUse` | JSON audit trail of every tool call |

### Templates

| Plugin | Stack | Description |
|--------|-------|-------------|
| [python-project](plugins/templates/python-project/) | Python / uv | `CLAUDE.md` for Python with uv, pytest, ruff, mypy |
| [nodejs-project](plugins/templates/nodejs-project/) | Node.js / TypeScript | `CLAUDE.md` for TypeScript with Vitest and ESLint |

> **A note on plugin overhead** — MCP servers run as persistent subprocesses and expose all their tools to Claude on every turn. `PreToolUse` hooks execute synchronously before every tool call — a slow hook blocks Claude entirely. Skills and agents cost nothing until invoked. Practical rule: enable hooks and skills for the whole team; let individuals opt in to MCP servers based on the services they actively use.

---

## Recommended official plugins

Curated picks from [claude.com/plugins](https://claude.com/plugins). Install any of them via `/plugin`.

> Most of these are hooks or skills with negligible overhead. MCP servers (GitHub, Greptile, Atlassian, the LSPs) launch subprocesses — only install the ones your project actively uses.

### MCP servers — integrations

#### Developer tools

| Plugin | Description |
|--------|-------------|
| [GitHub](https://claude.com/plugins/github) | Official GitHub integration — manage repos, issues, PRs, Actions, and Dependabot alerts directly from Claude |
| [Greptile](https://claude.com/plugins/greptile) | AI-powered codebase search and automated PR reviews integrated with GitHub and GitLab |
| [Pyright LSP](https://claude.com/plugins/pyright-lsp) | Python static type checking — real-time type errors and diagnostics without executing code |
| [TypeScript LSP](https://claude.com/plugins/typescript-lsp) | TS/JS code intelligence — go-to-definition, find references, real-time error checking |

#### Project management

| Plugin | Description |
|--------|-------------|
| [Atlassian](https://claude.com/plugins/atlassian) | Search and manage Jira, Confluence, and Compass via natural language commands |

### Skills

#### Architecture & workflow

| Plugin | Description |
|--------|-------------|
| [Superpowers](https://claude.com/plugins/superpowers) | TDD cycles, Socratic planning, and subagent-driven development with built-in review checkpoints |
| [Claude Code Setup](https://claude.com/plugins/claude-code-setup) | Analyses your project and recommends relevant MCP servers, skills, hooks, and agents |

#### Git & version control

| Plugin | Description |
|--------|-------------|
| [Commit Commands](https://claude.com/plugins/commit-commands) | Generates commit messages matching repo style; full commit → push → PR workflow in one command |

#### Code review

| Plugin | Description |
|--------|-------------|
| [Code Review](https://claude.com/plugins/code-review) | Five parallel review agents with confidence-score filtering to reduce false positives |
| [PR Review Toolkit](https://claude.com/plugins/pr-review-toolkit) | Six specialised agents covering tests, type design, silent failures, docs, and code simplicity |

#### Memory & documentation

| Plugin | Description |
|--------|-------------|
| [Remember](https://claude.com/plugins/remember) | Captures sessions into tiered logs so Claude recalls decisions and file changes across restarts |
| [CLAUDE.md Management](https://claude.com/plugins/claude-md-management) | Audits and proposes updates to CLAUDE.md files to keep project memory accurate |

#### Plugin creation

| Plugin | Best for | Description |
|--------|---------|-------------|
| [Plugin Developer Toolkit](https://claude.com/plugins/plugin-dev) | All types | Guided workflow for building skills, agents, MCP servers, hooks, and commands |
| [Skill Creator](https://claude.com/plugins/skill-creator) | Skills | Create, evaluate, improve, and A/B benchmark Claude Code skills |
| [MCP Server Dev](https://claude.com/plugins/mcp-server-dev) | MCP servers | Three skills covering remote HTTP, MCP app, and bundled stdio server paths |
| [Hookify](https://claude.com/plugins/hookify) | Hooks | Generate hook config files from plain-English rules — no JSON editing required |

### Hooks — automatic

#### Security

| Plugin | Event | Description |
|--------|-------|-------------|
| [Security Guidance](https://claude.com/plugins/security-guidance) | `PreToolUse` | Intercepts Write/Edit operations and warns on command injection, XSS, eval, and unsafe deserialization before changes land |

#### Code quality

| Plugin | Event | Description |
|--------|-------|-------------|
| [Code Simplifier](https://claude.com/plugins/code-simplifier) | automatic | Simplifies recently modified code — reduces nesting, improves naming, removes redundancy while preserving behaviour |

#### Learning & output style

| Plugin | Event | Description |
|--------|-------|-------------|
| [Learning Output Style](https://claude.com/plugins/learning-output-style) | session start | Pauses at architectural decisions and prompts you to contribute key code, turning sessions into hands-on learning |
| [Explanatory Output Style](https://claude.com/plugins/explanatory-output-style) | session start | Adds insight boxes to responses covering codebase-specific patterns and design trade-offs |
