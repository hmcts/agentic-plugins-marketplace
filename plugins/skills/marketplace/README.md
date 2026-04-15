# Marketplace Skill

The meta-plugin. Once installed, `/marketplace` turns Claude into an interactive plugin browser — it can list available plugins, search by keyword or type, explain what each one does, and run the installer on your behalf.

## Usage

```
/marketplace
```

Then just talk to Claude naturally:

```
> /marketplace
> show me all MCP servers
> anything for Slack?
> install the github plugin
> tell me about the audit-log hook before I add it
```

Claude will show a dry-run of what the installer will do and ask for confirmation before making any changes.

## Prerequisites

The marketplace repository must be cloned locally. Claude will prompt you to clone it if it is not found:

```bash
git clone https://github.com/your-org/agentic-plugins-marketplace.git
```

## Installation

This skill is the only plugin you need to bootstrap the rest. Install it once with a one-liner — no cloning required:

```bash
mkdir -p ~/.claude/skills && curl -fsSL \
  https://raw.githubusercontent.com/your-org/agentic-plugins-marketplace/main/plugins/skills/marketplace/skill.md \
  -o ~/.claude/skills/marketplace.md
```

After that, `/marketplace` is available in every Claude Code session.

## What Claude can do via this skill

| Command (natural language) | What happens |
|---------------------------|-------------|
| "list all plugins" | Reads `registry.json` and renders a full table |
| "show skills" / "show hooks" | Filters by plugin type |
| "find postgres" | Searches name, description, and tags |
| "tell me about github" | Shows the plugin README summary |
| "install code-review" | Runs `--dry-run`, asks for confirmation, then installs |
| "install python template to ./my-project" | Installs a template to a specific directory |
