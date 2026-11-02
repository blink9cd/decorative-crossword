"""Suite aggregator: runs every grouped suite under tests/.

The subject modules live under src/ and are imported by bare name, which works
because this file's own directory plus src/ are on sys.path (see _SRC below).
Each behavior has its own module in tests/; this file owns only the wiring and
the checks on the suite's own shape: the floor assertions that keep a
silently-emptied suite from passing, and the assertions that each property
module registers a deadline-free Hypothesis profile of its own.
"""

import ast
import sys
import unittest
from collections.abc import Iterator
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
# The suites get this tool folder from discovery's `top_level_dir` below (they import
# as `tests.test_x`), and src/ from this insert.
# import-alone: ., src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_TESTS = Path(__file__).resolve().parent / "tests"

#: The folders whose modules run Hypothesis properties: the grouped suites, and
#: the shared strategy library, whose own unit test draws from it.
_PROPERTY_FOLDERS = (_TESTS, Path(__file__).resolve().parent / "property_strategies")

#: The Hypothesis class, and its two methods that name a profile.
_SETTINGS = "settings"
_REGISTER_PROFILE = "register_profile"
_LOAD_PROFILE = "load_profile"

#: The profile setting every registration must pass as None.
_DEADLINE = "deadline"

#: The package, and its decorator that makes a test a property.
_HYPOTHESIS = "hypothesis"
_GIVEN = "given"

#: Per-file floors. A test deleted from a grouped suite drops its file's count
#: below this and fails loudly, rather than shrinking the suite unnoticed.
#: Raise a floor when you add tests; never lower one to make a run pass.
#: Lower one only when its tests move to another file or lose their subject
#: with a removed feature: a floor kept above those can only be met by padding.
_MIN_GROUPED_TESTS_BY_FILE = {
    "test_grid.py": 36,
    "test_mask.py": 42,
    "test_mask_properties.py": 4,
    "test_cli_mask.py": 10,
    "test_cli_mask_shape.py": 4,
    "test_bank.py": 48,
    "test_bank_themes.py": 8,
    "test_bank_merge.py": 21,
    "test_bank_merge_properties.py": 1,
    "test_cli_banks.py": 18,
    "test_bank_ratings.py": 12,
    "test_properties.py": 1,
    "test_feature_properties.py": 1,
    "test_feature.py": 24,
    "test_feature_source.py": 20,
    "test_config.py": 49,
    "test_emit.py": 36,
    "test_emit_load.py": 31,
    "test_emit_write_path.py": 9,
    "test_place.py": 40,
    "test_search_parts.py": 38,
    "test_order.py": 21,
    "test_search.py": 27,
    "test_search_pins.py": 12,
    "test_search_interlock.py": 6,
    "test_search_cost.py": 8,
    "test_select.py": 25,
    "test_symmetry.py": 9,
    "test_search_best.py": 10,
    "test_island.py": 29,
    "test_island_properties.py": 2,
    "test_cli_best_islands.py": 19,
    "test_cli_symmetry.py": 10,
    "test_cli_strays.py": 6,
    "test_reach.py": 33,
    "test_reach_properties.py": 5,
    "test_accept_features.py": 7,
    "test_search_properties.py": 5,
    "test_search_determinism.py": 2,
    "test_report.py": 35,
    "test_report_remedy.py": 24,
    "test_report_ratings.py": 12,
    "test_report_source.py": 25,
    "test_svg.py": 37,
    "test_svg_containment.py": 9,
    "test_svg_visibility.py": 14,
    "test_svg_caption.py": 30,
    "test_svg_hidden.py": 9,
    "test_svg_fixed.py": 16,
    "test_svg_empty_blocks.py": 23,
    "test_cli_fixed.py": 3,
    "test_cli.py": 40,
    "test_cli_features.py": 16,
    "test_cli_help_prose.py": 10,
    "test_cli_preview.py": 29,
    "test_cli_preview_features.py": 12,
    "test_cli_shade.py": 27,
    "test_cli_themeless.py": 3,
    "test_cli_empty_bank.py": 5,
    "test_samples.py": 23,
    "test_samples_content.py": 10,
    "test_samples_read.py": 12,
    "test_samples_source.py": 8,
    "test_shade.py": 36,
    "test_shade_properties.py": 6,
    "test_shade_report.py": 20,
    "test_gaps.py": 24,
    "test_gaps_vocabulary.py": 27,
    "test_gaps_report.py": 52,
    "test_cli_gaps.py": 27,
    "test_svg_gaps.py": 12,
    "test_gaps_properties.py": 8,
    "test_pairs.py": 27,
    "test_pairs_properties.py": 1,
    "test_cli_pairs.py": 14,
    "test_pairs_barred.py": 16,
    "test_cli_barred_joins.py": 5,
    "test_source.py": 18,
    "test_source_properties.py": 1,
    "test_source_size.py": 11,
    "test_size_cap.py": 14,
    "test_cli_grown.py": 12,
    "test_search_source.py": 25,
    "test_cli_source.py": 20,
    "test_cli_partial.py": 10,
    "test_cli_absorb.py": 9,
    "test_search_absorb.py": 7,
    "test_absorb_properties.py": 1,
    "test_paths.py": 17,
    "test_cli_outputs.py": 18,
    "test_cli_two_letter.py": 4,
    "test_search_two_letter.py": 2,
    "test_answer.py": 21,
    "test_answer_properties.py": 5,
    "test_bank_spelling.py": 15,
    "test_emit_spelling.py": 7,
    "test_cli_spelling.py": 14,
    "test_json.py": 17,
    "test_text.py": 19,
    "test_text_properties.py": 1,
    "test_refusal_echo.py": 14,
    "test_cli_control_characters.py": 6,
    "test_label_properties.py": 2,
    "test_cli_finite.py": 3,
    "test_cli_flag_defaults.py": 6,
    "test_input.py": 18,
    "test_cli_input.py": 4,
    "test_cli_undecodable_argv.py": 1,
    "test_input_text.py": 17,
    "test_loader_properties.py": 7,
    "test_dependency_pins.py": 11,
    "test_density.py": 17,
    "test_report_file_names.py": 7,
    "test_json_repeated_key.py": 15,
    "test_cli_refusal_escape.py": 4,
    "test_cell_ceiling.py": 1,
    "test_bank_file_properties.py": 1,
    "test_grid_file_properties.py": 1,
    "test_island_letters_properties.py": 1,
    "test_mask_file_properties.py": 1,
    "test_terms_properties.py": 1,
    "test_word_list_properties.py": 1,
}


