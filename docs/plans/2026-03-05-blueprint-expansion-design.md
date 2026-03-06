# Blueprint Expansion Design — Read-Write + Enhanced Reads

## Overview

Expand `unreal-blueprint-mcp` from 5 read-only tools to ~30 tools across 5 stages:

1. **Mutation Core** — Add/remove/modify nodes, connections, variables, graphs
2. **Diagnostics** — Compile and report errors/warnings
3. **Enhanced Reads** — Components, parent chains, references, dispatchers, interfaces, timelines
4. **Advanced Analysis** — Diffing, comment blocks, collapsed graph expansion
5. **Cross-BP Search** — Structural pattern matching across multiple Blueprints

The C++ plugin (`BlueprintReaderLibrary`) grows from 5 UFUNCTIONs to ~30. The Python MCP server adds corresponding tools and adapts `_call_plugin()` for non-string arguments needed by mutations.

---

## Stage 1: Mutation Core

All mutation operations follow this pattern:
1. Load Blueprint via `StaticLoadObject`
2. Open `FScopedTransaction` for undo support
3. Perform the mutation
4. Mark Blueprint modified (`FBlueprintEditorUtils::MarkBlueprintAsModified`)
5. Compile (`FKismetEditorUtilities::CompileBlueprint`)
6. Return JSON with success/error + resulting state

### Common C++ helpers

```cpp
// Shared preamble for all mutation functions
namespace BlueprintMutation
{
    struct FMutationResult
    {
        bool bSuccess;
        FString Message;
        TSharedPtr<FJsonObject> Data;
    };

    // Load + validate + begin transaction
    UBlueprint* BeginMutation(const FString& AssetPath, const FString& OpName);

    // Mark modified + compile + serialize result
    FString FinishMutation(UBlueprint* BP, FMutationResult Result);
}
```

---

### 1.1 add_node

**MCP Tool:**
```python
@mcp.tool()
def add_node(
    asset_path: str,
    graph_name: str,
    node_type: str,         # "CallFunction", "Event", "IfThenElse", "MacroInstance",
                            # "VariableGet", "VariableSet", "Cast", "ForEachLoop",
                            # "SpawnActor", "Delay", "PrintString", "Custom"
    pos_x: int = 0,
    pos_y: int = 0,
    # Type-specific params (JSON string for flexibility):
    params: str = "{}"      # e.g. {"function_name":"SetActorLocation","target_class":"AActor"}
) -> str:
```

**Node type dispatch table:**

