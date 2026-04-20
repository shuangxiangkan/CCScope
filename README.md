# CCScope

CCScope is a Python library for structured analysis of C and C++ codebases.
It uses `multilspy` and `clangd` underneath, and exposes LLM-friendly interfaces for:

- compilation database inspection
- source file discovery
- symbol search
- definition and reference lookup
- hover and completion queries
- source snippet extraction
- workspace indexing
- LangChain and LangGraph integration

The goal is to make native codebases easy to inspect programmatically before handing the extracted evidence to an LLM for debugging, code review, root-cause analysis, and retrieval-augmented reasoning.

## What CCScope Expects

CCScope currently expects:

- Python 3.10+
- `clangd` 18 or newer
- a `compile_commands.json` file at the repository root of the target project

Why `clangd >= 18`:

- current `multilspy` C/C++ support is only reliable with newer `clangd` builds
- older releases can fail during LSP initialization
- CCScope detects this in `preflight()` and raises a clear error before starting a session

## Installation

### macOS

Install `clangd`:

```bash
brew install llvm@18
export CLANGD_PATH="$(brew --prefix llvm@18)/bin/clangd"
```

Install CCScope:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Optional agent integrations:

```bash
pip install -e ".[agents]"
```

### Linux

Install `clangd`:

```bash
sudo apt-get update
sudo apt-get install -y clangd-18 cmake
export CLANGD_PATH=/usr/bin/clangd-18
```

Install CCScope:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Optional agent integrations:

```bash
pip install -e ".[agents]"
```

## Generating `compile_commands.json`

This is the most important setup step for real projects.
`clangd` needs the actual compile flags used for each translation unit, such as include paths, language mode, target flags, macro definitions, and sysroot settings.

Official background:

- clangd compile-command design: <https://clangd.llvm.org/design/compile-commands>
- CMake `CMAKE_EXPORT_COMPILE_COMMANDS`: <https://cmake.org/cmake/help/latest/variable/CMAKE_EXPORT_COMPILE_COMMANDS.html>
- Bear compilation database generator: <https://github.com/rizsotto/Bear>

### 1. CMake Projects

For CMake-based projects, use the native export path.

```bash
cmake -S /path/to/project -B /path/to/project/build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cp /path/to/project/build/compile_commands.json /path/to/project/compile_commands.json
```

You can also enable it inside `CMakeLists.txt`:

```cmake
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
```

Notes:

- per the CMake docs, this works with Makefile and Ninja generators
- for CCScope, place the resulting `compile_commands.json` at the analyzed project root

### 2. Non-CMake Projects

If the build system does not export a compilation database natively, the most practical option is usually `Bear`.

```bash
bear -- make -j
```

or:

```bash
bear -- ninja
```

This records the real compiler invocations and writes `compile_commands.json` to the current working directory.

Use this when:

- the project uses `make`, custom shell scripts, or ad-hoc native builds
- you do not want to migrate the project to CMake just to get a compilation database

For very small projects, you can also hand-write `compile_commands.json`, but that becomes fragile quickly.

### 3. Simple or Prototype Projects

clangd can also work with `compile_flags.txt` for small codebases, according to the clangd docs.
However, CCScope currently expects `compile_commands.json`, so for this library you should still generate or write a real compilation database.

### 4. JNI and Other Cross-Language Projects

For JNI, Android native modules, or other mixed-language repositories, the key rule is:

- generate the compilation database from the native C/C++ build, not from the Java/Kotlin layer

Typical setups:

- if the JNI layer is built with CMake, export `compile_commands.json` from that CMake build
- if the native layer is built with `ndk-build`, `make`, or a custom script, intercept the native compiler calls with `Bear`
- if the repository contains several native subprojects, generate the database from the subproject you want CCScope to analyze, or merge databases as part of your build tooling

Practical requirement:

- the database must contain the real native compiler flags, including JNI headers, Android NDK headers, target triples, ABI flags, and preprocessor macros

This JNI guidance is an inference from how clangd uses compile commands: it only cares about the native translation units and the flags needed to parse them correctly.

### 5. Python Projects with Native Extensions

For Python projects that build C or C++ extensions, the rule is similar:

- generate the compilation database from the native extension build, not from Python import-time behavior

Common cases:

- `pybind11` or `scikit-build-core` with CMake:
  export from the CMake build exactly like a normal CMake project
- `setuptools` with `Extension(...)` and a custom compiler-driven build:
  capture the native compiler invocations with `Bear`
- mixed Python + Cython + C/C++ repositories:
  generate the database for the underlying C/C++ compilation stage that produces the extension module

Practical requirement:

- the database must include Python headers, platform ABI flags, extension-specific macros, and any generated include directories

This recommendation is also an inference from clangd’s compile-command model: for CCScope, what matters is whether the final native compiler command accurately reflects the extension build.

## Quick Start

The distribution name is `ccscope`, while the current Python import package remains `cc_analyzer`.

### Async

```python
from cc_analyzer import AsyncCodebaseAnalyzer


async def main() -> None:
    async with AsyncCodebaseAnalyzer.from_root("tests/cJSON") as analyzer:
        preflight = analyzer.preflight()
        print(preflight.to_dict())

        symbols = await analyzer.get_document_symbols("cJSON.c")
        print(symbols[0].to_dict())
```

### Sync

```python
from cc_analyzer import SyncCodebaseAnalyzer


with SyncCodebaseAnalyzer.from_root("tests/cJSON") as analyzer:
    files = analyzer.list_source_files(limit=10)
    print([item.relative_path for item in files])

    definitions = analyzer.get_definition("tests/compare_tests.c", line=31, column=14)
    print([item.to_dict() for item in definitions])
```

## API Reference

The full public API is documented in `API_REFERENCE.md`.

That file covers:

- `AsyncCodebaseAnalyzer`
- `SyncCodebaseAnalyzer`
- `LangGraphToolkit`
- the return models in `src/cc_analyzer/models.py`
- method-by-method usage and return types

## LangChain and LangGraph

CCScope includes `LangGraphToolkit`, which can expose:

- plain callable tool functions
- LangChain-compatible tools via `as_langchain_tools()`

See `API_REFERENCE.md` for the full interface list, and the examples there for usage patterns.

## Test Fixture

This repository includes a real integration fixture under `tests/cJSON`.
It is a clone of the `cJSON` project and is used to validate the analyzer against a non-trivial C codebase.

The fixture contains `tests/cJSON/compile_commands.json`.
The test helper regenerates this file with CMake automatically if its absolute paths become stale on another machine.

## Running Tests

Unit tests:

```bash
./.venv/bin/python -m unittest discover -s tests
```

LSP integration tests:

```bash
RUN_CCLSP_LSP_TESTS=1 ./.venv/bin/python -m unittest discover -s tests
```

The LSP tests run only if:

- `RUN_CCLSP_LSP_TESTS=1`
- `clangd` is available
- `clangd` is compatible with the current `multilspy` C/C++ support

## Repository Layout

```text
src/cc_analyzer/
  __init__.py
  analyzer.py
  config.py
  constants.py
  errors.py
  langgraph.py
  models.py
tests/
  cJSON/
  helpers.py
  test_config_and_models.py
  test_langgraph_toolkit.py
  test_sync_analyzer.py
API_REFERENCE.md
requirements.txt
pyproject.toml
```
