"""Third-party imports: none in the tool itself, and each one elsewhere pinned exactly.

A third-party import is one from neither the standard library nor the project's
own code. The tool itself makes none, so `[project].dependencies` is empty by
design, and one in the files it runs from, its entry point, the vendored library
beside it and the modules under `src/`, fails this suite even when it is pinned.
Own code, for those files, is only the tool's modules, that library, and the
libraries it finds by an upward search, so a
test helper is third-party there too, and the tool cannot reach a library
through one. The tests are another matter: the property suites import a
third-party library, and an import that nothing declares is one no dependency
audit can see, however carefully the audit is run. So every import in the project
is read here, and each third-party one must be declared in the `test` extra with
an exact `==` pin. A new third-party import fails this suite until it is declared.

What counts as the project's own code is derived from the files present, never
listed here: the name of every module file under the project, the name of every
package directory, and the name of every module file in each directory the
type checker's `mypy_path` names that exists outside the project. That last set
is how the libraries the code finds by an upward search at runtime are
recognized. A list kept by hand would need an edit for
every module added or renamed, and a name left on it after its module was gone
would let a third-party import of that name through unnoticed.

An import name is compared with a distribution name directly, which holds while
every third-party import is named like the distribution that provides it.

Read as source with `ast` rather than by importing anything: the question is
what the code names, including an import inside a function or behind an `if`,
and importing a module answers only which of its imports happened to run.
"""

import ast
import re
import sys
import tempfile
import tomllib
import unittest
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent

#: The extra that declares, pinned, every third-party library outside the tool.
_TEST_EXTRA = "test"

#: The tool's entry point. A literal name because it IS the contract with the
#: project, kept here only; the folder holding it may be named anything.
_ENTRY_POINT = "decorative_crossword.py"

#: The folder beside the entry point holding the modules the tool runs from.
_RUNTIME_MODULES = "src"

#: The token mypy expands to the directory of the config file that names it.
_CONFIG_DIR_TOKEN = "$MYPY_CONFIG_FILE_DIR"

#: A package directory's marker file, whose module name is its directory's.
_PACKAGE_MARKER = "__init__.py"

#: The bytecode cache directory the interpreter writes beside the code.
_BYTECODE_CACHE = "__pycache__"

#: One requirement pinned to exactly one release: a distribution name, `==`, and a
#: version, with no wildcard, range, `===` or environment marker after it.
_EXACT_PIN = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*(?P<version>[A-Za-z0-9.+!_-]+)"
)

#: Distribution names compare case-insensitively, with any run of `-`, `_` and `.`
#: equal to any other.
_NAME_SEPARATORS = re.compile(r"[-_.]+")

#: A floor on the scan's denominator. The pin check passes trivially over a scan that
#: found nothing, or one rooted a level too deep that saw only one folder. Well below
#: today's count and well above any one folder's, so it is not a census to keep in step.
_MIN_SOURCES = 150


def _is_cache_directory(name: str) -> bool:
    """A directory tools write beside the code: bytecode, or a hidden cache."""
    return name == _BYTECODE_CACHE or name.startswith(".")


def _module_files(root: Path) -> list[Path]:
    """Every `.py` file under `root`, outside the cache directories."""
    found: list[Path] = []
    for directory, subdirectories, files in root.walk():
        # Pruned in place, so the walk never descends into a cache at all.
        subdirectories[:] = sorted(
            name for name in subdirectories if not _is_cache_directory(name)
        )
        found.extend(directory / name for name in sorted(files) if name.endswith(".py"))
    return found


def _module_name(path: Path) -> str:
    """The name `path` is imported by: its stem, or its directory's for a package."""
    return path.parent.name if path.name == _PACKAGE_MARKER else path.stem


