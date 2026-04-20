from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Literal

from .config import AnalyzerConfig
from .constants import DEFAULT_EXCLUDED_DIRS
from .errors import ConfigurationError, DependencyUnavailableError
from .models import (
    CodeSnippet,
    CompilationUnit,
    CompletionInfo,
    HoverInfo,
    Location,
    Position,
    PreflightResult,
    SourceFileInfo,
    SymbolContext,
    SymbolInfo,
    WorkspaceFileIndex,
    WorkspaceIndex,
)

FileSource = Literal["database", "filesystem", "merged"]


def _detect_language(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".h", ".hh", ".hpp", ".hxx", ".inc", ".ipp", ".tpp"}:
        return "header"
    if suffix == ".c":
        return "c"
    if suffix in {".m", ".mm"}:
        return "objective-c"
    return "cpp"


def _flatten_hover_contents(contents: Any) -> tuple[str, str | None]:
    if isinstance(contents, str):
        return contents, None
    if isinstance(contents, dict):
        return str(contents.get("value", "")), contents.get("kind")
    if isinstance(contents, list):
        parts = []
        kinds: list[str] = []
        for item in contents:
            text, kind = _flatten_hover_contents(item)
            if text:
                parts.append(text)
            if kind:
                kinds.append(kind)
        return "\n\n".join(parts), kinds[0] if kinds else None
    return str(contents), None


