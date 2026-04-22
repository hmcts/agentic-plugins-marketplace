# Agentic Plugins Marketplace

This repo is a community plugin marketplace for Claude Code. It contains MCP servers, skills, agents, hooks, and project templates that users can install via `/plugin`.

## Choosing the right plugin type

When a user describes something they want to build, suggest the best plugin type before asking which tool to use. Use these signals:

| If the user wants to… | Suggest |
|-----------------------|---------|
| Give Claude a reusable playbook / workflow for a task | **Skill** |
| Let Claude call an external API or service | **MCP Server** |
| Offload a focused task to an isolated sub-agent | **Agent** |
| Run a shell script automatically on a Claude lifecycle event (tool call, stop, etc.) | **Hook** |
| Provide a standard `CLAUDE.md` starting point for a project type | **Template** |

When the intent is ambiguous, ask one clarifying question: "Should this run automatically in the background, be invoked on demand, or call an external service?" That answer usually resolves the type.

## Creating plugins with Claude

Once the plugin type is decided, use the appropriate official Claude tool. Install the tool first if it isn't already present.

| Plugin type | Official tool | Install command |
|-------------|--------------|-----------------|
| **Skill** | Skill Creator | `/plugin install skill-creator@claude-plugins-official` |
| **Agent** | Plugin Developer Toolkit | `/plugin install plugin-dev@claude-plugins-official` |
| **MCP Server** | MCP Server Dev | `/plugin install mcp-server-dev@claude-plugins-official` |
| **Hook** | Hookify | `/plugin install hookify@claude-plugins-official` |
| **Template** | Use `/init` | Built into Claude Code — no install needed |

