"""MCP server with 5 tools for UE Blueprint graph reading."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from unreal_blueprint_mcp.editor_bridge import EditorBridge, EditorNotRunning

mcp = FastMCP(
    "unreal-blueprint",
    instructions=(
        "Blueprint graph reader for Unreal Engine. "
        "Read Blueprint graphs, nodes, pins, connections, variables, "
        "execution flow, and search for nodes."
    ),
)

_bridge: EditorBridge | None = None


def _reset_state() -> None:
    """Reset all singletons (for testing)."""
    global _bridge
    if _bridge:
        _bridge.disconnect()
    _bridge = None


def _get_bridge() -> EditorBridge:
    """Lazy-init the editor bridge."""
    global _bridge
    if _bridge is not None:
        return _bridge
    _bridge = EditorBridge(auto_connect=False)
    return _bridge


def _call_plugin(func_name: str, **kwargs: str) -> dict:
    """Call a BlueprintReaderLibrary function via the editor Python bridge.

    Returns the parsed JSON response from the plugin.
    Raises EditorNotRunning if the editor is not available.
    """
    bridge = _get_bridge()

    # Build the Python command to run in the editor
    args = ", ".join(f'{k}="{v}"' for k, v in kwargs.items())
    command = (
        "import unreal, json\n"
        f"result = unreal.BlueprintReaderLibrary.{func_name}({args})\n"
        "print(result)"
    )

    result = bridge.run_command(command, exec_mode="ExecuteFile")
    if not result.get("success", False):
        return {"error": True, "message": result.get("result", "Command failed")}

    # The plugin returns JSON as a string via print()
    output = result.get("output", "").strip()
    if not output:
        # Try the result field
        output = result.get("result", "").strip()

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"error": True, "message": f"Invalid JSON from plugin: {output[:200]}"}


def _format_error(data: dict) -> str | None:
    """Return error message if data is an error response, else None."""
    if data.get("error"):
        return f"Error: {data.get('message', 'Unknown error')}"
    return None


# -- Tools (5) ---------------------------------------------------------------


@mcp.tool()
def get_blueprint_graphs(asset_path: str) -> str:
    """List all graphs in a Blueprint: event graphs, functions, macros.

    asset_path: Full asset path, e.g. '/Game/Characters/BP_Hero'
    """
    try:
        data = _call_plugin("get_blueprint_graph_list", asset_path=asset_path)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return err

    lines = [
        f"Blueprint: {data.get('asset_path', '')}",
        f"Class: {data.get('class', '')}",
        f"Parent: {data.get('parent_class', '')}",
        "",
        "Graphs:",
    ]
    for g in data.get("graphs", []):
        lines.append(f"  [{g['type']}] {g['name']} ({g['node_count']} nodes)")

    return "\n".join(lines)


@mcp.tool()
def get_blueprint_graph(asset_path: str, graph_name: str = "") -> str:
    """Get full graph data: all nodes with pins, connections, defaults.

    asset_path: Full asset path, e.g. '/Game/Characters/BP_Hero'
    graph_name: Name of the graph (e.g. 'EventGraph'). Empty = main event graph.

    Returns structured JSON with all node and pin data.
    """
    try:
        data = _call_plugin(
            "get_graph_data",
            asset_path=asset_path,
            graph_name=graph_name,
        )
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return err

    # Return the full JSON — the AI can parse it
    return json.dumps(data, indent=2)


@mcp.tool()
def get_blueprint_variables(asset_path: str) -> str:
    """Get all variables defined in a Blueprint with types, defaults, and flags.

    asset_path: Full asset path, e.g. '/Game/Characters/BP_Hero'
    """
    try:
        data = _call_plugin("get_blueprint_variables", asset_path=asset_path)
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return err

    variables = data.get("variables", [])
    if not variables:
        return "No variables defined in this Blueprint."

    lines = ["Variables:"]
    for v in variables:
        flags = []
        if v.get("replicated"):
            flags.append("replicated")
        if v.get("expose_on_spawn"):
            flags.append("expose_on_spawn")
        if v.get("blueprint_read_only"):
            flags.append("read_only")
        if v.get("transient"):
            flags.append("transient")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        default = f" = {v['default_value']}" if v.get("default_value") else ""
        category = f" ({v['category']})" if v.get("category") else ""
        lines.append(f"  {v['name']}: {v['type']}{default}{flag_str}{category}")

    return "\n".join(lines)


@mcp.tool()
def get_blueprint_flow(asset_path: str, entry_point: str) -> str:
    """Get linearized execution flow from an entry point.

    asset_path: Full asset path, e.g. '/Game/Characters/BP_Hero'
    entry_point: Name of the entry event or function (e.g. 'ReceiveBeginPlay', 'SetupHUD')
    """
    try:
        data = _call_plugin(
            "get_execution_flow",
            asset_path=asset_path,
            entry_point=entry_point,
        )
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return err

    # Format as indented text tree
    lines = [f"Flow from: {data.get('entry', '')} (graph: {data.get('graph', '')})"]

    def format_flow(flow: dict, indent: int = 0) -> None:
        prefix = "  " * indent
        node_name = flow.get("node", "?")
        lines.append(f"{prefix}-> {node_name}")

        if "then" in flow:
            for child in flow["then"]:
                format_flow(child, indent + 1)
        elif "branches" in flow:
            for branch_name, children in flow["branches"].items():
                lines.append(f"{prefix}   [{branch_name}]:")
                for child in children:
                    format_flow(child, indent + 2)

    flow = data.get("flow")
    if flow:
        format_flow(flow)
    else:
        lines.append("  (no execution flow from this entry point)")

    return "\n".join(lines)


@mcp.tool()
def search_blueprint_nodes(asset_path: str, query: str) -> str:
    """Search for nodes in a Blueprint by title, class, or function name.

    asset_path: Full asset path, e.g. '/Game/Characters/BP_Hero'
    query: Search string (case-insensitive)
    """
    try:
        data = _call_plugin(
            "search_nodes",
            asset_path=asset_path,
            query=query,
        )
    except EditorNotRunning as e:
        return f"Editor not available: {e}"

    err = _format_error(data)
    if err:
        return err

    results = data.get("results", [])
    if not results:
        return f"No nodes matching '{query}'."

    lines = [f"Found {data.get('match_count', 0)} nodes matching '{query}':"]
    for r in results:
        func = f" -> {r['function']}" if r.get("function") else ""
        lines.append(
            f"  [{r['graph_type']}:{r['graph']}] {r['class']}: {r['title']}{func}"
        )

    return "\n".join(lines)


# -- Entry point -----------------------------------------------------------


def main() -> None:
    """Run the MCP server."""
    mcp.run()
