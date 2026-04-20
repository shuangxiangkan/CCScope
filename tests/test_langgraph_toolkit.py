import unittest

from helpers import CJSON_ROOT

from cc_analyzer import LangGraphToolkit, SyncCodebaseAnalyzer


class LangGraphToolkitTests(unittest.TestCase):
    def test_toolkit_exposes_core_tool_functions(self) -> None:
        analyzer = SyncCodebaseAnalyzer.from_root(CJSON_ROOT)
        toolkit = LangGraphToolkit(analyzer)

        tool_names = {tool.__name__ for tool in toolkit.as_tool_functions()}

        self.assertIn("preflight", tool_names)
        self.assertIn("read_file", tool_names)
        self.assertIn("get_workspace_symbols", tool_names)
        self.assertIn("inspect_symbol", tool_names)

    def test_preflight_payload_is_serializable(self) -> None:
        analyzer = SyncCodebaseAnalyzer.from_root(CJSON_ROOT)
        toolkit = LangGraphToolkit(analyzer)
        payload = toolkit.preflight()

        self.assertIn("project_root", payload)
        self.assertIn("clangd_path", payload)
        self.assertIn("compile_commands_path", payload)


if __name__ == "__main__":
    unittest.main()
