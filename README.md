# unreal-blueprint-mcp

Blueprint graph reader for Unreal Engine AI development via [Model Context Protocol](https://modelcontextprotocol.io/).

Gives AI assistants structural access to Blueprint graph data — nodes, pins, connections, execution flow, and variables — through a companion C++ plugin that serializes graph data to JSON.

## Why?

AI assistants can read C++ but are blind to Blueprint logic — the visual scripting that drives most UE gameplay code. This server exposes Blueprint graphs as structured data so AI agents can understand execution flow, trace connections, and reason about Blueprint architecture alongside C++ code.

**Complements** (does not replace):
- [unreal-source-mcp](https://github.com/tumourlove/unreal-source-mcp) — Engine-level source intelligence (full UE C++ and HLSL)
- [unreal-project-mcp](https://github.com/tumourlove/unreal-project-mcp) — Project-level source intelligence (your C++ code)
- [unreal-editor-mcp](https://github.com/tumourlove/unreal-editor-mcp) — Build diagnostics and editor log tools (Live Coding, error parsing, log search)
- [unreal-material-mcp](https://github.com/tumourlove/unreal-material-mcp) — Material graph intelligence and editing (expressions, connections, parameters, instances, graph manipulation)
- [unreal-config-mcp](https://github.com/tumourlove/unreal-config-mcp) — Config/INI intelligence (resolve inheritance chains, search settings, diff from defaults, explain CVars)
- [unreal-animation-mcp](https://github.com/tumourlove/unreal-animation-mcp) — Animation data inspector and editor (sequences, montages, blend spaces, ABPs, skeletons, 62 tools)
- [unreal-api-mcp](https://github.com/nicobailon/unreal-api-mcp) by [Nico Bailon](https://github.com/nicobailon) — API surface lookup (signatures, #include paths, deprecation warnings)

Together these servers give AI agents full-stack UE understanding: engine internals, API surface, your project code, build/runtime feedback, Blueprint graph data, config/INI intelligence, material graph inspection + editing, and animation data inspection + editing.

## Prerequisites

- **BlueprintReader plugin** installed in your UE project ([unreal-blueprint-reader](https://github.com/tumourlove/unreal-blueprint-reader))
- **Python Remote Execution** enabled in the editor: **Edit > Project Settings** > search "remote" > under **Python Remote Execution**, check **"Enable Remote Execution?"**

## Quick Start

### Install from GitHub

```bash
uvx --from git+https://github.com/tumourlove/unreal-blueprint-mcp.git unreal-blueprint-mcp
```

### Claude Code Configuration

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "unreal-blueprint": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/tumourlove/unreal-blueprint-mcp.git", "unreal-blueprint-mcp"],
      "env": {
        "UE_PROJECT_PATH": "D:/Unreal Projects/MyProject"
      }
    }
  }
}
```

Or run from local source during development:

```json
{
  "mcpServers": {
    "unreal-blueprint": {
      "command": "uv",
      "args": ["run", "--directory", "C:/Projects/unreal-blueprint-mcp", "unreal-blueprint-mcp"],
      "env": {
        "UE_PROJECT_PATH": "D:/Unreal Projects/MyProject"
      }
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `get_blueprint_graphs` | List all graphs (event graphs, functions, macros) in a Blueprint |
| `get_blueprint_graph` | Get full graph data: all nodes with pins, connections, defaults |
| `get_blueprint_variables` | Get all variables with types, defaults, and property flags |
| `get_blueprint_flow` | Get linearized execution flow from an entry point |
| `search_blueprint_nodes` | Search nodes by title, class, or function name |

## Asset Path Format

Tools accept Unreal asset paths (no file extension):

| Location | Format | Example |
|----------|--------|---------|
| Project `Content/` | `/Game/Path/To/Blueprint` | `/Game/Blueprints/BP_Hero` |
| Project `Plugins/` | `/PluginName/PluginName/Path/To/Asset` | `/InventorySystemX/InventorySystemX/Components/AC_HUD` |
| Engine plugins | `/PluginName/Path/To/Asset` | `/EnginePlugin/Blueprints/BP_Example` |

Marketplace packs copied into your project's `Content/` folder use the `/Game/` prefix like any other project content.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `UE_PROJECT_PATH` | `""` | Path to your Unreal project directory |
| `UE_EDITOR_PYTHON_PORT` | `6776` | TCP port for editor Python bridge commands |
| `UE_MULTICAST_GROUP` | `239.0.0.1` | UDP multicast group for editor discovery |
| `UE_MULTICAST_PORT` | `6766` | UDP multicast port for editor discovery |
| `UE_MULTICAST_BIND` | `127.0.0.1` | Local interface to bind multicast listener |

## How It Works

1. **Editor Discovery** — Discovers the running UE editor via UDP multicast (the same protocol as UE's built-in `remote_execution.py`). Opens a TCP command channel to execute Python in the editor.

2. **Plugin Bridge** — Sends Python commands to the editor that call `BlueprintReaderLibrary` static functions from the companion C++ plugin. The plugin serializes Blueprint graph data to JSON strings.

3. **Serving** — FastMCP server exposes 5 tools over stdio. Claude Code manages the server lifecycle automatically.

**No database, no indexing** — all data comes live from the running editor. The server is stateless; graphs are read on demand from whatever Blueprints are loaded.

## Adding to Your Project's CLAUDE.md

```markdown
## Blueprint Graph Reading (unreal-blueprint MCP)

Use `unreal-blueprint` MCP tools to read Blueprint graph data — nodes, pins,
connections, execution flow, and variables. Requires **BlueprintReader** plugin
and **Python Remote Execution** enabled in editor.

| Tool | When |
|------|------|
| `get_blueprint_graphs` | Discover what graphs exist in a Blueprint |
| `get_blueprint_graph` | Read full node/pin/connection data for a graph |
| `get_blueprint_variables` | Get all variables with types, defaults, flags |
| `get_blueprint_flow` | Understand execution order from an entry point |
| `search_blueprint_nodes` | Find specific nodes by name/class/function |

**Asset paths (no extension):**
- Project `Content/`: `/Game/Path/To/Blueprint` (includes marketplace packs copied into Content/)
- Project `Plugins/`: `/PluginName/PluginName/Path/To/Asset`
- Engine plugins: `/PluginName/Path/To/Asset`
```

## Development

```bash
# Clone and install
git clone https://github.com/tumourlove/unreal-blueprint-mcp.git
cd unreal-blueprint-mcp
uv sync

# Run tests
uv run pytest -v

# Run server locally
uv run unreal-blueprint-mcp
```

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Unreal Engine 5.x with Python plugin and Remote Execution enabled
- [BlueprintReader](https://github.com/tumourlove/unreal-blueprint-reader) C++ plugin

## License

MIT