| `node_type` | Required `params` | C++ Node Class |
|---|---|---|
| `CallFunction` | `function_name`, optional `target_class` | `UK2Node_CallFunction` |
| `Event` | `event_name` | `UK2Node_Event` |
| `CustomEvent` | `event_name` | `UK2Node_CustomEvent` |
| `IfThenElse` | (none) | `UK2Node_IfThenElse` |
| `MacroInstance` | `macro_path` | `UK2Node_MacroInstance` |
| `VariableGet` | `variable_name` | `UK2Node_VariableGet` |
| `VariableSet` | `variable_name` | `UK2Node_VariableSet` |
| `Cast` | `target_class` | `UK2Node_DynamicCast` |
| `ForEachLoop` | (none) | `UK2Node_CallFunction` (macro) |
| `SpawnActor` | `actor_class` | `UK2Node_SpawnActorFromClass` |
| `Delay` | (none) | `UK2Node_CallFunction` (Delay) |
| `Select` | (none) | `UK2Node_Select` |
| `MakeArray` | (none) | `UK2Node_MakeArray` |
| `SwitchOnEnum` | `enum_type` | `UK2Node_SwitchEnum` |
| `SwitchOnString` | (none) | `UK2Node_SwitchString` |

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString AddNode(
    const FString& AssetPath,
    const FString& GraphName,
    const FString& NodeType,
    int32 PosX,
    int32 PosY,
    const FString& ParamsJson  // type-specific params
);
```

**Key UE APIs:**
- `FEdGraphSchemaAction_K2NewNode::PerformAction()` — preferred way to spawn nodes with proper schema initialization
- `UK2Node_CallFunction::SetFromFunction()` — bind to a UFunction
- `UK2Node_VariableGet/Set::SetPropertyName()` — bind to a variable
- `UEdGraph::AddNode()` — low-level add (use if PerformAction insufficient)
- `Node->CreateNewGuid()`, `Node->PostPlacedNewNode()`, `Node->AllocateDefaultPins()`

**Implementation sketch:**
```cpp
FString UBlueprintWriterLibrary::AddNode(
    const FString& AssetPath, const FString& GraphName,
    const FString& NodeType, int32 PosX, int32 PosY,
    const FString& ParamsJson)
{
    UBlueprint* BP = LoadBP(AssetPath);
    if (!BP) return ErrorJson("Blueprint not found");
    UEdGraph* Graph = FindGraphByName(BP, GraphName);
    if (!Graph) return ErrorJson("Graph not found");

    TSharedPtr<FJsonObject> Params;
    auto Reader = TJsonReaderFactory<>::Create(ParamsJson);
    FJsonSerializer::Deserialize(Reader, Params);

    FScopedTransaction Transaction(FText::FromString("MCP: Add Node"));
    Graph->Modify();

    UK2Node* NewNode = nullptr;

    if (NodeType == "CallFunction")
    {
        FString FuncName = Params->GetStringField("function_name");
        FString TargetClass = Params->GetStringField("target_class");

        UFunction* Func = FindFunction(FuncName, TargetClass); // helper
        if (!Func) return ErrorJson("Function not found");

        UK2Node_CallFunction* CallNode = NewObject<UK2Node_CallFunction>(Graph);
        CallNode->SetFromFunction(Func);
        NewNode = CallNode;
    }
    else if (NodeType == "VariableGet")
    {
        FName VarName(*Params->GetStringField("variable_name"));
        UK2Node_VariableGet* GetNode = NewObject<UK2Node_VariableGet>(Graph);
        GetNode->VariableReference.SetSelfMember(VarName);
        NewNode = GetNode;
    }
    // ... dispatch for each node type ...

    if (!NewNode) return ErrorJson("Unknown node type");

    NewNode->NodePosX = PosX;
    NewNode->NodePosY = PosY;
    NewNode->CreateNewGuid();
    NewNode->PostPlacedNewNode();
    NewNode->AllocateDefaultPins();
    Graph->AddNode(NewNode, false, false);

    FBlueprintEditorUtils::MarkBlueprintAsModified(BP);
    FKismetEditorUtilities::CompileBlueprint(BP);

    // Return node ID and pin list
    return SerializeNodeResult(NewNode);
}
```

**Safety:** Transaction wrapping enables Ctrl+Z undo. Validate function/variable existence before creating node. Compile after to catch immediate errors.

---

### 1.2 remove_node

**MCP Tool:**
```python
@mcp.tool()
def remove_node(asset_path: str, graph_name: str, node_id: str) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString RemoveNode(
    const FString& AssetPath,
    const FString& GraphName,
    const FString& NodeId
);
```

**Key UE APIs:**
- `FBlueprintEditorUtils::RemoveNode(BP, Node)` — handles pin disconnection, notification, cleanup
- Preferred over `Graph->RemoveNode()` which doesn't clean up properly

**Safety:** Verify node exists. RemoveNode handles disconnecting all pins automatically.

---

### 1.3 modify_node

**MCP Tool:**
```python
@mcp.tool()
def modify_node(
    asset_path: str,
    graph_name: str,
    node_id: str,
    pos_x: int | None = None,
    pos_y: int | None = None,
    comment: str | None = None,
    # Node-type-specific modifications via JSON
    params: str = "{}"
) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString ModifyNode(
    const FString& AssetPath,
    const FString& GraphName,
    const FString& NodeId,
    const FString& ModificationsJson  // {"pos_x":100,"pos_y":200,"comment":"..."}
);
```

**Key UE APIs:**
- Direct property assignment: `Node->NodePosX`, `Node->NodePosY`, `Node->NodeComment`
- `Node->ReconstructNode()` if pin layout changes

---

### 1.4 connect_pins

**MCP Tool:**
```python
@mcp.tool()
def connect_pins(
    asset_path: str,
    graph_name: str,
    source_node_id: str,
    source_pin_name: str,
    target_node_id: str,
    target_pin_name: str,
) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString ConnectPins(
    const FString& AssetPath,
    const FString& GraphName,
    const FString& SourceNodeId,
    const FString& SourcePinName,
    const FString& TargetNodeId,
    const FString& TargetPinName
);
```

**Key UE APIs:**
- `Graph->GetSchema()->TryCreateConnection(PinA, PinB)` — validates type compatibility, returns bool
- `UEdGraphSchema_K2::CanCreateConnection()` — pre-check without making the connection

**Safety:** Use `TryCreateConnection` which validates type compatibility. Return the schema's error message if connection fails.

---

### 1.5 disconnect_pins

**MCP Tool:**
```python
@mcp.tool()
def disconnect_pins(
    asset_path: str,
    graph_name: str,
    node_id: str,
    pin_name: str,
    target_node_id: str = "",   # empty = disconnect all
    target_pin_name: str = "",
) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString DisconnectPins(
    const FString& AssetPath,
    const FString& GraphName,
    const FString& NodeId,
    const FString& PinName,
    const FString& TargetNodeId,
    const FString& TargetPinName
);
```

**Key UE APIs:**
- `Pin->BreakLinkTo(OtherPin)` — disconnect specific link
- `Pin->BreakAllPinLinks()` — disconnect all (when target not specified)

---

### 1.6 set_pin_default

**MCP Tool:**
```python
@mcp.tool()
def set_pin_default(
    asset_path: str,
    graph_name: str,
    node_id: str,
    pin_name: str,
    value: str,
) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString SetPinDefault(
    const FString& AssetPath,
    const FString& GraphName,
    const FString& NodeId,
    const FString& PinName,
    const FString& Value
);
```

**Key UE APIs:**
- `Graph->GetSchema()->TrySetDefaultValue(*Pin, Value)` — validates and sets
- `Pin->DefaultValue` — direct assignment (less safe)
- `Pin->DefaultObject` — for object references

---

### 1.7 add_variable

**MCP Tool:**
```python
@mcp.tool()
def add_variable(
    asset_path: str,
    variable_name: str,
    variable_type: str,        # "bool", "int", "float", "string", "Vector", "Object:ClassName"
    default_value: str = "",
    instance_editable: bool = True,
    category: str = "",
) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString AddVariable(
    const FString& AssetPath,
    const FString& VariableName,
    const FString& VariableType,
    const FString& DefaultValue,
    bool bInstanceEditable,
    const FString& Category
);
```

**Key UE APIs:**
- `FBlueprintEditorUtils::AddMemberVariable(BP, VarName, PinType)` — the correct way
- `FEdGraphPinType` construction from type string (parse "bool"→PC_Boolean, "Object:Actor"→PC_Object+SubCategoryObject)

**Safety:** Validate variable name is unique. Type string parsing must be robust.

---

### 1.8 remove_variable

**MCP Tool:**
```python
@mcp.tool()
def remove_variable(asset_path: str, variable_name: str) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString RemoveVariable(const FString& AssetPath, const FString& VariableName);
```

**Key UE APIs:**
- `FBlueprintEditorUtils::RemoveMemberVariable(BP, VarName)`
- Check for references first — return warning listing nodes that use this variable

---

### 1.9 set_variable_default

**MCP Tool:**
```python
@mcp.tool()
def set_variable_default(asset_path: str, variable_name: str, value: str) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString SetVariableDefault(
    const FString& AssetPath,
    const FString& VariableName,
    const FString& Value
);
```

**Key UE APIs:**
- Modify `FBPVariableDescription::DefaultValue` in `BP->NewVariables`
- `FBlueprintEditorUtils::MarkBlueprintAsModified(BP)`

---

### 1.10 add_event_dispatcher

**MCP Tool:**
```python
@mcp.tool()
def add_event_dispatcher(asset_path: str, dispatcher_name: str) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString AddEventDispatcher(const FString& AssetPath, const FString& DispatcherName);
```

**Key UE APIs:**
- `FBlueprintEditorUtils::AddMemberVariable()` with `PC_MCDelegate` type
- Or directly: add to `BP->DelegateSignatureGraphs` + create signature graph

---

### 1.11 remove_event_dispatcher

**MCP Tool:**
```python
@mcp.tool()
def remove_event_dispatcher(asset_path: str, dispatcher_name: str) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString RemoveEventDispatcher(const FString& AssetPath, const FString& DispatcherName);
```

**Key UE APIs:**
- `FBlueprintEditorUtils::RemoveMemberVariable(BP, DispatcherName)`
- Remove associated delegate signature graph

---

### 1.12 create_graph

**MCP Tool:**
```python
@mcp.tool()
def create_graph(
    asset_path: str,
    graph_name: str,
    graph_type: str = "function",  # "function", "macro", "event_graph"
) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString CreateGraph(
    const FString& AssetPath,
    const FString& GraphName,
    const FString& GraphType
);
```

**Key UE APIs:**
- `FBlueprintEditorUtils::AddFunctionGraph(BP, Graph, /*bIsUserCreated=*/true, /*SignatureFromObject=*/nullptr)`
- `FBlueprintEditorUtils::AddMacroGraph(BP, GraphName, /*bIsUserCreated=*/true, /*SignatureFromBlueprint=*/nullptr)`
- `FEdGraphSchemaAction_K2NewNode` for function entry/result nodes auto-creation

---

### 1.13 delete_graph

**MCP Tool:**
```python
@mcp.tool()
def delete_graph(asset_path: str, graph_name: str) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Writer")
static FString DeleteGraph(const FString& AssetPath, const FString& GraphName);
```

**Key UE APIs:**
- `FBlueprintEditorUtils::RemoveGraph(BP, Graph)`
- Refuse to delete the last UbergraphPage (EventGraph)

---

## Stage 2: Diagnostics

### 2.1 get_compilation_status

**MCP Tool:**
```python
@mcp.tool()
def get_compilation_status(asset_path: str, force_recompile: bool = False) -> str:
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString GetCompilationStatus(const FString& AssetPath, bool bForceRecompile);
```

**Key UE APIs:**
- `FKismetEditorUtilities::CompileBlueprint(BP)` — if force recompile
- `BP->Status` — `BS_UpToDate`, `BS_Dirty`, `BS_Error`, `BS_BeingCreated`
- `BP->Message` array — compiler messages with severity

**Return JSON format:**
```json
{
    "status": "error",
    "up_to_date": false,
    "messages": [
        {
            "severity": "error",
            "message": "Pin 'Target' on node 'Set Actor Location' has no connection and no default",
            "node_id": "K2Node_CallFunction_42",
            "graph": "EventGraph",
            "line": null
        },
        {
            "severity": "warning",
            "message": "Variable 'OldHealth' is unused",
            "node_id": null,
            "graph": null,
            "line": null
        }
    ],
    "error_count": 1,
    "warning_count": 1
}
```

**Implementation:** Iterate `BP->ErrorMessageLog` or hook into `FCompilerResultsLog` during compile. Each `FTokenizedMessage` has severity + optional node reference.

---

## Stage 3: Enhanced Reads

### 3.1 get_component_list

**MCP Tool:**
```python
@mcp.tool()
def get_component_list(asset_path: str) -> str:
    """List all components in a Blueprint's component hierarchy."""
