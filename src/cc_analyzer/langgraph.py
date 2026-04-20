from __future__ import annotations

from typing import Any, Callable

from .analyzer import SyncCodebaseAnalyzer


class LangGraphToolkit:
    """LangGraph-friendly wrapper around SyncCodebaseAnalyzer."""

    def __init__(self, analyzer: SyncCodebaseAnalyzer) -> None:
        self.analyzer = analyzer

    def preflight(self) -> dict[str, Any]:
        """Check whether clangd and compile_commands.json are available."""
        return self.analyzer.preflight().to_dict()

    def get_compilation_units(self) -> dict[str, Any]:
        """Return compilation units from compile_commands.json."""
        units = [item.to_dict() for item in self.analyzer.get_compilation_units()]
        return {"count": len(units), "items": units}

    def list_source_files(self, source: str = "merged", limit: int = 200) -> dict[str, Any]:
        """List source and header files in the workspace."""
        files = [item.to_dict() for item in self.analyzer.list_source_files(source=source, limit=limit)]
        return {"count": len(files), "items": files}

    def read_file(self, relative_path: str) -> dict[str, Any]:
        """Read a file from the workspace."""
        text = self.analyzer.read_file(relative_path)
        return {"relative_path": relative_path, "text": text}

    def get_snippet(self, relative_path: str, start_line: int, end_line: int) -> dict[str, Any]:
        """Read a line-numbered source snippet."""
        return self.analyzer.get_snippet(relative_path, start_line, end_line).to_dict()

    def get_document_symbols(self, relative_path: str) -> dict[str, Any]:
        """Return document symbols for a single file."""
        symbols = [item.to_dict() for item in self.analyzer.get_document_symbols(relative_path)]
        return {"count": len(symbols), "items": symbols}

    def get_workspace_symbols(self, query: str, limit: int = 50) -> dict[str, Any]:
        """Search workspace-wide symbols using a raw query string."""
        symbols = [item.to_dict() for item in self.analyzer.get_workspace_symbols(query, limit=limit)]
        return {"count": len(symbols), "items": symbols}

    def find_symbol(self, name: str, exact: bool = False, limit: int = 20) -> dict[str, Any]:
        """Find symbols in the workspace by name."""
        symbols = [item.to_dict() for item in self.analyzer.find_symbol(name, exact=exact, limit=limit)]
        return {"count": len(symbols), "items": symbols}

    def get_definition(self, relative_path: str, line: int, column: int) -> dict[str, Any]:
        """Resolve the definition(s) of the symbol at the given location."""
        items = [item.to_dict() for item in self.analyzer.get_definition(relative_path, line, column)]
        return {"count": len(items), "items": items}

    def get_references(
        self,
        relative_path: str,
        line: int,
        column: int,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Find references for the symbol at the given location."""
        items = [
            item.to_dict()
            for item in self.analyzer.get_references(relative_path, line, column, limit=limit)
        ]
        return {"count": len(items), "items": items}

    def get_hover(self, relative_path: str, line: int, column: int) -> dict[str, Any]:
        """Return hover information at the given location."""
        hover = self.analyzer.get_hover(relative_path, line, column)
        return hover.to_dict() if hover else {"contents": "", "markup_kind": None, "range": None}

    def get_completions(
        self,
        relative_path: str,
        line: int,
        column: int,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return completion candidates at the given location."""
        items = [
            item.to_dict()
            for item in self.analyzer.get_completions(relative_path, line, column, limit=limit)
        ]
        return {"count": len(items), "items": items}

    def inspect_symbol(
        self,
        relative_path: str,
        line: int,
        column: int,
        reference_limit: int = 20,
        snippet_radius: int = 8,
    ) -> dict[str, Any]:
        """Return a symbol-centered context payload suitable for LLM consumption."""
        return self.analyzer.inspect_symbol(
            relative_path,
            line,
            column,
            reference_limit=reference_limit,
            snippet_radius=snippet_radius,
        ).to_dict()

    def build_workspace_index(
        self,
        include_symbols: bool = True,
        file_limit: int = 100,
        symbol_limit_per_file: int = 50,
    ) -> dict[str, Any]:
        """Build a workspace index for offline scanning or initialization."""
        return self.analyzer.build_workspace_index(
            include_symbols=include_symbols,
            file_limit=file_limit,
            symbol_limit_per_file=symbol_limit_per_file,
        ).to_dict()

    def as_tool_functions(self) -> list[Callable[..., dict[str, Any]]]:
        return [
            self.preflight,
            self.get_compilation_units,
            self.list_source_files,
            self.read_file,
            self.get_snippet,
            self.get_document_symbols,
            self.get_workspace_symbols,
            self.find_symbol,
            self.get_definition,
            self.get_references,
            self.get_hover,
            self.get_completions,
            self.inspect_symbol,
            self.build_workspace_index,
        ]

    def as_langchain_tools(self):  # type: ignore[no-untyped-def]
        try:
            from langchain_core.tools import tool
        except ImportError as exc:
            raise RuntimeError(
                "langchain-core is not installed. Install it before creating LangChain/LangGraph tools."
            ) from exc
        return [tool(fn) for fn in self.as_tool_functions()]
