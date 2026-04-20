from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .constants import HEADER_SUFFIXES, SOURCE_SUFFIXES
from .errors import ConfigurationError, MissingCompilationDatabaseError


@dataclass(slots=True)
class AnalyzerConfig:
    project_root: str | Path
    clangd_path: str | None = None
    compile_commands_path: str | Path | None = None
    trace_lsp_communication: bool = False
    start_independent_lsp_process: bool = False
    source_suffixes: tuple[str, ...] = SOURCE_SUFFIXES
    header_suffixes: tuple[str, ...] = HEADER_SUFFIXES

    def __post_init__(self) -> None:
        self.project_root = Path(self.project_root).expanduser().resolve()
        if self.compile_commands_path is not None:
            self.compile_commands_path = Path(self.compile_commands_path).expanduser().resolve()
        self.source_suffixes = tuple(sorted({suffix.lower() for suffix in self.source_suffixes}))
        self.header_suffixes = tuple(sorted({suffix.lower() for suffix in self.header_suffixes}))

    @property
    def all_suffixes(self) -> tuple[str, ...]:
        return self.source_suffixes + self.header_suffixes

    def resolve_clangd_path(self) -> str | None:
        if self.clangd_path:
            return str(Path(self.clangd_path).expanduser())

        env_path = os.environ.get("CLANGD_PATH")
        if env_path:
            return str(Path(env_path).expanduser())

        return shutil.which("clangd")

    def resolve_compile_commands_path(self) -> Path | None:
        if self.compile_commands_path is not None:
            return self.compile_commands_path

        candidate = self.project_root / "compile_commands.json"
        if candidate.exists():
            return candidate
        return None

    def validate(self) -> None:
        if not self.project_root.exists():
            raise ConfigurationError(f"Project root does not exist: {self.project_root}")
        if not self.project_root.is_dir():
            raise ConfigurationError(f"Project root must be a directory: {self.project_root}")

        compile_commands_path = self.resolve_compile_commands_path()
        if compile_commands_path is None or not compile_commands_path.exists():
            raise MissingCompilationDatabaseError(
                "compile_commands.json was not found in the project root. "
                "This library currently expects the compilation database to live at "
                f"{self.project_root / 'compile_commands.json'}."
            )
        if compile_commands_path.parent != self.project_root:
            raise ConfigurationError(
                "multilspy + clangd is configured here with the project root as the workspace root, "
                "so compile_commands.json must currently live in that same directory."
            )

    def to_multilspy_config(self):  # type: ignore[no-untyped-def]
        from multilspy.multilspy_config import MultilspyConfig

        payload = {
            "code_language": "cpp",
            "trace_lsp_communication": self.trace_lsp_communication,
            "start_independent_lsp_process": self.start_independent_lsp_process,
        }
        clangd_path = self.resolve_clangd_path()
        if clangd_path:
            payload["server_binary"] = clangd_path
        return MultilspyConfig.from_dict(payload)