```

**Return format:**
```json
{
    "root": "DefaultSceneRoot",
    "components": [
        {
            "name": "DefaultSceneRoot",
            "class": "USceneComponent",
            "parent": null,
            "children": ["StaticMesh1", "BoxCollision"]
        },
        {
            "name": "StaticMesh1",
            "class": "UStaticMeshComponent",
            "parent": "DefaultSceneRoot",
            "children": []
        }
    ]
}
```

**C++ approach:**
- Access `BP->SimpleConstructionScript->GetRootNodes()`
- Walk `USCS_Node` tree: `GetChildNodes()`, `ComponentClass`, `GetVariableName()`

```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString GetComponentList(const FString& AssetPath);
```

---

### 3.2 get_parent_chain

**MCP Tool:**
```python
@mcp.tool()
def get_parent_chain(asset_path: str) -> str:
    """Get the full parent class chain from this Blueprint up to UObject."""
```

**Return:** Array of `{"class":"BP_Enemy","type":"blueprint","asset_path":"/Game/BP_Enemy"}` entries.

**C++ approach:**
- Walk `BP->ParentClass->GetSuperClass()` chain
- Check `UBlueprint::GetBlueprintFromClass()` to distinguish BP vs native parents

```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString GetParentChain(const FString& AssetPath);
```

---

### 3.3 get_references

**MCP Tool:**
```python
@mcp.tool()
def get_references(asset_path: str) -> str:
    """Get assets referenced by this Blueprint and assets that reference it."""
