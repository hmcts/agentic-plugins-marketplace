# Filesystem MCP Server

Exposes a sandboxed directory to Claude, allowing it to read, write, and navigate your local files without needing shell access.

## Tools provided

| Tool | Description |
|------|-------------|
| `read_file` | Read the contents of a file |
| `read_multiple_files` | Read several files at once |
| `write_file` | Create or overwrite a file |
| `edit_file` | Apply targeted string replacements to a file |
| `create_directory` | Make a new directory |
| `list_directory` | List directory contents |
| `directory_tree` | Recursive tree view of a directory |
| `move_file` | Move or rename a file |
| `search_files` | Find files by name pattern |
| `get_file_info` | Stat a file (size, timestamps, etc.) |
| `list_allowed_directories` | Show which directories are accessible |

## Prerequisites

- Node.js 18+ (for `npx`)

## Installation

```
/plugin install filesystem@agentic-plugins-marketplace
```

The `/plugin` TUI will prompt for `ALLOWED_DIRECTORY` — enter the absolute path to the single directory Claude is allowed to access (e.g. `/Users/you/projects/my-app`).

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `ALLOWED_DIRECTORY` | Yes | Absolute path to the directory Claude may read and write |

## Security note

Set `ALLOWED_DIRECTORY` to the specific project directory you want Claude to work in. **Do not set it to your home directory (`~`)** — doing so would expose ssh keys, browser profiles, credentials files, and every other project on your machine.
