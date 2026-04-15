#!/usr/bin/env node
/**
 * Agentic Plugins Marketplace — MCP Server
 *
 * Exposes the plugin registry as MCP tools so Claude can browse and
 * search plugins without leaving the conversation.
 *
 * Tools:
 *   list_plugins    — list all plugins, optionally filtered by category
 *   search_plugins  — full-text search across name, description, tags
 *   get_plugin      — detailed info + README for a single plugin
 *
 * Usage (point MARKETPLACE_DIR at the repo root):
 *   MARKETPLACE_DIR=/path/to/agentic-plugins-marketplace node server.js
 */

import { readFileSync, existsSync } from "fs";
import { join, resolve } from "path";
import { createInterface } from "readline";

const MARKETPLACE_DIR = resolve(
  process.env.MARKETPLACE_DIR ||
    new URL("../../..", import.meta.url).pathname
);

const CATALOG_PATH = join(MARKETPLACE_DIR, ".claude-plugin", "marketplace.json");

// ── catalog helpers ───────────────────────────────────────────────────────────

function loadCatalog() {
  if (!existsSync(CATALOG_PATH)) {
    throw new Error(
      `marketplace.json not found at ${CATALOG_PATH}. ` +
      `Is MARKETPLACE_DIR set to the repo root?`
    );
  }
  return JSON.parse(readFileSync(CATALOG_PATH, "utf8"));
}

function pluginRow(p) {
  return `- [${p.category}] **${p.name}** — ${p.description}`;
}

// ── tool handlers ─────────────────────────────────────────────────────────────

function handleListPlugins({ category } = {}) {
  const catalog = loadCatalog();
  const plugins = category
    ? catalog.plugins.filter((p) => p.category === category)
    : catalog.plugins;

  if (plugins.length === 0) {
    return `No plugins found${category ? ` in category '${category}'` : ""}.`;
  }

  const rows = plugins.map(pluginRow);
  return `${plugins.length} plugin(s) available:\n\n${rows.join("\n")}\n\nInstall any of them with:\n  /plugin install <name>@agentic-plugins-marketplace`;
}

function handleSearchPlugins({ query }) {
  const catalog = loadCatalog();
  const q = query.toLowerCase();
  const matches = catalog.plugins.filter(
    (p) =>
      p.name.toLowerCase().includes(q) ||
      p.description.toLowerCase().includes(q) ||
      (p.tags || []).some((t) => t.toLowerCase().includes(q))
  );

  if (matches.length === 0) {
    return `No plugins matched "${query}".`;
  }

  const rows = matches.map(
    (p) =>
      `- [${p.category}] **${p.name}** — ${p.description}\n  tags: ${(p.tags || []).join(", ")}`
  );
  return (
    `${matches.length} result(s) for "${query}":\n\n${rows.join("\n\n")}\n\n` +
    `Install with:\n  /plugin install <name>@agentic-plugins-marketplace`
  );
}

function handleGetPlugin({ name }) {
  const catalog = loadCatalog();
  const plugin = catalog.plugins.find(
    (p) => p.name.toLowerCase() === name.toLowerCase()
  );

  if (!plugin) {
    return `Plugin "${name}" not found. Use list_plugins to see what's available.`;
  }

  const readmePath = join(MARKETPLACE_DIR, plugin.source.replace(/^\.\//, ""), "README.md");
  const readme = existsSync(readmePath)
    ? readFileSync(readmePath, "utf8")
    : "(no README available)";

  return [
    `## ${plugin.name} (${plugin.category})`,
    `**Version:** ${plugin.version}`,
    `**Tags:** ${(plugin.tags || []).join(", ")}`,
    ``,
    readme,
    ``,
    `**Install:**`,
    `\`\`\``,
    `/plugin install ${plugin.name}@agentic-plugins-marketplace`,
    `\`\`\``,
  ].join("\n");
}

// ── MCP tools definition ──────────────────────────────────────────────────────

const TOOLS = [
  {
    name: "list_plugins",
    description:
      "List all plugins in the marketplace, optionally filtered by category (mcp-server | skill | hook | template).",
    inputSchema: {
      type: "object",
      properties: {
        category: {
          type: "string",
          enum: ["mcp-server", "skill", "hook", "template"],
          description: "Filter by category (omit to list all)",
        },
      },
    },
  },
  {
    name: "search_plugins",
    description:
      "Search plugins by keyword. Matches against name, description, and tags.",
    inputSchema: {
      type: "object",
      required: ["query"],
      properties: {
        query: {
          type: "string",
          description: "Search term",
        },
      },
    },
  },
  {
    name: "get_plugin",
    description:
      "Get detailed information and the full README for a specific plugin.",
    inputSchema: {
      type: "object",
      required: ["name"],
      properties: {
        name: {
          type: "string",
          description: "Plugin name (e.g. github, code-review, audit-log)",
        },
      },
    },
  },
];

// ── MCP stdio transport ───────────────────────────────────────────────────────

const rl = createInterface({ input: process.stdin });

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

rl.on("line", (line) => {
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }

  const { id, method, params } = msg;

  if (method === "initialize") {
    send({
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "marketplace", version: "1.0.0" },
      },
    });
    return;
  }

  if (method === "tools/list") {
    send({ jsonrpc: "2.0", id, result: { tools: TOOLS } });
    return;
  }

  if (method === "tools/call") {
    const { name, arguments: args = {} } = params;
    let text;
    try {
      if (name === "list_plugins")   text = handleListPlugins(args);
      else if (name === "search_plugins") text = handleSearchPlugins(args);
      else if (name === "get_plugin")     text = handleGetPlugin(args);
      else text = `Unknown tool: ${name}`;
    } catch (err) {
      text = `Error: ${err.message}`;
    }
    send({ jsonrpc: "2.0", id, result: { content: [{ type: "text", text }] } });
    return;
  }

  send({ jsonrpc: "2.0", id, result: {} });
});