```

**C++ approach:**
- `FAssetRegistryModule::GetDependencies()` — what this BP uses
- `FAssetRegistryModule::GetReferencers()` — what uses this BP

```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString GetReferences(const FString& AssetPath);
```

---

### 3.4 get_event_dispatchers

**MCP Tool:**
```python
@mcp.tool()
def get_event_dispatchers(asset_path: str) -> str:
    """List all event dispatchers with their signature pins."""
```

**C++ approach:**
- Iterate `BP->DelegateSignatureGraphs`
- For each graph, find `UK2Node_FunctionEntry` and read its output pins (the signature)

```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString GetEventDispatchers(const FString& AssetPath);
```

---

### 3.5 get_interfaces

**MCP Tool:**
```python
@mcp.tool()
def get_interfaces(asset_path: str) -> str:
    """List all interfaces implemented by this Blueprint with their functions."""
```

**C++ approach:**
- `BP->ImplementedInterfaces` array → `FBPInterfaceDescription`
- Each has `InterfaceClass` and `Graphs` for implemented functions

```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString GetInterfaces(const FString& AssetPath);
```

---

### 3.6 get_variable_metadata

**MCP Tool:**
```python
@mcp.tool()
def get_variable_metadata(asset_path: str, variable_name: str) -> str:
    """Get detailed metadata for a specific variable: replication, tooltip, clamping, etc."""
