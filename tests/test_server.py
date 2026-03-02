"""Tests for the Blueprint MCP server tools."""

import json
from unittest.mock import MagicMock

import pytest


def setup_function():
    """Reset server state before each test."""
    from unreal_blueprint_mcp.server import _reset_state
    _reset_state()


# -- Mock helpers --


def _mock_plugin_response(json_data: dict):
    """Create a mock bridge that returns the given JSON from any command."""
    mock_bridge = MagicMock()
    mock_bridge.run_command.return_value = {
        "success": True,
        "output": json.dumps(json_data),
    }
    return mock_bridge


# -- get_blueprint_graphs tests --


def test_get_blueprint_graphs_success():
    from unreal_blueprint_mcp import server
    data = {
        "asset_path": "/Game/BP_Test",
        "class": "Blueprint",
        "parent_class": "Actor",
        "graphs": [
            {"name": "EventGraph", "type": "event_graph", "node_count": 10},
            {"name": "DoStuff", "type": "function", "node_count": 5},
        ],
    }
    server._bridge = _mock_plugin_response(data)
    result = server.get_blueprint_graphs("/Game/BP_Test")
    assert "EventGraph" in result
    assert "10 nodes" in result
    assert "DoStuff" in result
    assert "function" in result


def test_get_blueprint_graphs_not_found():
    from unreal_blueprint_mcp import server
    data = {"error": True, "message": "Blueprint not found: /Game/Missing"}
    server._bridge = _mock_plugin_response(data)
    result = server.get_blueprint_graphs("/Game/Missing")
    assert "Error" in result
    assert "not found" in result


def test_get_blueprint_graphs_editor_not_running():
    from unreal_blueprint_mcp import server
    from unreal_blueprint_mcp.editor_bridge import EditorNotRunning
    mock_bridge = MagicMock()
    mock_bridge.run_command.side_effect = EditorNotRunning("No editor")
    server._bridge = mock_bridge
    result = server.get_blueprint_graphs("/Game/BP_Test")
    assert "Editor not available" in result


# -- get_blueprint_graph tests --


def test_get_blueprint_graph_returns_json():
    from unreal_blueprint_mcp import server
    data = {
        "graph_name": "EventGraph",
        "graph_type": "event_graph",
        "nodes": [
            {
                "id": "K2Node_Event_0",
                "class": "K2Node_Event",
                "title": "Event BeginPlay",
                "pins": [],
            }
        ],
    }
    server._bridge = _mock_plugin_response(data)
    result = server.get_blueprint_graph("/Game/BP_Test", "EventGraph")
    parsed = json.loads(result)
    assert parsed["graph_name"] == "EventGraph"
    assert len(parsed["nodes"]) == 1
    assert parsed["nodes"][0]["class"] == "K2Node_Event"


# -- get_blueprint_variables tests --


def test_get_blueprint_variables_formatting():
    from unreal_blueprint_mcp import server
    data = {
        "variables": [
            {
                "name": "Health",
                "type": "float",
                "default_value": "100.0",
                "category": "Stats",
                "replicated": True,
                "expose_on_spawn": False,
                "blueprint_read_only": False,
                "transient": False,
            },
            {
                "name": "IsAlive",
                "type": "bool",
                "default_value": "true",
                "category": "",
                "replicated": False,
                "expose_on_spawn": False,
                "blueprint_read_only": True,
                "transient": False,
            },
        ],
    }
    server._bridge = _mock_plugin_response(data)
    result = server.get_blueprint_variables("/Game/BP_Test")
    assert "Health: float = 100.0 [replicated]" in result
    assert "IsAlive: bool = true [read_only]" in result


def test_get_blueprint_variables_empty():
    from unreal_blueprint_mcp import server
    data = {"variables": []}
    server._bridge = _mock_plugin_response(data)
    result = server.get_blueprint_variables("/Game/BP_Test")
    assert "No variables" in result


# -- get_blueprint_flow tests --


def test_get_blueprint_flow_linear():
    from unreal_blueprint_mcp import server
    data = {
        "entry": "ReceiveBeginPlay",
        "graph": "EventGraph",
        "flow": {
            "node": "Event BeginPlay",
            "class": "K2Node_Event",
            "then": [
                {
                    "node": "Print String",
                    "class": "K2Node_CallFunction",
                }
            ],
        },
    }
    server._bridge = _mock_plugin_response(data)
    result = server.get_blueprint_flow("/Game/BP_Test", "ReceiveBeginPlay")
    assert "Event BeginPlay" in result
    assert "Print String" in result
    assert "->" in result