def _grouped_suite() -> unittest.TestSuite:
    """Discover every test module under tests/."""
    return unittest.TestLoader().discover(str(_TESTS), top_level_dir=str(_TESTS.parent))


def _iter_cases(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    """Yield every actual TestCase leaf out of a nested suite tree.

    unittest.TestLoader().discover() nests three deep (top, per-module,
    per-class), not the flat two levels a fixed-depth loop would assume; a
    module with more than one test class (test_grid.py has several) makes
    a two-level walk land on inner TestSuite objects instead of TestCase
    instances, miscounting every file. Recursing keeps this correct regardless
    of how many classes a grouped file has.
    """
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_cases(item)
        else:
            yield item


def _property_modules() -> Iterator[Path]:
    """Every module in `_PROPERTY_FOLDERS`, each folder's in name order."""
    for folder in _PROPERTY_FOLDERS:
        yield from sorted(folder.glob("*.py"))


def _settings_calls(path: Path, method: str) -> list[ast.Call]:
    """Every `settings.<method>(...)` call in `path`, read as source with `ast`.

    Never imported: importing a property module would run its `load_profile`,
    changing the process-wide default under every suite this run has yet to
    decorate.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == _SETTINGS
    ]


def _profile_names(path: Path, method: str) -> list[str]:
    """The profile name each `settings.<method>(...)` call in `path` passes.

    A name passed as anything but a leading string literal fails, because only
    a literal can be compared without running it.
    """
    names: list[str] = []
    for call in _settings_calls(path, method):
        first = call.args[0] if call.args else None
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            raise AssertionError(
                f"{path.name}: {_SETTINGS}.{method} is not passed a string literal "
                "first, so its profile name cannot be compared"
            )
        names.append(first.value)
    return names


def _passes_no_deadline(call: ast.Call) -> bool:
    """Whether `call` passes `deadline=None` as a keyword of its own."""
    return any(
        keyword.arg == _DEADLINE
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is None
        for keyword in call.keywords
    )


def _imports_given(node: ast.AST) -> bool:
    """Whether `node` is a `from hypothesis import ...` naming `given`."""
    return (
        isinstance(node, ast.ImportFrom)
        and node.module == _HYPOTHESIS
        and any(alias.name == _GIVEN for alias in node.names)
    )


def _decorated_with_given(node: ast.AST) -> bool:
    """Whether `node` is a definition decorated with `given`, bare or dotted."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    targets = [
        decorator.func if isinstance(decorator, ast.Call) else decorator
        for decorator in node.decorator_list
    ]
    return any(
        (isinstance(target, ast.Name) and target.id == _GIVEN)
        or (isinstance(target, ast.Attribute) and target.attr == _GIVEN)
        for target in targets
    )