```

**C++ approach:**
- Find in `BP->NewVariables` by name
- Read `FBPVariableDescription::PropertyFlags`, `RepNotifyFunc`, `MetaDataArray`

```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString GetVariableMetadata(const FString& AssetPath, const FString& VariableName);
```

---

### 3.7 get_timelines

**MCP Tool:**
```python
@mcp.tool()
def get_timelines(asset_path: str) -> str:
    """List all timelines with their tracks, keyframes, and length."""
```

**C++ approach:**
- `BP->Timelines` array → `UTimelineTemplate`
- Each has float/vector/event tracks, `TimelineLength`, `bLoop`

```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString GetTimelines(const FString& AssetPath);
```

---

### 3.8 inspect_library

**MCP Tool:**
```python
@mcp.tool()
def inspect_library(class_name: str, function_filter: str = "") -> str:
    """List callable functions on a class — useful for discovering what nodes are available."""
```

**C++ approach:**
- `FindObject<UClass>(ANY_PACKAGE, *ClassName)`
- Iterate `TFieldIterator<UFunction>(Class)` — filter `FUNC_BlueprintCallable`
- Return function name, params, return type

```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString InspectLibrary(const FString& ClassName, const FString& FunctionFilter);
```

---

### 3.9 resolve_pin_value

**MCP Tool:**
```python
@mcp.tool()
def resolve_pin_value(
    asset_path: str, graph_name: str, node_id: str, pin_name: str
) -> str:
    """Trace a data pin backwards to find what feeds into it — through reroute nodes, casts, etc."""
