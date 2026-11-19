# Graph Report - Ableton MCP  (2026-11-14)

## Corpus Check
- 20 files · ~31,120 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: .xml 2, (none) 1, .lock 1)

## Summary
- 562 nodes · 829 edges · 28 communities (19 shown, 9 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 29 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9a525125`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- tool
- AbletonClaude
- _load
- vst3_scan.py
- evaluation.py
- connections.py
- test_sin_ableton.py
- Node/TypeScript MCP Server Implementation Guide
- ableton-mcp
- Python MCP Server Implementation Guide
- Node/TypeScript MCP Server Implementation Guide (SDK v2)
- Running Evaluations
- MCP Server Evaluation Guide
- MCP Server Best Practices
- 🚀 High-Level Workflow
- evaluation.py
- .cmd_arrange_automation
- server.py
- ableton_device_params
- Ableton MCP
- ableton_compare_reference
- ControlSurface
- __init__.py

## God Nodes (most connected - your core abstractions)
1. `AbletonClaude` - 53 edges
2. `call_live()` - 27 edges
3. `Node/TypeScript MCP Server Implementation Guide` - 21 edges
4. `Python MCP Server Implementation Guide` - 18 edges
5. `Node/TypeScript MCP Server Implementation Guide (SDK v2)` - 14 edges
6. `MCPConnection` - 13 edges
7. `MCP Server Evaluation Guide` - 12 edges
8. `MCP Server Best Practices` - 12 edges
9. `_attr_list()` - 10 edges
10. `_get_state()` - 10 edges

## Surprising Connections (you probably didn't know these)
- `Medir el master sin exportar` --references--> `ableton_record_master()`  [INFERRED]
  README.md → server/server.py
- `Medir el master sin exportar` --references--> `ableton_reload_set()`  [INFERRED]
  README.md → server/server.py
- `Medir el master sin exportar` --references--> `ableton_analyze_audio()`  [INFERRED]
  README.md → server/server.py
- `Medir el master sin exportar` --references--> `ableton_compare_reference()`  [INFERRED]
  README.md → server/server.py
- `AbletonClaude` --inherits--> `ControlSurface`  [EXTRACTED]
  remote_script/AbletonClaude/__init__.py → tests/test_sin_ableton.py

## Import Cycles
- None detected.

## Communities (28 total, 9 thin omitted)

### Community 0 - "tool"
Cohesion: 0.09
Nodes (17): ableton_add_notes(), ableton_arrange_automation(), ableton_arrange_clear(), ableton_arrange_clip(), ableton_arrange_list(), ableton_clip_props(), ableton_create_clip(), ableton_create_track() (+9 more)

### Community 2 - "_load"
Cohesion: 0.20
Nodes (7): ableton_add_reference(), ableton_get_profile(), ableton_set_profile(), _inventory(), _load(), _safe(), _save_profile()

### Community 3 - "vst3_scan.py"
Cohesion: 0.08
Nodes (14): _attr_list(), _call(), _com(), qi(), _create_instance(), dll_path(), _get_state(), _make_host() (+6 more)

### Community 4 - "evaluation.py"
Cohesion: 0.10
Nodes (14): analyze(), compare(), _graph(), _num(), parse(), find_plugins(), main(), safe_name() (+6 more)

### Community 5 - "connections.py"
Cohesion: 0.07
Nodes (7): create_connection(), MCPConnection, MCPConnectionHTTP, MCPConnectionSSE, MCPConnectionStdio, uv, ableton

### Community 6 - "test_sin_ableton.py"
Cohesion: 0.11
Nodes (9): _arr_clip(), Clip, main(), new_audio(), Obj, Param, Slot, track() (+1 more)

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

### Community 16 - "evaluation.py"
Cohesion: 0.14
Nodes (8): agent_loop(), evaluate_single_task(), extract_xml_content(), main(), parse_env_vars(), parse_evaluation_file(), parse_headers(), run_evaluation()

### Community 17 - ".cmd_arrange_automation"
Cohesion: 0.24
Nodes (3): finish(), finish(), tick()

### Community 18 - "server.py"
Cohesion: 0.14
Nodes (9): ableton_find_samples(), ableton_load_sample(), ableton_scan_samples(), _classify(), _is_loop(), _library_summary(), _sample_index(), _user_folders() (+1 more)

### Community 19 - "ableton_device_params"
Cohesion: 0.17
Nodes (5): ableton_device_params(), ableton_list_browser(), ableton_load_device(), ableton_set_device_param(), ableton_set_mixer()

### Community 22 - "Ableton MCP"
Cohesion: 0.33
Nodes (5): Ableton MCP, Instalacion, Limites conocidos, Pruebas, Requisitos

### Community 24 - "ableton_compare_reference"
Cohesion: 0.18
Nodes (7): Medir el master sin exportar, ableton_analyze_audio(), ableton_compare_reference(), ableton_record_master(), ableton_reload_set(), _measure(), _song_end()

## Knowledge Gaps
- **2 isolated node(s):** `uv`, `ableton-mcp`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 315 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AbletonClaude` connect `AbletonClaude` to `._device`, `.cmd_arrange_automation`, `._to_value`, `ControlSurface`, `.cmd_add_notes`, `._walk`, `__init__.py`, `._track`?**
  _High betweenness centrality (0.128) - this node is a cross-community bridge._
- **What connects `uv`, `ableton-mcp` to the rest of the system?**
  _2 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `tool` be split into smaller, more focused modules?**
  _Cohesion score 0.0855614973262032 - nodes in this community are weakly interconnected._
- **Why does `Node/TypeScript MCP Server Implementation Guide` connect `Node/TypeScript MCP Server Implementation Guide` to `Running Evaluations`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Should `AbletonClaude` be split into smaller, more focused modules?**
  _Cohesion score 0.13043478260869565 - nodes in this community are weakly interconnected._
- **Why does `Python MCP Server Implementation Guide` connect `Python MCP Server Implementation Guide` to `Running Evaluations`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Should `vst3_scan.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07823613086770982 - nodes in this community are weakly interconnected._