def _string_array(table: dict[str, object], *keys: str) -> list[str]:
    """The TOML array of strings reached through `keys`, or empty if a key is absent.

    Absence reads as empty because both arrays this module reads fail loudly when
    empty: no pins leaves every third-party import unpinned, and no `mypy_path`
    leaves the upward-search libraries looking third-party.
    """
    value: object = table
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return []
        value = value[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AssertionError(f"{'.'.join(keys)} is not an array of strings: {value!r}")
    return value


def _read_pyproject(project: Path) -> dict[str, object]:
    """The project's own `pyproject.toml`, parsed."""
    with (project / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _library_names(project: Path) -> frozenset[str]:
    """The module names of the libraries the code finds by an upward search.

    Those are the `.py` files in each `mypy_path` directory that exists outside the
    project. A listed directory inside it holds the project's own code, which is
    read file by file instead, so which files may import it stays a question about
    those files. `$MYPY_CONFIG_FILE_DIR` is the directory holding the
    `pyproject.toml`, which is the project root.
    """
    root = project.resolve()
    names: set[str] = set()
    for entry in _string_array(_read_pyproject(project), "tool", "mypy", "mypy_path"):
        directory = Path(entry.replace(_CONFIG_DIR_TOKEN, str(project))).resolve()
        if directory.is_dir() and not directory.is_relative_to(root):
            names.update(path.stem for path in directory.glob("*.py"))
    return frozenset(names)


def _local_names(files: Iterable[str], libraries: frozenset[str]) -> set[str]:
    """The names an import from `files` may use without leaving them.

    Their own module names, and the upward-search libraries.
    """
    return {_module_name(Path(path)) for path in files} | libraries


def _imported_top_levels(tree: ast.Module) -> set[str]:
    """The top-level module of every absolute import anywhere in a parsed file.

    A relative import names the file's own package, so it is local by construction.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.partition(".")[0])
    return names


@dataclass(frozen=True)
class _ImportScan:
    """What one pass over a project's module files found.

    Every file the pass parsed is a key of `imports`, so a floor on the files parsed
    holds the very pass every check reads: a scan that reached less of the project
    shows it here.
    """

    #: Each file the pass parsed, relative to the project, with the top-level names
    #: it imports from outside the standard library.
    imports: dict[str, frozenset[str]]
    #: The module names of the libraries the code finds by an upward search.
    libraries: frozenset[str]


def _scan_imports(project: Path) -> _ImportScan:
    """Parse every module file under `project` and keep its non-stdlib imports."""
    imports: dict[str, frozenset[str]] = {}
    for path in _module_files(project):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = _imported_top_levels(tree) - sys.stdlib_module_names
        imports[path.relative_to(project).as_posix()] = frozenset(names)
    return _ImportScan(imports, _library_names(project))


def _third_party_imports(scan: _ImportScan, files: set[str]) -> dict[str, list[str]]:
    """Each third-party name `files` import, with the files that import it.

    Third-party is judged from `files` alone: a name is local only when it is one of
    their own modules or an upward-search library, so a module elsewhere in the
    project counts as third-party to them. Passed every parsed file, that is the
    whole project's view.
    """
    local = _local_names(files, scan.libraries)
    found: dict[str, list[str]] = {}
    for path in sorted(files):
        for name in sorted(scan.imports[path] - local):
            found.setdefault(name, []).append(path)
    return found


def _runtime_files(project: Path) -> set[str]:
    """The files the tool runs from, relative to `project`.

    Its entry point, the vendored library beside it, and every module under `src/`.
    The library counts as its one module file, `stdio_utf8/stdio_utf8.py`, never its
    folder's tests or their aggregator, which are test code. It counts where it is
    present, so a scratch project built without it holds the other two alone; were
    the tool's own copy missing, its import would read as third-party below.
    """
    library = project / "stdio_utf8" / "stdio_utf8.py"
    files = [
        project / _ENTRY_POINT,
        *([library] if library.is_file() else []),
        *_module_files(project / _RUNTIME_MODULES),
    ]
    return {path.relative_to(project).as_posix() for path in files}


def _normalized(name: str) -> str:
    """A distribution name in the form two spellings of it compare equal in."""
    return _NAME_SEPARATORS.sub("-", name).lower()


def _exact_pins(requirements: list[str]) -> dict[str, str]:
    """The requirements pinned to one exact release, as normalized name to version."""
    pins: dict[str, str] = {}
    for requirement in requirements:
        match = _EXACT_PIN.fullmatch(requirement.strip())
        if match:
            pins[_normalized(match["name"])] = match["version"]
    return pins


def _test_extra_pins(project: Path) -> dict[str, str]:
    """The exact pins the project's `test` extra declares."""
    document = _read_pyproject(project)
    return _exact_pins(
        _string_array(document, "project", "optional-dependencies", _TEST_EXTRA)
    )


def _write_files(root: Path, contents: dict[str, str]) -> None:
    """Write a small synthetic tree under `root`, one file per relative path.

    Written with `\\n` line endings on every host, so the tree is the same bytes
    wherever the suite runs.
    """
    for relative, text in contents.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


class TestImportsAreRead(unittest.TestCase):
    """The scan sees every import shape, and knows the project's own modules."""

    def test_imports_are_read_wherever_they_sit(self) -> None:
        source = (
            "import alpha.inner as renamed\n"
            "from beta.inner import thing\n"
            "def load() -> None:\n"
            "    import gamma\n"
            "if FLAG:\n"
            "    from delta import other\n"
            "try:\n"
            "    import epsilon\n"
            "except ImportError:\n"
            "    pass\n"
            "from . import sibling\n"
            "from .neighbor import item\n"
        )
        self.assertEqual(
            _imported_top_levels(ast.parse(source)),
            {"alpha", "beta", "gamma", "delta", "epsilon"},
        )

    def test_local_names_come_from_the_files_and_the_type_checker_path(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            _write_files(
                Path(scratch),
                {
                    "project/own.py": "",
                    f"project/pkg/{_PACKAGE_MARKER}": "",
                    "project/pkg/inner.py": "",
                    "project/.cache/cached.py": "",
                    "project/pyproject.toml": (
                        "[tool.mypy]\nmypy_path = [\n"
                        f'  "{_CONFIG_DIR_TOKEN}/../vendored",\n'
                        f'  "{_CONFIG_DIR_TOKEN}/pkg",\n'
                        f'  "{_CONFIG_DIR_TOKEN}/absent",\n'
                        "]\n"
                    ),
                    "vendored/library.py": "",
                },
            )
            scan = _scan_imports(Path(scratch) / "project")
        # The listed folder inside the project is its own code, not a library.
        self.assertEqual(scan.libraries, {"library"})
        self.assertEqual(
            _local_names(scan.imports, scan.libraries),
            {"own", "pkg", "inner", "library"},
        )

    def test_an_absent_type_checker_path_adds_no_names(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            project = Path(scratch)
            _write_files(project, {"pyproject.toml": "[tool.mypy]\n"})
            self.assertEqual(_library_names(project), set())

    def test_a_scan_reports_only_what_comes_from_outside(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            _write_files(
                Path(scratch),
                {
                    "project/pyproject.toml": (
                        f'[tool.mypy]\nmypy_path = ["{_CONFIG_DIR_TOKEN}/../vendored"]\n'
                    ),
                    "project/own.py": "import json\n",
                    "project/uses_own.py": "import own\n",
                    "project/uses_library.py": "import library\n",
                    "project/nested/uses_outsider.py": (
                        "def load() -> None:\n    import outsider\n"
                    ),
                    "vendored/library.py": "",
                },
            )
            scan = _scan_imports(Path(scratch) / "project")
        self.assertEqual(
            _third_party_imports(scan, set(scan.imports)),
            {"outsider": ["nested/uses_outsider.py"]},
        )
        self.assertEqual(
            sorted(scan.imports),
            ["nested/uses_outsider.py", "own.py", "uses_library.py", "uses_own.py"],
        )

    def test_a_pin_does_not_excuse_an_outside_import_in_the_tool(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            # Named unlike the entry point, so the check cannot lean on the folder.
            project = Path(scratch) / "renamed-checkout"
            _write_files(
                project,
                {
                    "pyproject.toml": (
                        '[project.optional-dependencies]\ntest = ["pinned==1.0"]\n'
                    ),
                    _ENTRY_POINT: "import json\nimport engine\n",
                    "src/engine.py": "import pinned\n",
                    "tests/test_engine.py": "import pinned\n",
                },
            )
            scan = _scan_imports(project)
            runtime = _runtime_files(project)
            pins = _test_extra_pins(project)
        self.assertEqual(pins, {"pinned": "1.0"})
        self.assertEqual(runtime, {_ENTRY_POINT, "src/engine.py"})
        self.assertEqual(
            _third_party_imports(scan, runtime), {"pinned": ["src/engine.py"]}
        )

    def test_the_tool_may_not_lean_on_a_test_helper(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            _write_files(
                Path(scratch),
                {
                    "project/pyproject.toml": (
                        "[tool.mypy]\nmypy_path = [\n"
                        f'  "{_CONFIG_DIR_TOKEN}/../vendored",\n'
                        f'  "{_CONFIG_DIR_TOKEN}/strategies",\n'
                        "]\n"
                    ),
                    f"project/{_ENTRY_POINT}": "import engine\n",
                    "project/src/engine.py": "import library\nimport helpers\n",
                    "project/strategies/helpers.py": "import pinned\n",
                    "project/tests/test_engine.py": "import engine\nimport helpers\n",
                    "vendored/library.py": "",
                },
            )
            project = Path(scratch) / "project"
            scan = _scan_imports(project)
            runtime = _runtime_files(project)
        # The helper is the project's own code, but not the tool's: to the files the
        # tool runs from it is as third-party as the library it imports.
        self.assertEqual(
            _third_party_imports(scan, runtime), {"helpers": ["src/engine.py"]}
        )
        self.assertEqual(
            _third_party_imports(scan, set(scan.imports)),
            {"pinned": ["strategies/helpers.py"]},
        )

    def test_an_array_of_another_shape_is_refused(self) -> None:
        with self.assertRaisesRegex(AssertionError, "tool.mypy.mypy_path"):
            _string_array(
                {"tool": {"mypy": {"mypy_path": "src"}}}, "tool", "mypy", "mypy_path"
            )


class TestPins(unittest.TestCase):
    """Only a pin to one exact release counts as a declaration."""

    def test_only_an_exact_pin_counts(self) -> None:
        requirements = [
            "exact==6.165.10",
            "Mixed_Case.Name == 1.0",
            "ranged>=1.0",
            "wildcard==1.*",
            "arbitrary===1.0",
            "marked==1.0; python_version >= '3.14'",
            "bare",
        ]
        self.assertEqual(
            _exact_pins(requirements), {"exact": "6.165.10", "mixed-case-name": "1.0"}
        )


class TestTheProjectAsItStands(unittest.TestCase):
    """The project as it stands, read by one scan every check below shares."""

    scan: _ImportScan

    @classmethod
    def setUpClass(cls) -> None:
        cls.scan = _scan_imports(_PROJECT)

    def test_the_scan_reaches_the_whole_project(self) -> None:
        found = len(self.scan.imports)
        self.assertGreaterEqual(
            found,
            _MIN_SOURCES,
            f"the scan parsed {found} module files under {_PROJECT.name}, expected "
            f"at least {_MIN_SOURCES} -- it may be rooted in the wrong directory",
        )

    def test_every_third_party_import_is_pinned_in_the_test_extra(self) -> None:
        pins = _test_extra_pins(_PROJECT)
        importers = _third_party_imports(self.scan, set(self.scan.imports))
        unpinned = sorted(name for name in importers if _normalized(name) not in pins)
        self.assertEqual(
            unpinned,
            [],
            "third-party imports not pinned as name==version in the pyproject.toml's "
            f"[project.optional-dependencies] {_TEST_EXTRA} extra: "
            + "; ".join(
                f"{name} ({len(importers[name])} files, first {importers[name][0]})"
                for name in unpinned
            ),
        )

    def test_the_tool_makes_no_third_party_import(self) -> None:
        runtime = _runtime_files(_PROJECT)
        # The check below passes over an empty set, so first prove the set is the
        # tool: its modules are there, and the scan parsed every file of it, the
        # entry point included.
        self.assertTrue(
            any(path.startswith(f"{_RUNTIME_MODULES}/") for path in runtime),
            f"no module found under {_RUNTIME_MODULES}/",
        )
        unparsed = sorted(runtime - set(self.scan.imports))
        self.assertEqual(
            unparsed, [], "files the tool runs from that the scan did not parse"
        )
        self.assertEqual(
            _third_party_imports(self.scan, runtime),
            {},
            "the tool makes no third-party import, and neither a pin in the "
            f"{_TEST_EXTRA} extra nor a module elsewhere in the project changes "
            "that (name: the tool's files importing it)",
        )


if __name__ == "__main__":
    unittest.main()