```

**C++ approach:**
- Follow `Pin->LinkedTo` chain, skipping `K2Node_Knot` (reroute) nodes
- Collect the chain of transformations until reaching a source (variable, literal, function output)

```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString ResolvePinValue(
    const FString& AssetPath,
    const FString& GraphName,
    const FString& NodeId,
    const FString& PinName
);
```

---

## Stage 4: Advanced Analysis

### 4.1 diff_blueprints

**MCP Tool:**
```python
@mcp.tool()
def diff_blueprints(
    asset_path_a: str,
    asset_path_b: str,
    graph_name: str = "",  # empty = compare all graphs
) -> str:
    """Compare two Blueprints or two graphs, reporting added/removed/modified nodes."""
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString DiffBlueprints(
    const FString& AssetPathA,
    const FString& AssetPathB,
    const FString& GraphName
);
```

**Approach:** Load both BPs, serialize their graphs to JSON (reusing existing `SerializeNode`), then diff in C++:
- Match nodes by class + title (not by ID, since IDs differ across BPs)
- Report: `added_nodes`, `removed_nodes`, `modified_nodes` (pin/connection differences), `added_variables`, `removed_variables`

---

### 4.2 get_comment_blocks

**MCP Tool:**
```python
@mcp.tool()
def get_comment_blocks(asset_path: str, graph_name: str = "") -> str:
    """Get all comment boxes with their text and the nodes they contain."""
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString GetCommentBlocks(const FString& AssetPath, const FString& GraphName);
```

**Key UE APIs:**
- `UEdGraphNode_Comment` — comment node class
- `Node->NodePosX/Y`, `Node->NodeWidth`, `Node->NodeHeight` — bounding box
- Check which nodes fall within the comment's bounds

---

### 4.3 expand_collapsed_graph

**MCP Tool:**
```python
@mcp.tool()
def expand_collapsed_graph(
    asset_path: str, graph_name: str, node_id: str
) -> str:
    """Read the subgraph inside a collapsed node, returning full graph data."""
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString ExpandCollapsedGraph(
    const FString& AssetPath,
    const FString& GraphName,
    const FString& NodeId
);
```

**Key UE APIs:**
- `UK2Node_Composite::BoundGraph` — the subgraph inside a collapsed node
- Serialize using existing `SerializeNode` on the subgraph's nodes

---

## Stage 5: Cross-BP Search

### 5.1 search_by_connection_pattern

**MCP Tool:**
```python
@mcp.tool()
def search_by_connection_pattern(
    search_path: str,           # e.g. "/Game/Characters/" — scope
    pattern: str,               # pattern query (see below)
    max_results: int = 20,
) -> str:
    """Find structural patterns across Blueprints in a directory."""
