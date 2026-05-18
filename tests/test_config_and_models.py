import unittest
from unittest.mock import patch

from helpers import CJSON_ROOT

from cc_analyzer import AnalyzerConfig
from cc_analyzer.models import Position, Range


class ConfigTests(unittest.TestCase):
    def test_compile_commands_is_detected(self) -> None:
        config = AnalyzerConfig(project_root=CJSON_ROOT)
        compile_commands_path = config.resolve_compile_commands_path()
        self.assertIsNotNone(compile_commands_path)
        self.assertEqual(compile_commands_path, CJSON_ROOT / "compile_commands.json")

    def test_validate_rejects_missing_project(self) -> None:
        config = AnalyzerConfig(project_root=CJSON_ROOT / "missing-project")
        with self.assertRaises(Exception):
            config.validate()

    def test_clangd_path_is_optional(self) -> None:
        config = AnalyzerConfig(project_root=CJSON_ROOT, clangd_path=None)
        self.assertIsNotNone(config.project_root)

    def test_clangd_18_is_preferred_over_plain_clangd(self) -> None:
        def fake_which(name: str) -> str | None:
            return {
                "clangd-18": "/usr/bin/clangd-18",
                "clangd": "/usr/bin/clangd",
            }.get(name)

        config = AnalyzerConfig(project_root=CJSON_ROOT, clangd_path=None)
        with patch("cc_analyzer.config.shutil.which", side_effect=fake_which):
            self.assertEqual(config.resolve_clangd_path(), "/usr/bin/clangd-18")


class ModelTests(unittest.TestCase):
    def test_position_round_trip(self) -> None:
        pos = Position(line=3, column=7)
        self.assertEqual(pos.to_lsp(), {"line": 2, "character": 6})
        self.assertEqual(Position.from_lsp({"line": 2, "character": 6}), pos)

    def test_range_contains_line(self) -> None:
        rng = Range.from_lsp(
            {
                "start": {"line": 4, "character": 0},
                "end": {"line": 7, "character": 2},
            }
        )
        self.assertTrue(rng.contains_line(5))
        self.assertFalse(rng.contains_line(20))


if __name__ == "__main__":
    unittest.main()
