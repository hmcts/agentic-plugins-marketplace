#!/usr/bin/env node
/**
 * Agentic Plugins Marketplace — MCP Server
 *
 * Exposes the plugin registry as MCP tools so Claude can browse,
 * search, and install plugins without leaving the conversation.
 *
 * Tools:
 *   list_plugins    — list all plugins, optionally filtered by type
 *   search_plugins  — full-text search across name, description, tags
 *   get_plugin      — detailed info on a single plugin
 *   install_plugin  — run the installer (dry-run by default)
 *
 * Usage:
 *   MARKETPLACE_DIR=/path/to/marketplace node server.js
 */

import { readFileSync, existsSync } from "fs";
import { join, resolve } from "path";
import { execSync } from "child_process";
import { createInterface } from "readline";

const MARKETPLACE_DIR = resolve(
  process.env.MARKETPLACE_DIR ||
    new URL("../../..", import.meta.url).pathname
);

const REGISTRY_PATH = join(MARKETPLACE_DIR, "registry.json");
const INSTALLER_PATH = join(MARKETPLACE_DIR, "scripts", "install.sh");

// ── registry helpers ──────────────────────────────────────────────────────────

function loadRegistry() {
  if (!existsSync(REGISTRY_PATH)) {
    throw new Error(`registry.json not found at ${REGISTRY_PATH}`);
  }
  return JSON.parse(readFileSync(REGISTRY_PATH, "utf8"));
}

function formatPlugin(p) {
  return {
    name: p.name,
    type: p.type,
    version: p.version,
    description: p.description,
    tags: p.tags,
    author: p.author,
    path: p.path,
  };
}

// ── MCP stdio transport ───────────────────────────────────────────────────────

const TOOLS = [
  {
    name: "list_plugins",
    description:
      "List all plugins in the marketplace, optionally filtered by type (mcp-server | skill | hook | template).",
    inputSchema: {
      type: "object",
      properties: {
        type: {
          type: "string",
          enum: ["mcp-server", "skill", "hook", "template"],
          description: "Filter by plugin type (omit to list all)",
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
      "Get detailed information about a specific plugin, including its README.",
    inputSchema: {
      type: "object",
      required: ["name"],
      properties: {
        name: {
          type: "string",
          description: "Plugin name (e.g. github, code-review)",
        },
      },
    },
  },
  {
    name: "install_plugin",
    description:
      "Install a plugin. Runs a dry-run by default — set dry_run=false to actually install.",
    inputSchema: {
      type: "object",
      required: ["name"],
      properties: {
        name: {
          type: "string",
          description: "Plugin name (e.g. github, code-review)",
        },
        dry_run: {
          type: "boolean",
          description: "Preview the install without making changes (default: true)",
          default: true,
        },
        target: {
          type: "string",
          description:
            "For template plugins: target directory path (defaults to current working directory)",
        },
      },
    },
  },
];

function handleListPlugins({ type } = {}) {
  const registry = loadRegistry();
  const plugins = type
    ? registry.plugins.filter((p) => p.type === type)
    : registry.plugins;

  if (plugins.length === 0) {
    return `No plugins found${type ? ` of type '${type}'` : ""}.`;
  }

  const rows = plugins.map(
    (p) => `- [${p.type}] **${p.name}** — ${p.description}`
  );
  return `Found ${plugins.length} plugin(s):\n\n${rows.join("\n")}`;
}

function handleSearchPlugins({ query }) {
  const registry = loadRegistry();
  const q = query.toLowerCase();
  const matches = registry.plugins.filter(
    (p) =>
      p.name.toLowerCase().includes(q) ||
      p.description.toLowerCase().includes(q) ||
      (p.tags || []).some((t) => t.toLowerCase().includes(q))
  );

  if (matches.length === 0) {
    return `No plugins matched "${query}".`;
  }

  const rows = matches.map(
    (p) => `- [${p.type}] **${p.name}** — ${p.description}\n  tags: ${(p.tags || []).join(", ")}`
  );
  return `Found ${matches.length} result(s) for "${query}":\n\n${rows.join("\n\n")}`;
}

function handleGetPlugin({ name }) {
  const registry = loadRegistry();
  const plugin = registry.plugins.find(
    (p) => p.name.toLowerCase() === name.toLowerCase()
  );

  if (!plugin) {
    return `Plugin "${name}" not found. Use list_plugins to see available plugins.`;
  }

  const readmePath = join(MARKETPLACE_DIR, plugin.path, "README.md");
  const readme = existsSync(readmePath)
    ? readFileSync(readmePath, "utf8")
    : "(no README available)";

  return [
    `## ${plugin.name} (${plugin.type})`,
    `**Version:** ${plugin.version}`,
    `**Author:** ${plugin.author}`,
    `**Tags:** ${(plugin.tags || []).join(", ")}`,
    "",
    readme,
  ].join("\n");
}

function handleInstallPlugin({ name, dry_run = true, target }) {
  const registry = loadRegistry();
  const plugin = registry.plugins.find(
    (p) => p.name.toLowerCase() === name.toLowerCase()
  );

  if (!plugin) {
    return `Plugin "${name}" not found. Use list_plugins to see available plugins.`;
  }

  if (!existsSync(INSTALLER_PATH)) {
    return `Installer not found at ${INSTALLER_PATH}. Is MARKETPLACE_DIR set correctly?`;
  }

  const args = [plugin.path];
  if (dry_run) args.push("--dry-run");
  if (target) args.push(`--target "${target}"`);

  const cmd = `bash "${INSTALLER_PATH}" ${args.join(" ")}`;

  try {
    const output = execSync(cmd, {
      cwd: MARKETPLACE_DIR,
      env: { ...process.env },
      encoding: "utf8",
      stdio: ["pipe", "pipe", "pipe"],
    });
    const prefix = dry_run
      ? "Dry-run output (no changes made):\n\n"
      : "Installation output:\n\n";
    return prefix + output;
  } catch (err) {
    return `Install failed:\n${err.stderr || err.message}`;
  }
}

// ── MCP protocol loop ─────────────────────────────────────────────────────────

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
      if (name === "list_plugins") text = handleListPlugins(args);
      else if (name === "search_plugins") text = handleSearchPlugins(args);
      else if (name === "get_plugin") text = handleGetPlugin(args);
      else if (name === "install_plugin") text = handleInstallPlugin(args);
      else text = `Unknown tool: ${name}`;
    } catch (err) {
      text = `Error: ${err.message}`;
    }

    send({
      jsonrpc: "2.0",
      id,
      result: { content: [{ type: "text", text }] },
    });
    return;
  }

  // Unhandled method — return empty result
  send({ jsonrpc: "2.0", id, result: {} });
});