```

**C++ UFUNCTION:**
```cpp
UFUNCTION(BlueprintCallable, Category = "Blueprint Reader")
static FString SearchByConnectionPattern(
    const FString& SearchPath,
    const FString& PatternJson,
    int32 MaxResults
);
```

**Query format:**

Pattern is a JSON array of node matchers with connection constraints:

```json
{
    "nodes": [
        {"id": "A", "class": "K2Node_DynamicCast", "params": {"target_class": "*"}},
        {"id": "B", "class": "K2Node_CallFunction", "params": {"function_name": "SetActorLocation"}}
    ],
    "connections": [
        {"from": "A", "from_pin": "As *", "to": "B", "to_pin": "Target"}
    ]
}
```

This expresses: "Find Cast nodes whose output feeds into SetActorLocation's Target pin."

**Wildcards:**
- `*` in params matches any value
- Pin names support `*` prefix/suffix matching (`"As *"` matches `"As BP_Enemy"`)
- Omitting `connections` finds nodes matching the matchers independently

**Implementation:** Use `FAssetRegistryModule` to enumerate Blueprint assets under `SearchPath`, load each, and test the pattern against all graphs.

---

## C++ File Organization

Split the growing library into domain-specific files:

```
Source/BlueprintReader/
├── BlueprintReaderLibrary.h         # Main header, all UFUNCTION declarations
├── BlueprintReaderLibrary.cpp       # Existing 5 read functions (unchanged)
├── BlueprintWriterLibrary.h         # Mutation UFUNCTION declarations
├── BlueprintWriterLibrary.cpp       # Stage 1 mutations (split further if needed)
├── BlueprintDiagnostics.cpp         # Stage 2 compile/diagnostics
├── BlueprintEnhancedReads.cpp       # Stage 3 enhanced reads
├── BlueprintAnalysis.cpp            # Stage 4 diff/comments/collapsed
├── BlueprintCrossBPSearch.cpp       # Stage 5 cross-BP pattern search
├── BlueprintMutationHelpers.h       # Shared: BeginMutation, FinishMutation, type parsing
├── BlueprintMutationHelpers.cpp
├── BlueprintJsonHelpers.h           # Shared: SerializeNode, SerializePin, ErrorJson
└── BlueprintJsonHelpers.cpp
```

Extract existing helpers (`LoadBP`, `ErrorJson`, `SerializeNode`, `SerializePin`, `PinTypeToString`, `FindGraphByName`) into `BlueprintJsonHelpers` so both reader and writer can use them.

The `.Build.cs` module file needs additional dependencies for mutations:
```csharp
PrivateDependencyModuleNames.AddRange(new string[] {
    "UnrealEd",           // FBlueprintEditorUtils, FKismetEditorUtilities
    "KismetCompiler",     // Compilation
    "BlueprintGraph",     // K2Node types
    "AssetRegistry",      // Cross-BP search
});
```

---

## Python MCP Changes

### _call_plugin evolution

Current `_call_plugin` only passes string kwargs. Mutations need integers and booleans.

```python
def _call_plugin(func_name: str, **kwargs: str | int | bool) -> dict:
    if func_name not in _ALLOWED_FUNCTIONS:
        return {"error": True, "message": f"Unknown function: {func_name}"}

    bridge = _get_bridge()

    arg_parts = []
    for k, v in kwargs.items():
        if isinstance(v, bool):
            arg_parts.append(f"{k}={'True' if v else 'False'}")
        elif isinstance(v, int):
            arg_parts.append(f"{k}={v}")
        else:
            arg_parts.append(f'{k}="{_escape_py_string(str(v))}"')

    args = ", ".join(arg_parts)
    # Mutations use BlueprintWriterLibrary, reads use BlueprintReaderLibrary
    lib_class = _FUNCTION_LIBRARY.get(func_name, "BlueprintReaderLibrary")
    command = (
        "import unreal, json\n"
        f"result = unreal.{lib_class}.{func_name}({args})\n"
        "print(result)"
    )
    # ... rest unchanged ...
```

### New _ALLOWED_FUNCTIONS

```python
_ALLOWED_FUNCTIONS = {
    # Stage 0 — existing reads
    "get_blueprint_graph_list",
    "get_graph_data",
    "get_blueprint_variables",
    "get_execution_flow",
    "search_nodes",
    # Stage 1 — mutations
    "add_node",
    "remove_node",
    "modify_node",
    "connect_pins",
    "disconnect_pins",
    "set_pin_default",
    "add_variable",
    "remove_variable",
    "set_variable_default",
    "add_event_dispatcher",
    "remove_event_dispatcher",
    "create_graph",
    "delete_graph",
    # Stage 2 — diagnostics
    "get_compilation_status",
    # Stage 3 — enhanced reads
    "get_component_list",
    "get_parent_chain",
    "get_references",
    "get_event_dispatchers",
    "get_interfaces",
    "get_variable_metadata",
    "get_timelines",
    "inspect_library",
    "resolve_pin_value",
    # Stage 4 — advanced analysis
    "diff_blueprints",
    "get_comment_blocks",
    "expand_collapsed_graph",
    # Stage 5 — cross-BP search
    "search_by_connection_pattern",
}

