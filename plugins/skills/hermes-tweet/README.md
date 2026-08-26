# Hermes Tweet Skill

Guides Claude through Hermes Tweet setup and approval-gated X/Twitter workflows in Hermes Agent.

Hermes Tweet is a Hermes Agent plugin for X/Twitter search, reading, exploration, and optional account actions through the Xquik API.

## Usage

After installation, type in Claude Code:

```
/hermes-tweet
```

Or invoke it in natural language:

```
Use Hermes Tweet to research posts about this launch.
```

## What it guides

- Install or verify the upstream Hermes Tweet plugin for Hermes Agent
- Configure `XQUIK_API_KEY` without exposing the value
- Keep reads and exploration available by default
- Require explicit approval before any account-changing action
- Enable write-like actions only when `HERMES_TWEET_ENABLE_ACTIONS=true`

## Prerequisites

- Hermes Agent installed
- Hermes Tweet installed from [Xquik-dev/hermes-tweet](https://github.com/Xquik-dev/hermes-tweet) or [PyPI](https://pypi.org/project/hermes-tweet/)
- `XQUIK_API_KEY` configured in the Hermes runtime environment

## Installation

```
/plugin install hermes-tweet@agentic-plugins-marketplace
```
