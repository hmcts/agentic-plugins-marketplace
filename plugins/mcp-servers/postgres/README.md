# PostgreSQL MCP Server

Gives Claude read-only access to a PostgreSQL database. Claude can explore schemas, describe tables, and run `SELECT` queries to help you analyse data or debug issues.

## Tools provided

| Tool | Description |
|------|-------------|
| `query` | Execute a read-only SQL query and return results |
| `list_schemas` | List all schemas in the database |
| `list_tables` | List tables within a schema |
| `describe_table` | Return column definitions, types, and constraints for a table |

## Prerequisites

- Node.js 18+ (for `npx`)
- A PostgreSQL connection string

## Installation

```
/plugin install postgres@agentic-plugins-marketplace
```

The `/plugin` TUI will prompt for `DATABASE_URL` and store it in your OS keychain.

## Configuration

```bash
export DATABASE_URL=postgres://username:password@host:5432/database_name
```

## Usage example

> "Show me the top 10 users by number of orders placed in the last 30 days."

> "Describe the `payments` table and explain any foreign key relationships."

## Security note

The server enforces read-only access — `INSERT`, `UPDATE`, `DELETE`, and DDL statements are rejected. Use a dedicated read-only database user for extra safety.
