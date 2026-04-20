import os
import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
CJSON_ROOT = REPO_ROOT / "tests" / "cJSON"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def ensure_cjson_fixture_prepared() -> None:
    compile_commands_path = CJSON_ROOT / "compile_commands.json"
    build_dir = CJSON_ROOT / "build"
    build_compile_commands_path = build_dir / "compile_commands.json"

    if not CJSON_ROOT.exists():
        raise RuntimeError(
            "The cJSON fixture is missing. Clone https://github.com/DaveGamble/cJSON.git into tests/cJSON first."
        )

    needs_regeneration = not compile_commands_path.exists()
    if not needs_regeneration:
        try:
            payload = json.loads(compile_commands_path.read_text(encoding="utf-8"))
            first_file = Path(payload[0]["file"]).resolve()
            needs_regeneration = not first_file.exists() or CJSON_ROOT not in first_file.parents
        except Exception:
            needs_regeneration = True

    if not needs_regeneration:
        return

    cmake_path = shutil.which("cmake")
    if cmake_path is None:
        raise RuntimeError(
            "cmake is required to regenerate the cJSON compile_commands.json fixture."
        )

    subprocess.run(
        [
            cmake_path,
            "-S",
            str(CJSON_ROOT),
            "-B",
            str(build_dir),
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
            "-DENABLE_CJSON_UTILS=ON",
        ],
        check=True,
        cwd=REPO_ROOT,
    )
    shutil.copyfile(build_compile_commands_path, compile_commands_path)


ensure_cjson_fixture_prepared()


def lsp_tests_enabled() -> bool:
    if os.environ.get("RUN_CCLSP_LSP_TESTS") != "1":
        return False

    from cc_analyzer import SyncCodebaseAnalyzer

    preflight = SyncCodebaseAnalyzer.from_root(CJSON_ROOT).preflight()
    return preflight.has_clangd and preflight.clangd_compatible is True
