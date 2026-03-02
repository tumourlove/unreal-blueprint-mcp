# CLAUDE.md — unreal-blueprint-mcp

## Project Overview

**unreal-blueprint-mcp** — Blueprint graph reader for Unreal Engine AI development.

A two-part system: a C++ editor plugin (`unreal-blueprint-reader`) serializes Blueprint graph data to JSON, and this Python MCP server wraps those functions as 5 tools for AI assistants.

**Complements** (does not replace):
- `unreal-source-mcp` — Engine-level source intelligence
- `unreal-project-mcp` — Project-level source intelligence
- `unreal-editor-mcp` — Build diagnostics and editor log tools
- `unreal-api-mcp` — API surface (signatures, includes, deprecation)

**We provide:** Structural access to Blueprint graphs — nodes, pins, connections, execution flow, variables.

## Tech Stack

- **Language:** Python 3.11+
- **MCP SDK:** `mcp` Python package (FastMCP)
- **Distribution:** PyPI via `uvx unreal-blueprint-mcp`
- **Package manager:** `uv` (for dev and build)
- **C++ plugin:** `unreal-blueprint-reader` (companion, must be installed in UE project)

## Project Structure

    unreal-blueprint-mcp/
    ├── pyproject.toml
    ├── CLAUDE.md
    ├── src/
    │   └── unreal_blueprint_mcp/
    │       ├── __init__.py          # Version
    │       ├── __main__.py          # CLI entry point
    │       ├── config.py            # UE_PROJECT_PATH, port config
    │       ├── server.py            # FastMCP + 5 tool definitions
    │       └── editor_bridge.py     # UE remote execution protocol client
    └── tests/
        └── test_server.py           # 13 tests (mocked bridge)

## Build & Run

```bash
uv sync                                    # Install deps
uv run pytest                              # Run tests
uv run python -m unreal_blueprint_mcp      # Run MCP server
```

## MCP Configuration (for Claude Code)

```json
{
  "mcpServers": {
    "unreal-blueprint": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/tumourlove/unreal-blueprint-mcp.git", "unreal-blueprint-mcp"],
      "env": {
        "UE_PROJECT_PATH": "D:/Unreal Projects/Leviathan"
      }
    }
  }
}
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `UE_PROJECT_PATH` | Path to UE project root (contains .uproject) |
| `UE_EDITOR_PYTHON_PORT` | TCP port for command connection (default: 6776) |
| `UE_MULTICAST_GROUP` | UDP multicast group for discovery (default: 239.0.0.1) |
| `UE_MULTICAST_PORT` | UDP multicast port (default: 6766) |
| `UE_MULTICAST_BIND` | Multicast bind address (default: 127.0.0.1) |

## MCP Tools (5)

| Tool | Purpose |
|------|---------|
| `get_blueprint_graphs` | List all graphs (event graphs, functions, macros) in a Blueprint |
| `get_blueprint_graph` | Get full graph data: all nodes with pins, connections, defaults |
| `get_blueprint_variables` | Get all variables with types, defaults, and property flags |
| `get_blueprint_flow` | Get linearized execution flow from an entry point |
| `search_blueprint_nodes` | Search nodes by title, class, or function name |

## Architecture Notes

- **C++ plugin does the heavy lifting** — walks UEdGraph nodes/pins/connections, serializes to JSON via UFUNCTIONs
- **MCP server is a thin wrapper** — calls plugin functions via editor Python bridge, formats output for AI consumption
- **Editor bridge** uses UE's remote execution protocol: UDP multicast discovery → TCP command connection
- `_call_plugin()` builds Python commands that call `unreal.BlueprintReaderLibrary.*` methods and parses JSON responses
- Tool handlers format the JSON into human-readable text (except `get_blueprint_graph` which returns raw JSON for AI parsing)

## Coding Conventions

- Follow standard Python conventions: snake_case, type hints, docstrings on public functions
- Use `logging` module, not print statements
- Tests use pytest with mocked bridge (no editor needed)
- Keep dependencies minimal — just `mcp>=1.0.0`
