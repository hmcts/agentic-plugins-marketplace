# Slack MCP Server

Lets Claude interact with your Slack workspace — read channel history, list channels, and post messages or replies.

## Tools provided

| Tool | Description |
|------|-------------|
| `slack_list_channels` | List public channels in the workspace |
| `slack_get_channel_history` | Fetch recent messages from a channel |
| `slack_get_thread_replies` | Fetch replies in a message thread |
| `slack_post_message` | Send a message to a channel |
| `slack_reply_to_thread` | Reply within an existing thread |
| `slack_search_messages` | Full-text search across messages |
| `slack_get_users` | List workspace members |

## Prerequisites

- Node.js 18+
- A Slack app with a Bot Token and the required OAuth scopes

### Required Slack OAuth scopes

```
channels:history    channels:read      groups:history
groups:read         im:history         im:read
mpim:history        mpim:read          users:read
chat:write
```

## Installation

```
/plugin install slack@agentic-plugins-marketplace
```

The `/plugin` TUI will prompt for `SLACK_BOT_TOKEN` (stored in OS keychain) and `SLACK_TEAM_ID`.

## Configuration

```bash
export SLACK_BOT_TOKEN=xoxb-your-bot-token
export SLACK_TEAM_ID=T0123456789   # Found in workspace settings
```

## Usage example

> "Summarise the last 50 messages in #engineering and highlight any open action items."

> "Post a standup update to #daily-standup."
