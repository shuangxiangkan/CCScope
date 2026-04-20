# CCScope API Reference

This document describes the public API exposed by CCScope.

The main Python import package is currently `cc_analyzer`.

## Main Entry Points

- `cc_analyzer.AsyncCodebaseAnalyzer`
- `cc_analyzer.SyncCodebaseAnalyzer`
- `cc_analyzer.LangGraphToolkit`

`SyncCodebaseAnalyzer` wraps the async analyzer and keeps a long-lived LSP session open under the hood so `clangd` does not need to restart on every query.

All location-based APIs use 1-based line and column numbers.

## `AsyncCodebaseAnalyzer`

### `AsyncCodebaseAnalyzer.from_root(project_root, **kwargs)`

Create an analyzer from a repository root.

Supported keyword arguments are forwarded to `AnalyzerConfig`, including:

- `clangd_path`
- `compile_commands_path`
- `trace_lsp_communication`
- `start_independent_lsp_process`
- `source_suffixes`
- `header_suffixes`

### `preflight() -> PreflightResult`

Check whether the workspace is ready for analysis.

Returns:

- `project_root`
- `clangd_path`
- `clangd_version`
- `clangd_major`
- `clangd_compatible`
- `compile_commands_path`
- `has_clangd`
- `has_compile_commands`

### `start() -> AsyncCodebaseAnalyzer`

Start the underlying `multilspy` / `clangd` session.

### `close() -> None`

Close the underlying LSP session.

### `clear_caches() -> None`

Clear in-memory file, symbol, and compilation-unit caches.

### `get_compilation_units() -> list[CompilationUnit]`

Parse `compile_commands.json` and return structured compilation units.

Each `CompilationUnit` contains:

- `directory`
- `command`
- `file`
- `absolute_path`
- `relative_path`

### `list_source_files(source="merged", limit=None) -> list[SourceFileInfo]`

List files from one of three views:

- `"database"`: only files found in `compile_commands.json`
- `"filesystem"`: only files discovered by walking the workspace
- `"merged"`: the union of both

Each `SourceFileInfo` contains:

- `relative_path`
- `absolute_path`
- `language`
- `line_count`
- `from_compilation_database`

### `read_file(relative_path) -> str`

Read a workspace file as plain text.

### `get_snippet(relative_path, start_line, end_line) -> CodeSnippet`

Return a line-numbered snippet.

`CodeSnippet` contains:

- `relative_path`
- `absolute_path`
- `start_line`
- `end_line`
- `text`
- `numbered_text`

### `get_document_symbols(relative_path, use_cache=True) -> list[SymbolInfo]`

Return symbols declared in a single file.

### `get_workspace_symbols(query, limit=50) -> list[SymbolInfo]`

Run a raw workspace-wide symbol query through the LSP workspace-symbol API.

### `find_symbol(name, exact=False, limit=20) -> list[SymbolInfo]`

Perform ranked symbol lookup:

- exact matches first
- prefix matches next
- remaining matches after that

### `get_definition(relative_path, line, column) -> list[Location]`

Resolve symbol definition locations.

### `get_references(relative_path, line, column, limit=None) -> list[Location]`

Resolve symbol reference locations.

### `get_hover(relative_path, line, column) -> HoverInfo | None`

Return hover text and optional range information.

### `get_completions(relative_path, line, column, limit=20) -> list[CompletionInfo]`

Return completion candidates at a source location.

### `inspect_symbol(relative_path, line, column, reference_limit=20, snippet_radius=8) -> SymbolContext`

Build a symbol-centered payload suitable for LLM consumption.

`SymbolContext` contains:

- `relative_path`
- `line`
- `column`
- `snippet`
- `hover`
- `definitions`
- `references`
- `nearby_symbols`

### `build_workspace_index(include_symbols=True, file_limit=None, symbol_limit_per_file=None) -> WorkspaceIndex`

Build a serializable workspace snapshot for offline indexing or caching.

`WorkspaceIndex` contains:

- `root_path`
- `compile_commands_path`
- `files`
- `failures`

## `SyncCodebaseAnalyzer`

`SyncCodebaseAnalyzer` exposes the same analysis methods as `AsyncCodebaseAnalyzer`, but as synchronous methods:

- `from_root(...)`
- `start()`
- `close()`
- `preflight()`
- `clear_caches()`
- `get_compilation_units()`
- `list_source_files(...)`
- `read_file(...)`
- `get_snippet(...)`
- `get_document_symbols(...)`
- `get_workspace_symbols(...)`
- `find_symbol(...)`
- `get_definition(...)`
- `get_references(...)`
- `get_hover(...)`
- `get_completions(...)`
- `inspect_symbol(...)`
- `build_workspace_index(...)`

Typical usage:

