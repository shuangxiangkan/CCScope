class AnalyzerError(Exception):
    """Base error for the analyzer library."""


class ConfigurationError(AnalyzerError):
    """Raised when the project or tool configuration is invalid."""


class MissingCompilationDatabaseError(ConfigurationError):
    """Raised when compile_commands.json cannot be found or used."""


class DependencyUnavailableError(AnalyzerError):
    """Raised when a runtime dependency such as clangd or multilspy is missing."""
