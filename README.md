# unreal-blueprint-mcp

Blueprint graph reader for Unreal Engine AI development via [Model Context Protocol](https://modelcontextprotocol.io/).

Gives AI assistants structural access to Blueprint graph data — nodes, pins, connections, execution flow, and variables — through a companion C++ plugin that serializes graph data to JSON.

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

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `UE_PROJECT_PATH` | `""` | Path to your Unreal project directory |
| `UE_EDITOR_PYTHON_PORT` | `6776` | TCP port for editor Python bridge commands |
| `UE_MULTICAST_GROUP` | `239.0.0.1` | UDP multicast group for editor discovery |
| `UE_MULTICAST_PORT` | `6766` | UDP multicast port for editor discovery |
| `UE_MULTICAST_BIND` | `127.0.0.1` | Local interface to bind multicast listener |

## Complements

**Does not replace** — works alongside:
- [unreal-source-mcp](https://github.com/tumourlove/unreal-source-mcp) — Engine-level source intelligence (full UE C++ and HLSL)
- [unreal-project-mcp](https://github.com/tumourlove/unreal-project-mcp) — Project-level source intelligence (your C++ code)
- [unreal-editor-mcp](https://github.com/tumourlove/unreal-editor-mcp) — Build diagnostics and editor log tools
- [unreal-api-mcp](https://github.com/nicobailon/unreal-api-mcp) by [Nico Bailon](https://github.com/nicobailon) — API surface lookup

Together these servers give AI agents full-stack UE understanding: engine internals, API surface, project code, build feedback, and now Blueprint graph data.

## Adding to Your Project's CLAUDE.md

```markdown
## Blueprint Graph Reading (via unreal-blueprint-mcp)

- Use `get_blueprint_graphs` to discover what graphs exist in a Blueprint
- Use `get_blueprint_graph` to read full node/pin/connection data
- Use `get_blueprint_flow` to understand execution order from an entry point
- Use `search_blueprint_nodes` to find specific nodes by name
- Asset paths use the format `/Game/Path/To/Blueprint` (no extension)
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

## License

MIT