def _detect_clangd_version(clangd_path: str | None) -> tuple[str | None, int | None]:
    if not clangd_path or not Path(clangd_path).exists():
        return None, None
    try:
        result = subprocess.run(
            [clangd_path, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None, None

    first_line = (result.stdout or result.stderr).strip().splitlines()
    version_text = first_line[0] if first_line else None
    match = re.search(r"clangd version (\d+)", version_text or "")
    major = int(match.group(1)) if match else None
    return version_text, major


class AsyncCodebaseAnalyzer:
    def __init__(self, config: AnalyzerConfig) -> None:
        self.config = config
        self._lsp = None
        self._start_server_cm = None
        self._started = False
        self._file_cache: dict[str, str] = {}
        self._document_symbol_cache: dict[str, list[SymbolInfo]] = {}
        self._compilation_units_cache: list[CompilationUnit] | None = None

    @classmethod
    def from_root(cls, project_root: str | Path, **kwargs: Any) -> "AsyncCodebaseAnalyzer":
        return cls(AnalyzerConfig(project_root=project_root, **kwargs))

    def preflight(self) -> PreflightResult:
        clangd_path = self.config.resolve_clangd_path()
        clangd_version, clangd_major = _detect_clangd_version(clangd_path)
        compile_commands_path = self.config.resolve_compile_commands_path()
        return PreflightResult(
            project_root=str(self.config.project_root),
            clangd_path=clangd_path,
            clangd_version=clangd_version,
            clangd_major=clangd_major,
            clangd_compatible=None if clangd_major is None else clangd_major >= 18,
            compile_commands_path=str(compile_commands_path) if compile_commands_path else None,
            has_clangd=bool(clangd_path and Path(clangd_path).exists()),
            has_compile_commands=bool(compile_commands_path and compile_commands_path.exists()),
        )

    async def start(self) -> "AsyncCodebaseAnalyzer":
        if self._started:
            return self

        self.config.validate()
        preflight = self.preflight()
        if preflight.has_clangd and preflight.clangd_major is not None and preflight.clangd_major < 18:
            raise DependencyUnavailableError(
                f"Detected {preflight.clangd_version}. "
                "multilspy's C/C++ support currently requires clangd >= 18."
            )
        try:
            from multilspy import LanguageServer
            from multilspy.multilspy_logger import MultilspyLogger
        except ImportError as exc:
            raise DependencyUnavailableError(
                "multilspy is not installed. Install the project dependencies first."
            ) from exc

        logger = MultilspyLogger()
        self._lsp = LanguageServer.create(
            self.config.to_multilspy_config(),
            logger,
            str(self.config.project_root),
        )
        self._start_server_cm = self._lsp.start_server()
        await self._start_server_cm.__aenter__()
        self._started = True
        return self

    async def close(self) -> None:
        if not self._started or self._start_server_cm is None:
            return
        await self._start_server_cm.__aexit__(None, None, None)
        self._started = False
        self._start_server_cm = None
        self._lsp = None

    async def __aenter__(self) -> "AsyncCodebaseAnalyzer":
        return await self.start()

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        await self.close()

    def clear_caches(self) -> None:
        self._file_cache.clear()
        self._document_symbol_cache.clear()
        self._compilation_units_cache = None

    def _ensure_started(self) -> None:
        if not self._started or self._lsp is None:
            raise RuntimeError("Analyzer session has not been started. Use it inside an async or sync context manager.")

    def _normalize_relative_path(self, relative_path: str) -> str:
        candidate = Path(relative_path)
        root = self.config.project_root
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (root / candidate).resolve()
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ConfigurationError(f"Path is outside the project root: {relative_path}") from exc

    def _read_text(self, relative_path: str) -> str:
        relative_path = self._normalize_relative_path(relative_path)
        if relative_path not in self._file_cache:
            absolute_path = self.config.project_root / relative_path
            self._file_cache[relative_path] = absolute_path.read_text(encoding="utf-8")
        return self._file_cache[relative_path]

    def _source_file_info(self, relative_path: str, from_database: bool) -> SourceFileInfo:
        relative_path = self._normalize_relative_path(relative_path)
        absolute_path = (self.config.project_root / relative_path).resolve()
        text = self._read_text(relative_path)
        line_count = len(text.splitlines()) or 1
        return SourceFileInfo(
            relative_path=relative_path,
            absolute_path=str(absolute_path),
            language=_detect_language(absolute_path),
            line_count=line_count,
            from_compilation_database=from_database,
        )

    def _walk_filesystem_sources(self) -> list[str]:
        root = self.config.project_root
        results: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                name for name in dirnames
                if name not in DEFAULT_EXCLUDED_DIRS and not name.startswith(".")
            ]
            for filename in filenames:
                path = Path(dirpath) / filename
                if path.suffix.lower() in self.config.all_suffixes:
                    results.append(path.relative_to(root).as_posix())
        return sorted(set(results))

    def get_compilation_units(self) -> list[CompilationUnit]:
        if self._compilation_units_cache is not None:
            return list(self._compilation_units_cache)

        self.config.validate()
        path = self.config.resolve_compile_commands_path()
        assert path is not None
        payload = json.loads(path.read_text(encoding="utf-8"))

        units: list[CompilationUnit] = []
        for entry in payload:
            file_path = Path(entry["file"])
            if not file_path.is_absolute():
                file_path = (Path(entry["directory"]) / file_path).resolve()
            else:
                file_path = file_path.resolve()

            try:
                relative_path = file_path.relative_to(self.config.project_root).as_posix()
            except ValueError:
                relative_path = None

            units.append(
                CompilationUnit(
                    directory=entry["directory"],
                    command=entry["command"],
                    file=entry["file"],
                    absolute_path=str(file_path),
                    relative_path=relative_path,
                )
            )

        units.sort(key=lambda item: item.relative_path or item.absolute_path)
        self._compilation_units_cache = units
        return list(units)

    def list_source_files(self, source: FileSource = "merged", limit: int | None = None) -> list[SourceFileInfo]:
        db_paths = {
            unit.relative_path for unit in self.get_compilation_units() if unit.relative_path is not None
        }
        fs_paths = set(self._walk_filesystem_sources())

        if source == "database":
            relative_paths = sorted(db_paths)
        elif source == "filesystem":
            relative_paths = sorted(fs_paths)
        else:
            relative_paths = sorted(db_paths | fs_paths)

        if limit is not None:
            relative_paths = relative_paths[:limit]

        return [self._source_file_info(path, path in db_paths) for path in relative_paths]

    def read_file(self, relative_path: str) -> str:
        return self._read_text(relative_path)

    def get_snippet(self, relative_path: str, start_line: int, end_line: int) -> CodeSnippet:
        if start_line < 1 or end_line < start_line:
            raise ValueError("Snippet lines are 1-based and must satisfy 1 <= start_line <= end_line.")

        relative_path = self._normalize_relative_path(relative_path)
        absolute_path = str((self.config.project_root / relative_path).resolve())
        lines = self._read_text(relative_path).splitlines()
        bounded_end_line = min(end_line, len(lines))
        snippet_lines = lines[start_line - 1:bounded_end_line]
        text = "\n".join(snippet_lines)
        numbered_text = "\n".join(
            f"{line_no:>4}: {content}"
            for line_no, content in zip(range(start_line, bounded_end_line + 1), snippet_lines)
        )
        return CodeSnippet(
            relative_path=relative_path,
            absolute_path=absolute_path,
            start_line=start_line,
            end_line=bounded_end_line,
            text=text,
            numbered_text=numbered_text,
        )

    async def get_document_symbols(self, relative_path: str, use_cache: bool = True) -> list[SymbolInfo]:
        self._ensure_started()
        relative_path = self._normalize_relative_path(relative_path)
        if use_cache and relative_path in self._document_symbol_cache:
            return list(self._document_symbol_cache[relative_path])

        raw_symbols, _ = await self._lsp.request_document_symbols(relative_path)
        symbols = [
            SymbolInfo.from_multilspy(symbol, self.config.project_root, fallback_relative_path=relative_path)
            for symbol in raw_symbols
        ]
        if use_cache:
            self._document_symbol_cache[relative_path] = symbols
        return list(symbols)

    async def get_workspace_symbols(self, query: str, limit: int | None = 50) -> list[SymbolInfo]:
        self._ensure_started()
        raw_symbols = await self._lsp.request_workspace_symbol(query) or []
        symbols = [SymbolInfo.from_multilspy(symbol, self.config.project_root) for symbol in raw_symbols]
        if limit is not None:
            symbols = symbols[:limit]
        return symbols

    async def find_symbol(
        self,
        name: str,
        exact: bool = False,
        limit: int = 20,
    ) -> list[SymbolInfo]:
        symbols = await self.get_workspace_symbols(name, limit=max(limit * 3, limit))

        def rank(symbol: SymbolInfo) -> tuple[int, str]:
            if symbol.name == name:
                return (0, symbol.name)
            if symbol.name.startswith(name):
                return (1, symbol.name)
            return (2, symbol.name)

        symbols.sort(key=rank)
        if exact:
            symbols = [symbol for symbol in symbols if symbol.name == name]
        return symbols[:limit]

    async def get_definition(self, relative_path: str, line: int, column: int) -> list[Location]:
        self._ensure_started()
        position = Position(line=line, column=column).to_lsp()
        relative_path = self._normalize_relative_path(relative_path)
        raw_locations = await self._lsp.request_definition(relative_path, position["line"], position["character"])
        return [Location.from_lsp(item) for item in raw_locations]

    async def get_references(
        self,
        relative_path: str,
        line: int,
        column: int,
        limit: int | None = None,
    ) -> list[Location]:
        self._ensure_started()
        position = Position(line=line, column=column).to_lsp()
        relative_path = self._normalize_relative_path(relative_path)
        raw_locations = await self._lsp.request_references(relative_path, position["line"], position["character"])
        locations = [Location.from_lsp(item) for item in raw_locations]
        if limit is not None:
            locations = locations[:limit]
        return locations

    async def get_hover(self, relative_path: str, line: int, column: int) -> HoverInfo | None:
        self._ensure_started()
        position = Position(line=line, column=column).to_lsp()
        relative_path = self._normalize_relative_path(relative_path)
        raw_hover = await self._lsp.request_hover(relative_path, position["line"], position["character"])
        if raw_hover is None:
            return None
        contents, markup_kind = _flatten_hover_contents(raw_hover["contents"])
        return HoverInfo(
            contents=contents,
            markup_kind=markup_kind,
            range=Location.from_relative_range(
                self.config.project_root,
                relative_path,
                raw_hover["range"],
            ).range if raw_hover.get("range") else None,
        )

    async def get_completions(
        self,
        relative_path: str,
        line: int,
        column: int,
        limit: int | None = 20,
    ) -> list[CompletionInfo]:
        self._ensure_started()
        position = Position(line=line, column=column).to_lsp()
        relative_path = self._normalize_relative_path(relative_path)
        raw_items = await self._lsp.request_completions(relative_path, position["line"], position["character"])
        items = [CompletionInfo.from_multilspy(item) for item in raw_items]
        if limit is not None:
            items = items[:limit]
        return items

    async def inspect_symbol(
        self,
        relative_path: str,
        line: int,
        column: int,
        reference_limit: int = 20,
        snippet_radius: int = 8,
    ) -> SymbolContext:
        self._ensure_started()
        relative_path = self._normalize_relative_path(relative_path)
        hover_task = asyncio.create_task(self.get_hover(relative_path, line, column))
        definition_task = asyncio.create_task(self.get_definition(relative_path, line, column))
        reference_task = asyncio.create_task(
            self.get_references(relative_path, line, column, limit=reference_limit)
        )
        symbol_task = asyncio.create_task(self.get_document_symbols(relative_path))

        hover = await hover_task
        definitions = await definition_task
        references = await reference_task
        symbols = await symbol_task

        snippet = self.get_snippet(
            relative_path,
            start_line=max(1, line - snippet_radius),
            end_line=line + snippet_radius,
        )
        nearby_symbols = [
            symbol for symbol in symbols
            if symbol.location and symbol.location.range.contains_line(line)
        ]
        if not nearby_symbols:
            nearby_symbols = [
                symbol for symbol in symbols
                if symbol.location and snippet.start_line <= symbol.location.range.start.line <= snippet.end_line
            ]

        return SymbolContext(
            relative_path=relative_path,
            line=line,
            column=column,
            snippet=snippet,
            hover=hover,
            definitions=definitions,
            references=references,
            nearby_symbols=nearby_symbols[:20],
        )

    async def build_workspace_index(
        self,
        include_symbols: bool = True,
        file_limit: int | None = None,
        symbol_limit_per_file: int | None = None,
    ) -> WorkspaceIndex:
        self._ensure_started()
        files = self.list_source_files(limit=file_limit)
        indexed_files: list[WorkspaceFileIndex] = []
        failures: list[str] = []

        for file_info in files:
            symbols: list[SymbolInfo] = []
            if include_symbols:
                try:
                    symbols = await self.get_document_symbols(file_info.relative_path)
                    if symbol_limit_per_file is not None:
                        symbols = symbols[:symbol_limit_per_file]
                except Exception as exc:  # pragma: no cover
                    failures.append(f"{file_info.relative_path}: {exc}")
            indexed_files.append(WorkspaceFileIndex(file=file_info, symbols=symbols))

        compile_commands_path = self.config.resolve_compile_commands_path()
        return WorkspaceIndex(
            root_path=str(self.config.project_root),
            compile_commands_path=str(compile_commands_path),
            files=indexed_files,
            failures=failures,
        )


class SyncCodebaseAnalyzer:
    def __init__(self, config: AnalyzerConfig) -> None:
        self.config = config
        self._async_analyzer = AsyncCodebaseAnalyzer(config)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = False

    @classmethod
    def from_root(cls, project_root: str | Path, **kwargs: Any) -> "SyncCodebaseAnalyzer":
        return cls(AnalyzerConfig(project_root=project_root, **kwargs))

    def _ensure_loop(self) -> None:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()

    def _run(self, coroutine):  # type: ignore[no-untyped-def]
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is not None and running_loop.is_running():
            raise RuntimeError(
                "SyncCodebaseAnalyzer cannot be used inside a running event loop. "
                "Use AsyncCodebaseAnalyzer instead."
            )

        self._ensure_loop()
        assert self._loop is not None
        return self._loop.run_until_complete(coroutine)

    def start(self) -> "SyncCodebaseAnalyzer":
        if not self._started:
            self._run(self._async_analyzer.start())
            self._started = True
        return self

    def close(self) -> None:
        if self._started:
            self._run(self._async_analyzer.close())
            self._started = False
        if self._loop is not None and not self._loop.is_closed():
            self._loop.close()

    def __enter__(self) -> "SyncCodebaseAnalyzer":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def preflight(self) -> PreflightResult:
        return self._async_analyzer.preflight()

    def clear_caches(self) -> None:
        self._async_analyzer.clear_caches()

    def get_compilation_units(self) -> list[CompilationUnit]:
        return self._async_analyzer.get_compilation_units()

    def list_source_files(self, source: FileSource = "merged", limit: int | None = None) -> list[SourceFileInfo]:
        return self._async_analyzer.list_source_files(source=source, limit=limit)

    def read_file(self, relative_path: str) -> str:
        return self._async_analyzer.read_file(relative_path)

    def get_snippet(self, relative_path: str, start_line: int, end_line: int) -> CodeSnippet:
        return self._async_analyzer.get_snippet(relative_path, start_line, end_line)

    def get_document_symbols(self, relative_path: str, use_cache: bool = True) -> list[SymbolInfo]:
        self.start()
        return self._run(self._async_analyzer.get_document_symbols(relative_path, use_cache=use_cache))

    def get_workspace_symbols(self, query: str, limit: int | None = 50) -> list[SymbolInfo]:
        self.start()
        return self._run(self._async_analyzer.get_workspace_symbols(query, limit=limit))

    def find_symbol(self, name: str, exact: bool = False, limit: int = 20) -> list[SymbolInfo]:
        self.start()
        return self._run(self._async_analyzer.find_symbol(name, exact=exact, limit=limit))

    def get_definition(self, relative_path: str, line: int, column: int) -> list[Location]:
        self.start()
        return self._run(self._async_analyzer.get_definition(relative_path, line, column))

    def get_references(
        self,
        relative_path: str,
        line: int,
        column: int,
        limit: int | None = None,
    ) -> list[Location]:
        self.start()
        return self._run(self._async_analyzer.get_references(relative_path, line, column, limit=limit))

    def get_hover(self, relative_path: str, line: int, column: int) -> HoverInfo | None:
        self.start()
        return self._run(self._async_analyzer.get_hover(relative_path, line, column))

    def get_completions(
        self,
        relative_path: str,
        line: int,
        column: int,
        limit: int | None = 20,
    ) -> list[CompletionInfo]:
        self.start()
        return self._run(self._async_analyzer.get_completions(relative_path, line, column, limit=limit))

    def inspect_symbol(
        self,
        relative_path: str,
        line: int,
        column: int,
        reference_limit: int = 20,
        snippet_radius: int = 8,
    ) -> SymbolContext:
        self.start()
        return self._run(
            self._async_analyzer.inspect_symbol(
                relative_path,
                line,
                column,
                reference_limit=reference_limit,
                snippet_radius=snippet_radius,
            )
        )

    def build_workspace_index(
        self,
        include_symbols: bool = True,
        file_limit: int | None = None,
        symbol_limit_per_file: int | None = None,
    ) -> WorkspaceIndex:
        self.start()
        return self._run(
            self._async_analyzer.build_workspace_index(
                include_symbols=include_symbols,
                file_limit=file_limit,
                symbol_limit_per_file=symbol_limit_per_file,
            )
        )