# Map function → C++ library class
_FUNCTION_LIBRARY = {
    "add_node": "BlueprintWriterLibrary",
    "remove_node": "BlueprintWriterLibrary",
    "modify_node": "BlueprintWriterLibrary",
    "connect_pins": "BlueprintWriterLibrary",
    "disconnect_pins": "BlueprintWriterLibrary",
    "set_pin_default": "BlueprintWriterLibrary",
    "add_variable": "BlueprintWriterLibrary",
    "remove_variable": "BlueprintWriterLibrary",
    "set_variable_default": "BlueprintWriterLibrary",
    "add_event_dispatcher": "BlueprintWriterLibrary",
    "remove_event_dispatcher": "BlueprintWriterLibrary",
    "create_graph": "BlueprintWriterLibrary",
    "delete_graph": "BlueprintWriterLibrary",
    # Everything else defaults to BlueprintReaderLibrary
}
```

### Server instructions update

```python
mcp = FastMCP(
    "unreal-blueprint",
    instructions=(
        "Blueprint graph reader and writer for Unreal Engine. "
        "Read and modify Blueprint graphs, nodes, pins, connections, variables, "
        "execution flow, components, interfaces, and more. "
        "Mutations are wrapped in undo transactions — use Ctrl+Z in the editor to revert."
    ),
)
```

---

## Testing Strategy

Same pattern as existing tests: mock `EditorBridge.run_command` to return canned JSON responses.

### Test structure

```python
# tests/test_mutations.py
def test_add_node_call_function(mock_bridge):
    """add_node dispatches correct Python command for CallFunction."""
    mock_bridge.return_value = {
        "success": True,
        "output": json.dumps({
            "success": True,
            "node_id": "K2Node_CallFunction_42",
            "pins": [{"name": "execute", "direction": "input", "type": "exec"}]
        })
    }
    result = add_node(
        asset_path="/Game/BP_Test",
        graph_name="EventGraph",
        node_type="CallFunction",
        pos_x=100, pos_y=200,
        params='{"function_name":"SetActorLocation"}'
    )
    assert "K2Node_CallFunction_42" in result
    # Verify the command sent to bridge
    cmd = mock_bridge.call_args[0][0]
    assert "BlueprintWriterLibrary.add_node" in cmd
    assert "SetActorLocation" in cmd
```

### Test categories

1. **Mutation dispatch tests** — verify correct Python commands are built for each mutation type
2. **Parameter encoding tests** — verify int/bool/string args are encoded correctly in `_call_plugin`
3. **Error handling tests** — verify graceful handling of:
   - Blueprint not found
   - Node/pin not found
   - Invalid node type
   - Type-incompatible pin connections
   - Compile errors after mutation
4. **Enhanced read format tests** — verify formatting of new read tool outputs
5. **Pattern query parsing tests** — verify cross-BP search query JSON is built correctly

### Integration test helpers

For manual integration testing with a running editor, add a `tests/integration/` directory with helpers that create a test Blueprint, run mutations, and verify results. These are not run in CI.

```python
# tests/integration/conftest.py
@pytest.fixture
def test_blueprint(live_bridge):
    """Create a temporary Blueprint for testing, clean up after."""
    live_bridge.run_command(
        "import unreal; "
        "factory = unreal.BlueprintFactory(); "
        "asset = unreal.AssetToolsHelpers.get_asset_tools()"
        ".create_asset('BP_MCPTest', '/Game/Tests', unreal.Blueprint, factory)"
    )
    yield "/Game/Tests/BP_MCPTest"
    live_bridge.run_command(
        "import unreal; "
        "unreal.EditorAssetLibrary.delete_asset('/Game/Tests/BP_MCPTest')"
    )
```