```python
from cc_analyzer import SyncCodebaseAnalyzer


with SyncCodebaseAnalyzer.from_root("tests/cJSON") as analyzer:
    symbol_hits = analyzer.find_symbol("cJSON_Parse", exact=True, limit=5)
    print([item.to_dict() for item in symbol_hits])
```

## `LangGraphToolkit`

`LangGraphToolkit` is a thin integration layer over `SyncCodebaseAnalyzer`.
It returns plain dictionaries so the outputs are easy to pass through tools and agents.

### Constructor

#### `LangGraphToolkit(analyzer: SyncCodebaseAnalyzer)`

Create a toolkit from an existing sync analyzer.

### Tool Methods

#### `preflight() -> dict[str, Any]`

Return the serialized preflight payload.

#### `get_compilation_units() -> dict[str, Any]`

Return serialized compilation units.

#### `list_source_files(source="merged", limit=200) -> dict[str, Any]`

Return serialized file metadata.

#### `read_file(relative_path) -> dict[str, Any]`

Return:

- `relative_path`
- `text`

#### `get_snippet(relative_path, start_line, end_line) -> dict[str, Any]`

Return a serialized `CodeSnippet`.

#### `get_document_symbols(relative_path) -> dict[str, Any]`

Return:

- `count`
- `items`

#### `get_workspace_symbols(query, limit=50) -> dict[str, Any]`

Return:

- `count`
- `items`

#### `find_symbol(name, exact=False, limit=20) -> dict[str, Any]`

Return ranked symbol hits.

#### `get_definition(relative_path, line, column) -> dict[str, Any]`

Return resolved definitions.

#### `get_references(relative_path, line, column, limit=50) -> dict[str, Any]`

Return resolved references.

#### `get_hover(relative_path, line, column) -> dict[str, Any]`

Return serialized hover data.

#### `get_completions(relative_path, line, column, limit=20) -> dict[str, Any]`

Return serialized completion items.

#### `inspect_symbol(relative_path, line, column, reference_limit=20, snippet_radius=8) -> dict[str, Any]`

Return a serialized `SymbolContext`.

#### `build_workspace_index(include_symbols=True, file_limit=100, symbol_limit_per_file=50) -> dict[str, Any]`

Return a serialized `WorkspaceIndex`.

### Tool Export Helpers

#### `as_tool_functions() -> list[Callable[..., dict[str, Any]]]`

Return plain Python callables suitable for custom orchestration.

#### `as_langchain_tools()`

Wrap the tool functions with LangChain’s `tool` decorator and return LangChain-compatible tool objects.

This requires `langchain-core` through the optional agent dependencies.

## Return Models

The structured return models are defined in `src/cc_analyzer/models.py`.

Important models:

- `PreflightResult`
- `CompilationUnit`
- `SourceFileInfo`
- `Position`
- `Range`
- `Location`
- `SymbolInfo`
- `HoverInfo`
- `CompletionInfo`
- `CodeSnippet`
- `SymbolContext`
- `WorkspaceFileIndex`
- `WorkspaceIndex`

Each model exposes `to_dict()` for JSON-friendly serialization.

## LangChain Example

```python
from cc_analyzer import LangGraphToolkit, SyncCodebaseAnalyzer
from langchain.agents import create_agent


with SyncCodebaseAnalyzer.from_root("tests/cJSON") as analyzer:
    toolkit = LangGraphToolkit(analyzer)
    tools = toolkit.as_langchain_tools()

    agent = create_agent(
        model="openai:gpt-4.1",
        tools=tools,
        system_prompt=(
            "You are a C code analysis assistant. "
            "Always inspect the repository before making claims."
        ),
    )

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Find where cJSON_Parse is defined and summarize the surrounding logic.",
                }
            ]
        }
    )

    print(result)
```

## LangGraph Example

```python
from typing_extensions import TypedDict
from langgraph.graph import END, START, StateGraph

from cc_analyzer import LangGraphToolkit, SyncCodebaseAnalyzer


class AnalysisState(TypedDict):
    symbol_name: str
    findings: dict


with SyncCodebaseAnalyzer.from_root("tests/cJSON") as analyzer:
    toolkit = LangGraphToolkit(analyzer)

    def lookup_symbol(state: AnalysisState) -> AnalysisState:
        return {
            "findings": toolkit.find_symbol(state["symbol_name"], exact=True, limit=5)
        }

    graph = StateGraph(AnalysisState)
    graph.add_node("lookup_symbol", lookup_symbol)
    graph.add_edge(START, "lookup_symbol")
    graph.add_edge("lookup_symbol", END)
    app = graph.compile()

    result = app.invoke({"symbol_name": "cJSON_Parse", "findings": {}})
    print(result)
```
