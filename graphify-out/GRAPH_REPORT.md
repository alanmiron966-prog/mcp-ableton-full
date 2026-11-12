# Graph Report - Ableton MCP  (2026-11-11)

## Corpus Check
- 19 files · ~69,856 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: .xml 2, (none) 1, .lock 1)

## Summary
- 517 nodes · 743 edges · 24 communities (17 shown, 7 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 21 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- tool
- AbletonClaude
- server.py
- vst3_scan.py
- evaluation.py
- agent_loop
- test_sin_ableton.py
- Node/TypeScript MCP Server Implementation Guide
- ableton-mcp
- Python MCP Server Implementation Guide
- Node/TypeScript MCP Server Implementation Guide (SDK v2)
- Running Evaluations
- MCP Server Evaluation Guide
- MCP Server Best Practices
- 🚀 High-Level Workflow
- MCPConnection
- evaluation.py
- connections.py
- _sample_index
- ableton_device_params
- ableton_load_device
- ableton_load_sample

## God Nodes (most connected - your core abstractions)
1. `AbletonClaude` - 45 edges
2. `call_live()` - 23 edges
3. `Node/TypeScript MCP Server Implementation Guide` - 21 edges
4. `Python MCP Server Implementation Guide` - 18 edges
5. `Node/TypeScript MCP Server Implementation Guide (SDK v2)` - 14 edges
6. `MCPConnection` - 13 edges
7. `MCP Server Evaluation Guide` - 12 edges
8. `MCP Server Best Practices` - 12 edges
9. `_attr_list()` - 10 edges
10. `_get_state()` - 10 edges

## Surprising Connections (you probably didn't know these)
- `AbletonClaude` --inherits--> `ControlSurface`  [EXTRACTED]
  remote_script/AbletonClaude/__init__.py → tests/test_sin_ableton.py
- `main()` --calls--> `create_connection()`  [EXTRACTED]
  .claude/skills/mcp-builder/scripts/evaluation.py → .claude/skills/mcp-builder/scripts/connections.py
- `_measure()` --calls--> `analyze()`  [EXTRACTED]
  server/server.py → server/analysis.py
- `ableton_compare_reference()` --calls--> `compare()`  [EXTRACTED]
  server/server.py → server/analysis.py
- `main()` --calls--> `write_adg()`  [EXTRACTED]
  server/batch_presets.py → server/preset_gen.py

## Import Cycles
- None detected.

## Communities (24 total, 7 thin omitted)

### Community 0 - "tool"
Cohesion: 0.09
Nodes (16): ableton_add_notes(), ableton_arrange_clear(), ableton_arrange_clip(), ableton_arrange_list(), ableton_clip_props(), ableton_create_clip(), ableton_create_track(), ableton_delete_clip() (+8 more)

### Community 2 - "server.py"
Cohesion: 0.14
Nodes (10): ableton_add_reference(), ableton_analyze_audio(), ableton_compare_reference(), ableton_get_profile(), ableton_set_profile(), _inventory(), _load(), _measure() (+2 more)

### Community 3 - "vst3_scan.py"
Cohesion: 0.08
Nodes (14): _attr_list(), _call(), _com(), qi(), _create_instance(), dll_path(), _get_state(), _make_host() (+6 more)

### Community 4 - "evaluation.py"
Cohesion: 0.09
Nodes (13): create_instance(), _parse_display(), analyze(), _graph(), _num(), parse(), find_plugins(), main() (+5 more)

### Community 5 - "agent_loop"
Cohesion: 0.23
Nodes (4): agent_loop(), evaluate_single_task(), parse_evaluation_file(), run_evaluation()

### Community 6 - "test_sin_ableton.py"
Cohesion: 0.10
Nodes (8): compare(), _arr_clip(), Clip, Obj, Param, Slot, track(), vol_fmt()

### Community 7 - "Node/TypeScript MCP Server Implementation Guide"
Cohesion: 0.05
Nodes (41): Advanced Features (where applicable), Advanced MCP Features, Async/Await Best Practices, Building and Running, Character Limits and Truncation, Code Best Practices, Code Composability and Reusability, Code Quality (+33 more)

### Community 9 - "Python MCP Server Implementation Guide"
Cohesion: 0.06
Nodes (36): Advanced FastMCP Features, Advanced Features (where applicable), Async/Await Best Practices, Code Best Practices, Code Composability and Reusability, Code Quality, Complete Example, Context Parameter Injection (+28 more)

### Community 10 - "Node/TypeScript MCP Server Implementation Guide (SDK v2)"
Cohesion: 0.06
Nodes (33): A Server in One Screen, Annotations, Authentication, Calling the Upstream API, Character Limit, Complete Example, Designing Tools, Errors (+25 more)

### Community 11 - "Running Evaluations"
Cohesion: 0.07
Nodes (23): 1. Local STDIO Server, 2. Server-Sent Events (SSE), 3. HTTP (Streamable HTTP), Command-Line Options, Complete Example Workflow, Connection Errors, Evaluation File Format, Low Accuracy (+15 more)

### Community 12 - "MCP Server Evaluation Guide"
Cohesion: 0.07
Nodes (29): Answer Guidelines, Complexity and Depth, Core Requirements, Diversity, Evaluation Examples, Evaluation Overview, Evaluation Process, Evaluation Requirements (+21 more)

### Community 13 - "MCP Server Best Practices"
Cohesion: 0.07
Nodes (28): Authentication and Authorization, DNS Rebinding Protection, Documentation Requirements, Error Handling, Error Handling, Input Validation, JSON Format (`response_format="json"`), Markdown Format (`response_format="markdown"`, typically default) (+20 more)

### Community 14 - "🚀 High-Level Workflow"
Cohesion: 0.11
Nodes (19): 1.1 Understand Modern MCP Design, 1.2 Study MCP Protocol Documentation, 1.3 Study Framework Documentation, 1.4 Plan Your Implementation, 2.1 Set Up Project Structure, 2.2 Implement Core Infrastructure, 2.3 Implement Tools, 3.1 Code Quality (+11 more)

### Community 15 - "MCPConnection"
Cohesion: 0.13
Nodes (5): create_connection(), MCPConnection, MCPConnectionHTTP, MCPConnectionSSE, MCPConnectionStdio

### Community 16 - "evaluation.py"
Cohesion: 0.23
Nodes (4): extract_xml_content(), main(), parse_env_vars(), parse_headers()

### Community 18 - "_sample_index"
Cohesion: 0.25
Nodes (5): ableton_find_samples(), ableton_scan_samples(), _classify(), _library_summary(), _sample_index()

### Community 19 - "ableton_device_params"
Cohesion: 0.29
Nodes (3): ableton_device_params(), ableton_set_device_param(), ableton_set_mixer()

## Knowledge Gaps
- **2 isolated node(s):** `uv`, `ableton-mcp`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 295 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AbletonClaude` connect `AbletonClaude` to `evaluation.py`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._
- **What connects `uv`, `ableton-mcp` to the rest of the system?**
  _2 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `tool` be split into smaller, more focused modules?**
  _Cohesion score 0.0907258064516129 - nodes in this community are weakly interconnected._
- **Why does `Node/TypeScript MCP Server Implementation Guide` connect `Node/TypeScript MCP Server Implementation Guide` to `Running Evaluations`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Should `AbletonClaude` be split into smaller, more focused modules?**
  _Cohesion score 0.05909090909090909 - nodes in this community are weakly interconnected._
- **Why does `Python MCP Server Implementation Guide` connect `Python MCP Server Implementation Guide` to `Running Evaluations`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Should `server.py` be split into smaller, more focused modules?**
  _Cohesion score 0.13852813852813853 - nodes in this community are weakly interconnected._