def test_get_blueprint_flow_with_branches():
    from unreal_blueprint_mcp import server
    data = {
        "entry": "ReceiveBeginPlay",
        "graph": "EventGraph",
        "flow": {
            "node": "Branch",
            "class": "K2Node_IfThenElse",
            "branches": {
                "True": [{"node": "DoA", "class": "K2Node_CallFunction"}],
                "False": [{"node": "DoB", "class": "K2Node_CallFunction"}],
            },
        },
    }
    server._bridge = _mock_plugin_response(data)
    result = server.get_blueprint_flow("/Game/BP_Test", "ReceiveBeginPlay")
    assert "[True]" in result
    assert "[False]" in result
    assert "DoA" in result
    assert "DoB" in result


def test_get_blueprint_flow_not_found():
    from unreal_blueprint_mcp import server
    data = {"error": True, "message": "Entry point not found: Nope"}
    server._bridge = _mock_plugin_response(data)
    result = server.get_blueprint_flow("/Game/BP_Test", "Nope")
    assert "Error" in result


# -- search_blueprint_nodes tests --


def test_search_nodes_with_results():
    from unreal_blueprint_mcp import server
    data = {
        "query": "GetActor",
        "match_count": 2,
        "results": [
            {
                "graph": "EventGraph",
                "graph_type": "event_graph",
                "node_id": "K2Node_CallFunction_0",
                "class": "K2Node_CallFunction",
                "title": "Get Actor Location",
                "function": "GetActorLocation",
            },
            {
                "graph": "EventGraph",
                "graph_type": "event_graph",
                "node_id": "K2Node_CallFunction_1",
                "class": "K2Node_CallFunction",
                "title": "Get Actor Rotation",
                "function": "GetActorRotation",
            },
        ],
    }
    server._bridge = _mock_plugin_response(data)
    result = server.search_blueprint_nodes("/Game/BP_Test", "GetActor")
    assert "Found 2 nodes" in result
    assert "GetActorLocation" in result
    assert "GetActorRotation" in result


def test_search_nodes_no_results():
    from unreal_blueprint_mcp import server
    data = {"query": "Nope", "match_count": 0, "results": []}
    server._bridge = _mock_plugin_response(data)
    result = server.search_blueprint_nodes("/Game/BP_Test", "Nope")
    assert "No nodes matching" in result


# -- _call_plugin tests --


def test_call_plugin_builds_correct_command():
    from unreal_blueprint_mcp import server
    mock_bridge = MagicMock()
    mock_bridge.run_command.return_value = {
        "success": True,
        "output": '{"test": true}',
    }
    server._bridge = mock_bridge
    result = server._call_plugin("get_blueprint_graph_list", asset_path="/Game/Test")
    call_args = mock_bridge.run_command.call_args
    command = call_args[0][0]
    assert "BlueprintReaderLibrary" in command
    assert "get_blueprint_graph_list" in command
    assert "/Game/Test" in command


def test_call_plugin_handles_invalid_json():
    from unreal_blueprint_mcp import server
    mock_bridge = MagicMock()
    mock_bridge.run_command.return_value = {
        "success": True,
        "output": "not json at all",
    }
    server._bridge = mock_bridge
    result = server._call_plugin("get_blueprint_graph_list", asset_path="/Game/Test")
    assert result.get("error") is True
    assert "Invalid JSON" in result.get("message", "")


def test_call_plugin_rejects_unknown_function():
    from unreal_blueprint_mcp import server
    result = server._call_plugin("evil_function", asset_path="/Game/Test")
    assert result.get("error") is True
    assert "Unknown function" in result.get("message", "")


def test_call_plugin_escapes_quotes_in_args():
    from unreal_blueprint_mcp import server
    mock_bridge = MagicMock()
    mock_bridge.run_command.return_value = {
        "success": True,
        "output": '{"test": true}',
    }
    server._bridge = mock_bridge
    server._call_plugin(
        "get_blueprint_graph_list",
        asset_path='/Game/Test"; import os; #',
    )
    call_args = mock_bridge.run_command.call_args
    command = call_args[0][0]
    # The injected quote should be escaped
    assert '\\"' in command
    assert 'import os' not in command.split('\n')[1].split('"')[0]


def test_get_blueprint_variables_not_editable():
    from unreal_blueprint_mcp import server
    data = {
        "variables": [
            {
                "name": "InternalVar",
                "type": "int",
                "default_value": "",
                "category": "",
                "instance_editable": False,
                "replicated": False,
                "expose_on_spawn": False,
                "blueprint_read_only": False,
                "transient": False,
            },
        ],
    }
    server._bridge = _mock_plugin_response(data)
    result = server.get_blueprint_variables("/Game/BP_Test")
    assert "not_editable" in result
