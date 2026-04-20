from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .constants import COMPLETION_KIND_NAMES, SYMBOL_KIND_NAMES


class Serializable:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Position(Serializable):
    line: int
    column: int

    @classmethod
    def from_lsp(cls, payload: dict[str, Any]) -> "Position":
        return cls(line=int(payload["line"]) + 1, column=int(payload["character"]) + 1)

    def to_lsp(self) -> dict[str, int]:
        if self.line < 1 or self.column < 1:
            raise ValueError("Public positions are 1-based. line/column must be >= 1.")
        return {"line": self.line - 1, "character": self.column - 1}


@dataclass(slots=True)
class Range(Serializable):
    start: Position
    end: Position

    @classmethod
    def from_lsp(cls, payload: dict[str, Any]) -> "Range":
        return cls(start=Position.from_lsp(payload["start"]), end=Position.from_lsp(payload["end"]))

    def contains_line(self, line: int) -> bool:
        return self.start.line <= line <= self.end.line


@dataclass(slots=True)
class Location(Serializable):
    absolute_path: str
    relative_path: str | None
    range: Range
    uri: str | None = None

    @classmethod
    def from_lsp(cls, payload: dict[str, Any]) -> "Location":
        return cls(
            absolute_path=payload["absolutePath"],
            relative_path=payload.get("relativePath"),
            range=Range.from_lsp(payload["range"]),
            uri=payload.get("uri"),
        )

    @classmethod
    def from_relative_range(
        cls,
        project_root: Path,
        relative_path: str,
        raw_range: dict[str, Any],
    ) -> "Location":
        absolute_path = str((project_root / relative_path).resolve())
        return cls(
            absolute_path=absolute_path,
            relative_path=relative_path,
            range=Range.from_lsp(raw_range),
            uri=Path(absolute_path).as_uri(),
        )


@dataclass(slots=True)
class SourceFileInfo(Serializable):
    relative_path: str
    absolute_path: str
    language: str
    line_count: int
    from_compilation_database: bool = False


@dataclass(slots=True)
class CompilationUnit(Serializable):
    directory: str
    command: str
    file: str
    absolute_path: str
    relative_path: str | None


@dataclass(slots=True)
class SymbolInfo(Serializable):
    name: str
    kind: int
    kind_name: str
    container_name: str | None = None
    detail: str | None = None
    location: Location | None = None
    range: Range | None = None
    selection_range: Range | None = None

    @classmethod
    def from_multilspy(
        cls,
        payload: dict[str, Any],
        project_root: Path,
        fallback_relative_path: str | None = None,
    ) -> "SymbolInfo":
        location = None
        if payload.get("location"):
            location = Location.from_lsp(payload["location"])
        elif payload.get("range") and fallback_relative_path:
            location = Location.from_relative_range(project_root, fallback_relative_path, payload["range"])

        return cls(
            name=payload["name"],
            kind=int(payload["kind"]),
            kind_name=SYMBOL_KIND_NAMES.get(int(payload["kind"]), f"Unknown({payload['kind']})"),
            container_name=payload.get("containerName"),
            detail=payload.get("detail"),
            location=location,
            range=Range.from_lsp(payload["range"]) if payload.get("range") else None,
            selection_range=Range.from_lsp(payload["selectionRange"]) if payload.get("selectionRange") else None,
        )


@dataclass(slots=True)
class HoverInfo(Serializable):
    contents: str
    markup_kind: str | None = None
    range: Range | None = None


@dataclass(slots=True)
class CompletionInfo(Serializable):
    completion_text: str
    kind: int
    kind_name: str
    detail: str | None = None

    @classmethod
    def from_multilspy(cls, payload: dict[str, Any]) -> "CompletionInfo":
        kind = int(payload["kind"])
        return cls(
            completion_text=payload["completionText"],
            kind=kind,
            kind_name=COMPLETION_KIND_NAMES.get(kind, f"Unknown({kind})"),
            detail=payload.get("detail"),
        )


@dataclass(slots=True)
class CodeSnippet(Serializable):
    relative_path: str
    absolute_path: str
    start_line: int
    end_line: int
    text: str
    numbered_text: str


@dataclass(slots=True)
class SymbolContext(Serializable):
    relative_path: str
    line: int
    column: int
    snippet: CodeSnippet
    hover: HoverInfo | None
    definitions: list[Location]
    references: list[Location]
    nearby_symbols: list[SymbolInfo]


@dataclass(slots=True)
class WorkspaceFileIndex(Serializable):
    file: SourceFileInfo
    symbols: list[SymbolInfo] = field(default_factory=list)


@dataclass(slots=True)
class WorkspaceIndex(Serializable):
    root_path: str
    compile_commands_path: str
    files: list[WorkspaceFileIndex]
    failures: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PreflightResult(Serializable):
    project_root: str
    clangd_path: str | None
    clangd_version: str | None
    clangd_major: int | None
    clangd_compatible: bool | None
    compile_commands_path: str | None
    has_clangd: bool
    has_compile_commands: bool
