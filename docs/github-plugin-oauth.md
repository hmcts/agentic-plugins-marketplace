# GitHub plugin — OAuth and PAT limitations

## The problem

The official GitHub plugin (`github@claude-plugins-official`) authenticates by injecting a bearer token into the `Authorization` header of every HTTP MCP request:

```json
{
  "github": {
    "type": "http",
    "url": "https://api.githubcopilot.com/mcp/",
    "headers": {
      "Authorization": "Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}"
    }
  }
}
```

The `${GITHUB_PERSONAL_ACCESS_TOKEN}` variable must be set in your shell environment before Claude Code starts. There is no `userConfig` in `plugin.json` to prompt for it at install time.

## Why Claude Code's native OAuth flow doesn't work

Claude Code supports OAuth for HTTP MCP servers via **dynamic client registration** (RFC 7591): it automatically registers itself as an OAuth client with the authorization server on first use.

GitHub's OAuth server (`https://github.com/login/oauth`) does not support dynamic client registration. Attempting the OAuth flow from `/mcp` → Authenticate produces:

```
Error: SDK auth failed: Incompatible auth server: does not support dynamic client registration
```

Removing the `Authorization` header from `.mcp.json` to trigger a clean 401 does not help — Claude Code discovers the `resource_metadata` URL, finds GitHub's auth server, and hits the same dead end.

## Why the `gh` CLI token doesn't work

The `gh` CLI stores an OAuth token (`gho_…`) issued to the `gh` app. That token is valid for `api.github.com` but is rejected by `api.githubcopilot.com/mcp/` with:

```
www-authenticate: Bearer error="invalid_token"
```

The Copilot MCP endpoint requires a token issued by the GitHub Copilot OAuth app specifically, not the `gh` CLI app.

## What does work

| Option | Works? | Notes |
|--------|--------|-------|
| Classic PAT | Yes | Set `GITHUB_PERSONAL_ACCESS_TOKEN` in shell |
| Fine-grained PAT | Yes | Scopeable to specific repos and permissions |
| `gh` CLI OAuth token | No | Wrong OAuth app — rejected by Copilot MCP endpoint |
| Claude Code native OAuth | No | GitHub doesn't support dynamic client registration |
| Org-created OAuth App | No | Plugin would need to be rewritten to use a specific `client_id` — only GitHub/Anthropic can do that |

## Recommended fix for orgs that block classic PATs

Ask your org security team for a **fine-grained PAT** scoped to the repos and permissions you need. Fine-grained PATs expire and are repo-scoped, so many orgs that ban classic PATs still allow them.

Once you have the token:

```bash
# Add to ~/.zshrc
export GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_…
```

Then restart Claude Code and run `/reload-plugins`.

## Long-term fix

This requires GitHub or Anthropic to update the official plugin to use a pre-registered OAuth App (with a baked-in `client_id`), so Claude Code can redirect users through the standard `github.com/login/oauth/authorize` flow without dynamic registration. Track progress on the [GitHub MCP Server repo](https://github.com/github/github-mcp-server).