def _uses_given(path: Path) -> bool:
    """Whether `path` imports `given` from Hypothesis or decorates with it.

    Read as source, for the reason `_settings_calls` gives.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        _imports_given(node) or _decorated_with_given(node) for node in ast.walk(tree)
    )


class TestSuiteDiscovery(unittest.TestCase):
    """The grouped suites are actually discovered and actually run."""

    def test_every_grouped_file_meets_its_floor(self) -> None:
        found: dict[str, int] = {}
        for case in _iter_cases(_grouped_suite()):
            module = sys.modules[type(case).__module__]
            name = Path(str(module.__file__)).name
            found[name] = found.get(name, 0) + 1
        self.assertEqual(
            sorted(found),
            sorted(_MIN_GROUPED_TESTS_BY_FILE),
            "tests/ discovery and _MIN_GROUPED_TESTS_BY_FILE disagree on which "
            f"files exist: found {sorted(found)}, mapped "
            f"{sorted(_MIN_GROUPED_TESTS_BY_FILE)}",
        )
        for filename, floor in _MIN_GROUPED_TESTS_BY_FILE.items():
            self.assertGreaterEqual(
                found.get(filename, 0),
                floor,
                f"tests/{filename} yielded {found.get(filename, 0)} tests, expected "
                f"at least {floor}: a test may have been removed from it",
            )


class TestHypothesisProfiles(unittest.TestCase):
    """Each property module loads a deadline-free profile that it alone registers."""

    def test_every_module_loads_the_profile_it_alone_registers(self) -> None:
        # Hypothesis keeps profiles in one process-wide registry keyed by name,
        # so a second registration of a name replaces the first, and what a
        # shared name holds would depend on which module the run imported last.
        registrars: dict[str, list[str]] = {}
        registering_folders: set[Path] = set()
        for path in _property_modules():
            where = f"{path.parent.name}/{path.name}"
            registered = _profile_names(path, _REGISTER_PROFILE)
            self.assertEqual(
                _profile_names(path, _LOAD_PROFILE),
                registered,
                f"{where} must load exactly the profiles it registers",
            )
            for name in registered:
                registrars.setdefault(name, []).append(where)
            if registered:
                registering_folders.add(path.parent)
        # Each folder is listed because it holds property modules, so one
        # yielding no registration means the scan missed them, and this test
        # and the deadline test below would pass over nothing.
        self.assertEqual(
            registering_folders,
            set(_PROPERTY_FOLDERS),
            "a property folder yielded no profile registration",
        )
        shared = {
            name: wheres for name, wheres in registrars.items() if len(wheres) > 1
        }
        self.assertEqual(
            shared, {}, "a profile name registered by more than one module"
        )

    def test_every_registered_profile_sets_no_deadline(self) -> None:
        """Every profile registration passes `deadline=None` on its own call.

        A per-example wall-clock deadline makes a property's verdict depend on
        how loaded the machine is rather than on whether the property holds: an
        example that passes can still overshoot once under contention and fail
        the run. Spelled on the call itself, because an explicit keyword
        overrides whatever a parent profile carries, and a value only a parent
        supplies cannot be read from source.
        """
        missing = [
            f"{path.parent.name}/{path.name}:{call.lineno}"
            for path in _property_modules()
            for call in _settings_calls(path, _REGISTER_PROFILE)
            if not _passes_no_deadline(call)
        ]
        self.assertEqual(
            missing, [], "a profile registered without deadline=None on its call"
        )

    def test_every_module_using_given_registers_a_profile(self) -> None:
        """Every module that uses `given` registers a profile through `settings`.

        Hypothesis binds a test's settings when `given` decorates it, so a
        module with no profile of its own runs under whichever one was loaded
        when it was imported: Hypothesis's default, which carries a deadline, or
        another module's. The other checks in this class see a registration
        only as a `settings.register_profile` call, so a module that registers
        only through another name for `settings` fails here, where those checks
        would pass it unseen.
        """
        unregistered = [
            f"{path.parent.name}/{path.name}"
            for path in _property_modules()
            if _uses_given(path) and not _settings_calls(path, _REGISTER_PROFILE)
        ]
        self.assertEqual(
            unregistered,
            [],
            f"a module using {_GIVEN} registers no profile through {_SETTINGS}",
        )


def load_tests(
    _loader: unittest.TestLoader, tests: unittest.TestSuite, _pattern: str | None
) -> unittest.TestSuite:
    """unittest's hook: run this module's own tests plus every grouped suite."""
    return unittest.TestSuite([tests, _grouped_suite()])


if __name__ == "__main__":
    unittest.main()
