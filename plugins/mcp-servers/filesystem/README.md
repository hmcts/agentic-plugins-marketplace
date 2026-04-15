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

```bash
# Quick install via the marketplace installer
./scripts/install.sh mcp-servers/filesystem

# Or add manually — pass the directories you want accessible as extra arguments
claude mcp add filesystem \
  -- npx -y @modelcontextprotocol/server-filesystem /path/to/dir1 /path/to/dir2
```

## Configuration

Pass one or more absolute directory paths as arguments. Claude will only be able to access files within those directories.

```bash
# Example: grant access to your home projects folder
claude mcp add filesystem -- npx -y @modelcontextprotocol/server-filesystem ~/projects
```

## Security note

Only allow directories that Claude should be permitted to modify. Avoid exposing system directories such as `/`, `/etc`, or `~/.ssh`.
