import unittest

from helpers import CJSON_ROOT, lsp_tests_enabled

from cc_analyzer import SyncCodebaseAnalyzer


LSP_ENABLED = lsp_tests_enabled()


class SyncAnalyzerTests(unittest.TestCase):
    def test_compilation_units_and_filesystem_views(self) -> None:
        analyzer = SyncCodebaseAnalyzer.from_root(CJSON_ROOT)
        units = analyzer.get_compilation_units()
        files = analyzer.list_source_files()

        self.assertGreaterEqual(len(units), 20)
        self.assertTrue(any(unit.relative_path == "cJSON.c" for unit in units))
        self.assertTrue(any(file.relative_path == "cJSON.h" for file in files))
        self.assertFalse(any(file.relative_path.startswith("build/") for file in files))

    def test_snippet_reads_expected_lines(self) -> None:
        analyzer = SyncCodebaseAnalyzer.from_root(CJSON_ROOT)
        snippet = analyzer.get_snippet("cJSON.c", 1227, 1230)
        self.assertIn("cJSON_Parse", snippet.text)
        self.assertIn("cJSON_ParseWithOpts", snippet.text)
        self.assertIn("1227:", snippet.numbered_text)

    def test_preflight_reports_fixture_state(self) -> None:
        analyzer = SyncCodebaseAnalyzer.from_root(CJSON_ROOT)
        preflight = analyzer.preflight()

        self.assertTrue(preflight.has_compile_commands)
        self.assertEqual(preflight.project_root, str(CJSON_ROOT))

    @unittest.skipUnless(LSP_ENABLED, "LSP integration test disabled or clangd is incompatible")
    def test_document_symbols_for_real_project(self) -> None:
        with SyncCodebaseAnalyzer.from_root(CJSON_ROOT) as analyzer:
            symbols = analyzer.get_document_symbols("cJSON.c")
            self.assertTrue(any(symbol.name == "cJSON_Parse" for symbol in symbols))

    @unittest.skipUnless(LSP_ENABLED, "LSP integration test disabled or clangd is incompatible")
    def test_definition_resolution_for_call_site(self) -> None:
        with SyncCodebaseAnalyzer.from_root(CJSON_ROOT) as analyzer:
            line, column = _find_token(analyzer, "tests/compare_tests.c", "cJSON_Parse")
            definitions = analyzer.get_definition("tests/compare_tests.c", line, column)
            self.assertTrue(any(location.relative_path == "cJSON.c" for location in definitions))


def _find_token(analyzer: SyncCodebaseAnalyzer, relative_path: str, token: str) -> tuple[int, int]:
    for line_number, line in enumerate(analyzer.read_file(relative_path).splitlines(), start=1):
        column = line.find(token)
        if column >= 0:
            return line_number, column + 1
    raise AssertionError(f"Could not find token {token!r} in {relative_path}")


if __name__ == "__main__":
    unittest.main()
