# Filesystem MCP Server

Exposes a sandboxed set of directories to Claude, allowing it to read, write, and navigate your local files without needing shell access.

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

The `/plugin` TUI will prompt for `FILESYSTEM_ALLOWED_DIRS` — enter a space-separated list of absolute paths Claude is allowed to access.

## Configuration

Pass one or more absolute directory paths. Claude will only be able to access files within those directories.

```
FILESYSTEM_ALLOWED_DIRS=/home/user/projects /tmp
```

## Security note

Only allow directories that Claude should be permitted to modify. Avoid exposing system directories such as `/`, `/etc`, or `~/.ssh`.