See [CONTRIBUTING.md#creating-plugins-with-claude](CONTRIBUTING.md#creating-plugins-with-claude) for the full guide, including directory structure, required files, and the testing checklist for each plugin type.

## Migrating plugins from other formats

When a user brings in a plugin from another source — a personal dotfiles repo, a third-party marketplace, a standalone script, or a settings.json snippet — help them migrate it to this repo's structure. Work through the steps below.

### Step 1 — identify the source format

| Source | Likely form |
|--------|-------------|
| Personal Claude config | Entries in `~/.claude/settings.json` under `mcpServers`, `hooks`, `enabledPlugins`, or `skills` |
| Standalone repo | A repo with a `SKILL.md`, `hook.sh`, or server entry point but no `.claude-plugin/` directory |
| Third-party marketplace | A plugin directory with a different manifest format (e.g. `package.json` or `manifest.json` instead of `.claude-plugin/plugin.json`) |
| Raw prompt file | A plain `.md` file with no YAML frontmatter |
| `settings.json` MCP entry | A JSON snippet with an `mcpServers` wrapper |

### Step 1b — evaluate whether the plugin type is still the right fit

Before migrating, check that the original plugin type is actually the best choice for what it does. Plugins from other sources are sometimes the wrong type for their purpose — a prompt-only workflow packaged as an MCP server, a hook that would work better as a skill, or a monolithic skill that should be split into a skill + agent pair.

Use these signals to spot mismatches:

| If the source plugin… | The better type is probably… |
|-----------------------|------------------------------|
| Is an MCP server that contains only a system prompt or instructions, no tools | **Skill** or **Agent** — MCP servers should expose callable tools, not prompts |
| Is a hook that runs a fixed multi-step workflow on every tool call | **Skill** — hooks should be lightweight lifecycle scripts; complex workflows belong in skills |
| Is a skill that calls an external API directly in its prompt body (hardcoded curl, API URL, credentials) | **MCP Server** + **Skill** — extract the API calls into an MCP server, keep the workflow in the skill |
| Is a skill that does a long, isolated task that could run in parallel or needs its own context | **Agent** — offload focused sub-tasks to agents so the main context stays clean |
| Is a large monolithic skill covering multiple unrelated tasks | Split into **multiple skills** — one skill, one job |
| Is a hook that only fires on `Stop` and sends a notification | Fine as a hook — this is the correct use |
| Is a template that contains dynamic logic or workflow steps | **Skill** — templates should be static `CLAUDE.md` files, not executable logic |

If a type mismatch is found, explain the issue and propose the better type before proceeding with the migration. Give the user a concrete reason: "This is packaged as a hook but it runs a 10-step workflow — hooks block Claude until they complete, so this will slow every tool call. A skill would give you the same result without the latency."

### Step 2 — map to this repo's structure

Work out which plugin type the source maps to, then create the correct directory skeleton under `plugins/<type>/<name>/`.

#### MCP server from settings.json

`settings.json` uses an `mcpServers` wrapper. Plugin `.mcp.json` files do **not** — the server name is the top-level key:

```jsonc
// settings.json (native config) — NOT the plugin format
{
  "mcpServers": {
    "my-server": { "command": "npx", "args": ["-y", "my-package"] }
  }
}

// .mcp.json (plugin format) — top-level key, no wrapper
{
  "my-server": { "command": "npx", "args": ["-y", "my-package"] }
}
```

Add a `userConfig` block to `.claude-plugin/plugin.json` for every environment variable the server needs.

#### Standalone SKILL.md

If the file has no YAML frontmatter, add it:

```yaml
---
name: <skill-name>
description: Use when the user asks to [describe intent patterns].
---
```

Then move the file to `plugins/skills/<name>/skills/<trigger>/SKILL.md`.

If the file is a slash command (has an `argument-hint` field or uses `$ARGUMENTS`), place it under `commands/<name>.md` instead.

#### Hook script

Check whether the existing script reads from stdin — hooks in this repo receive the JSON payload via stdin, not environment variables:

```bash
PAYLOAD="$(cat)"  # correct — reads stdin
TOOL=$(echo "$PAYLOAD" | jq -r '.tool_name')
```

If the script reads from env vars instead, update it to use `jq` on `PAYLOAD`. Then create `hooks/hooks.json` using `${CLAUDE_PLUGIN_ROOT}/hook.sh` as the command.

#### Agent / sub-agent prompt

If the source is a system prompt for a sub-agent (Claude Projects system prompt, a plain `.md` file, etc.), wrap it as an agent:

```yaml
---
name: <agent-name>
description: |
  Use this agent when [trigger conditions].

  <example>
  user: "[Example message]"
  assistant: "I'll use the <agent-name> agent to [action]."
  </example>
model: inherit
color: blue
---

[paste existing system prompt here]
```

Place it at `plugins/agents/<name>/agents/<agent-name>.md`.

### Step 3 — fill in missing required files

Every plugin needs these files regardless of source format:

| File | What to put in it |
|------|-------------------|
| `.claude-plugin/plugin.json` | `name`, `version`, `description`, `author`, `license`, `keywords`; add `userConfig` for MCP servers |
| `README.md` | What it does, prerequisites, install command, configuration, usage example |
| `.claude-plugin/marketplace.json` entry | Name, source path, description, version, category, tags |

### Step 4 — security review

Before committing any migrated plugin, follow the [Security — porting from external sources](CONTRIBUTING.md#security--porting-from-external-sources) checklist. This applies even to plugins that look benign — a hook script with `eval`, an MCP server that phones home, or a SKILL.md with hidden Unicode are all real risks.

### Step 5 — test

```bash
# Reload and verify no load errors
/reload-plugins

# For hooks — smoke-test stdin parsing
echo '{"tool_name":"Bash","session_id":"test","tool_input":{"command":"ls"}}' \
  | bash plugins/hooks/<name>/hook.sh

# For MCP servers — confirm tools are registered
/mcp
```

## Testing a plugin after creation or migration

After creating or migrating a plugin, run through the iteration loop below until the plugin installs and loads cleanly. Do not consider the task done until all checks pass.

### Iteration loop

```
create/edit files → review → reload → read errors → fix → repeat
```

Run the code review skill before reloading to catch issues in the files themselves. Only reload once the review is clean — this avoids wasting a reload cycle on a plugin that still has known problems.

**Never stop at the first reload.** Fix every error reported, reload again, and continue until the output is clean.

### Step 1 — run a code review

Before reloading, invoke the `code-review:review` skill on the current branch:

```
review the current branch
```

Fix any **Must fix** findings before proceeding. **Should fix** and **Nit** findings can be addressed before or after the reload at your discretion.

### Step 2 — register the local marketplace source

If the local directory source is not already registered, add it to `.claude/settings.local.json`:

```jsonc
{
  "extraKnownMarketplaces": {
    "agentic-plugins-marketplace": {
      "source": { "source": "directory", "path": "/absolute/path/to/this/repo" }
    }
  }
}
```

Then enable the plugin under test:

```jsonc
{
  "enabledPlugins": {
    "<name>@agentic-plugins-marketplace": true
  }
}
```

### Step 3 — reload and read the result

Run `/reload-plugins` in Claude Code. Read the summary line carefully:

```
Reloaded: 3 plugins · 2 skills · 1 agent · 1 hook · 0 plugin MCP servers
```

If the counts do not include the new plugin, there is a load error — check the **Errors** tab in `/plugin`.

### Step 4 — diagnose and fix errors

Common errors and fixes:

| Error | Likely cause | Fix |
|-------|-------------|-----|
| Plugin not listed after reload | Missing or invalid `.claude-plugin/plugin.json` | Validate JSON; check `name` matches directory name |
| Skill not in skills count | SKILL.md missing YAML frontmatter or wrong file path | Add `---\nname:\ndescription:\n---` frontmatter; check path is `skills/<trigger>/SKILL.md` |
| Agent not in agents count | Agent `.md` missing frontmatter or `name`/`description` fields | Add required frontmatter fields; ensure `<example>` blocks are present in `description` |
| MCP server not in server count | `.mcp.json` has `mcpServers` wrapper (wrong format) | Remove the wrapper; use server name as top-level key |
| MCP server not in server count | Missing `userConfig` for required env var | Add `userConfig` entry in `plugin.json` for each `${VAR}` |
| Hook not firing | `hooks.json` path uses absolute path instead of `${CLAUDE_PLUGIN_ROOT}` | Replace with `${CLAUDE_PLUGIN_ROOT}/hook.sh` |
| Hook firing but erroring | Script reads env vars instead of stdin | Rewrite to `PAYLOAD="$(cat)"` and parse with `jq` |
| `/doctor` reports issues | JSON syntax error in any config file | Run `jq . <file>` to find the syntax error |

### Step 5 — run /doctor

```
/doctor
```

Expected output: `"Claude Code diagnostics dismissed"`. Any other output means there is still a problem — read the report, fix the flagged file, and reload again.

### Step 6 — type-specific smoke tests

Run the appropriate test for the plugin type before marking the task complete:

**Skill**
Ask Claude something that matches the skill's `description` trigger. Confirm the skill fires and produces the expected output. If it doesn't trigger, the `description` is too narrow — broaden the intent patterns.

**Agent**
Ask Claude something that matches the agent's `description`. Confirm the agent is spawned (Claude will say "I'll use the `<name>` agent…"). If it doesn't spawn, add more `<example>` blocks to the frontmatter `description`.

**MCP server**
```
/mcp
```
Confirm the server name and its tools appear in the list. Then ask Claude to use one of the tools and verify it returns a real response.

**Hook**
Smoke-test stdin parsing directly:
```bash
echo '{"tool_name":"Bash","session_id":"test","tool_input":{"command":"ls"}}' \
  | bash plugins/hooks/<name>/hook.sh
```
Exit code must be 0. Then trigger the hook's lifecycle event in a real Claude session and verify the expected side effect (log written, notification sent, etc.).

**Template**
Run the slash command that copies `CLAUDE.md` into place:
```
/use-<name>-template
```
Confirm `CLAUDE.md` appears in the current directory with the correct content.

### Step 7 — done criteria

The plugin is ready to commit when all of the following are true:

- [ ] `code-review:review` reports no Must fix findings
- [ ] `/reload-plugins` summary line counts include the new plugin
- [ ] `/doctor` returns clean
- [ ] Type-specific smoke test passes
- [ ] No hardcoded secrets or credentials in any file

## Plugin directory structure

Plugins live under `plugins/<type>/<name>/`. Each plugin must have a `.claude-plugin/plugin.json` manifest. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full layout and required fields.
