"""Tests for cw_search: the search, its budgets, and its byte-identical output.

The pure parts it is assembled from are tested in test_search_parts.py.
"""

import dataclasses
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import cw_accept
import cw_bank
import cw_config
import cw_grid
import cw_order
import cw_place
import cw_search

# Aliased to the private spellings the test bodies use, so a fixture shared
# across the cw_search suites is still defined exactly once (see search_fixtures).
from tests import search_fixtures
from tests.search_fixtures import bank as _bank
from tests.search_fixtures import config as _config
from tests.search_fixtures import entries_bank as _entries_bank
from tests.search_fixtures import one_theme_bank as _one_theme_bank
from tests.search_fixtures import still as _still
from tests.search_fixtures import themed_bank as _themed_bank

#: src/, for the child interpreter the determinism test spawns. Derived from
#: this file's own location so the suite survives a move.
_SRC = Path(__file__).resolve().parent.parent / "src"

#: A wall-clock budget no search here can reach, so the only budget that can
#: stop those searches is the deterministic step cap.
_LONG_BUDGET = 3600.0

#: A step budget generous enough to reach the dense window below.
_LONG_STEPS = 20000

#: Seconds before a spawned child is abandoned: a bound on a blocking call,
#: not a guess at the search's duration (it runs in well under a second).
_CHILD_TIMEOUT = 120.0

#: A window that needs several crossing answers, not just the seed: 9x9 is 81
#: cells, so 80% blocked means at least 17 must be filled, which 5-letter
#: answers crossing at one cell each reach in four placements.
_DENSE_WINDOW = 80.0

#: The seed the candidate-ordering tests run under. Chosen, not arbitrary: it
#: is a seed whose tie-break key prefers the losing candidate in both of those
#: tests, so a scoring term dropped from the wiring flips the emitted grid
#: instead of leaving the outcome to the hash.
_ADVERSARIAL_SEED = 9

#: The PYTHONHASHSEED values the cross-process determinism test runs under.
#: Different values salt builtin hash() differently, so a search that took an
#: ordering from a set (or a dict built from one) returns two different grids.
_HASH_SEEDS = ("0", "524287")

_CHILD_PROGRAM = """\
import json
import pathlib
import sys

sys.path.insert(0, sys.argv[1])

import cw_bank
import cw_config
import cw_search

bank = cw_bank.parse_bank(json.loads(sys.argv[2]))
fields = json.loads(sys.argv[3])
fields["masked"] = frozenset((row, col) for row, col in fields["masked"])
config = cw_config.FillConfig(**fields)
outcome = cw_search.search(bank, config)
pathlib.Path(sys.argv[4]).write_text(
    json.dumps({"rows": list(outcome.rows), "conforming": outcome.conforming}),
    encoding="utf-8",
)
"""


def _mixed_bank() -> cw_bank.Bank:
    """The themed bank plus two unthemed answers: a legal bank shape.

    Derived from `themed_bank` rather than written out again, so the two cannot
    drift into disagreeing about what the themed half contains.
    """
    base = _themed_bank()
    unthemed = tuple(
        cw_bank.BankEntry(answer=answer, theme=None, clue=None)
        for answer in ("DRIFT", "GLOVE")
    )
    return cw_bank.Bank(themes=base.themes, entries=base.entries + unthemed)


def _dense_config(max_steps: int = _LONG_STEPS) -> cw_config.FillConfig:
    """A configuration whose window only a multi-answer grid can reach.

    The step budget is the one field a caller varies: it is what the
    "budgets decide whether, never which" claim is tested against.
    """
    return _config(
        max_blocked=_DENSE_WINDOW, max_steps=max_steps, time_budget=_LONG_BUDGET
    )


@dataclasses.dataclass(frozen=True)
class _ChildOutcome:
    """The half of a SearchOutcome a spawned child reports back."""

    rows: tuple[str, ...]
    conforming: bool


def _run_child(
    bank: cw_bank.Bank, config: cw_config.FillConfig, hash_seed: str
) -> _ChildOutcome:
    """Search in a fresh interpreter under `hash_seed`, and return its outcome.

    The bank and the config cross the process boundary as JSON derived from the
    caller's own objects, so the child cannot drift from what the parent ran.
    """
    payload = json.dumps(
        {
            # ThemeInfo is a dataclass, which json.dumps refuses; the child
            # reads a bank file, so each record is written in its on-disk
            # shape rather than by serializing the object.
            "themes": {
                key: {"label": info.label, "summary": info.summary}
                for key, info in bank.themes.items()
            },
            "entries": [
                {"answer": entry.answer, "theme": entry.theme} for entry in bank.entries
            ],
        }
    )
    with tempfile.TemporaryDirectory() as scratch:
        result_path = Path(scratch) / "outcome.json"
        # No capture_output/stdout/stderr, deliberately: a timeout on a
        # capturing call kills only the direct child and then blocks re-reading
        # pipes a grandchild still holds. Handing the child a file to write
        # leaves the bound genuinely binding, and lets a failing child's
        # traceback reach the runner's own stderr.
        subprocess.run(
            [
                sys.executable,
                "-c",
                _CHILD_PROGRAM,
                str(_SRC),
                payload,
                json.dumps(search_fixtures.wire_config(config)),
                str(result_path),
            ],
            timeout=_CHILD_TIMEOUT,
            check=True,
            env=dict(os.environ, PYTHONHASHSEED=hash_seed),
        )
        decoded = json.loads(result_path.read_text(encoding="utf-8"))
    return _ChildOutcome(
        rows=tuple(decoded["rows"]), conforming=bool(decoded["conforming"])
    )


class TestSearch(unittest.TestCase):
    """The search places words, honors its budgets, and is reproducible."""

    def test_places_something_on_a_reachable_request(self) -> None:
        outcome = cw_search.search(_themed_bank(), _config())
        self.assertTrue(outcome.placed)

    def test_is_byte_identical_for_the_same_seed(self) -> None:
        first = cw_search.search(_themed_bank(), _config())
        second = cw_search.search(_themed_bank(), _config())
        self.assertEqual(first.rows, second.rows)

    def test_differs_for_a_different_seed(self) -> None:
        # Not a guarantee of the algorithm, but a guard that the seed is wired
        # through at all: a search ignoring it would return identical grids.
        first = cw_search.search(_themed_bank(), _config(seed=1))
        second = cw_search.search(_themed_bank(), _config(seed=99))
        self.assertNotEqual(first.rows, second.rows)

    def test_respects_the_grid_dimensions(self) -> None:
        outcome = cw_search.search(_themed_bank(), _config(rows=7, cols=11))
        self.assertEqual(len(outcome.rows), 7)
        self.assertTrue(all(len(row) == 11 for row in outcome.rows))

    def test_stops_at_the_step_budget(self) -> None:
        outcome = cw_search.search(_themed_bank(), _config(max_steps=1))
        self.assertLessEqual(outcome.steps, 1)

    def test_stops_at_the_time_budget(self) -> None:
        # An injected clock that leaps past the budget on its second reading, so
        # the deadline fires without the test waiting for anything.
        readings = iter([0.0, 0.0, 999.0, 999.0, 999.0])
        outcome = cw_search.search(
            _themed_bank(),
            _config(max_steps=0, time_budget=1.0),
            clock=lambda: next(readings, 999.0),
        )
        self.assertFalse(outcome.conforming)

    def test_a_walk_cut_at_its_root_still_counts_that_node(self) -> None:
        # The report tells a refusal from a walk by `steps == 0` alone, which
        # holds only because the root counts itself before its budget check. A
        # clock past the budget at that very first check must leave one step,
        # not the zero a refusal reports. The clock, not `max_steps=1`: under a
        # swapped check that cap cuts the root's first child, still one step.
        bank = _themed_bank()
        config = _config(max_steps=0, time_budget=1.0)
        readings = iter([0.0])
        outcome = cw_search.search(bank, config, clock=lambda: next(readings, 999.0))
        self.assertEqual(cw_accept.preflight(bank, config), ())
        self.assertEqual(outcome.steps, 1)

    def test_a_zero_time_budget_disables_the_wall_clock(self) -> None:
        # Zero is "no limit", the same reading `--max-steps` has, and it is
        # what lets a caller ask for a run whose result does not depend on
        # machine speed: under a live clock, a search that merely runs slowly
        # returns a different, worse, grid rather than a later one. A clock
        # that leaps past any budget on its every reading must therefore change
        # neither the grid nor the node count.
        runaway = iter([0.0])
        pinned = cw_search.search(
            _themed_bank(),
            dataclasses.replace(_dense_config(), time_budget=0.0),
            clock=lambda: next(runaway, 10.0**9),
        )
        reference = cw_search.search(_themed_bank(), _dense_config(), clock=_still)
        self.assertTrue(pinned.conforming)
        self.assertEqual(pinned.rows, reference.rows)
        self.assertEqual(pinned.steps, reference.steps)

    def test_places_the_featured_answer_where_the_grid_can_be_read(self) -> None:
        # Read back out of `rows` rather than out of `placed`, and
        # unconditionally: guarding this on `outcome.conforming`
        # makes it a test that disables itself the moment the search stops
        # short, which is exactly when a feature would go missing.
        outcome = cw_search.search(
            _themed_bank(), _config(feature="ALPHA"), clock=_still
        )
        self.assertTrue(outcome.conforming)
        self.assertIsNotNone(cw_grid.find_answer(outcome.rows, "ALPHA"))

    def test_places_a_feature_another_bank_answer_contains(self) -> None:
        # CAT is a proper substring of CATS. The feature is a hard constraint
        # on the grid's entries, so it has to be present as a
        # run of its own: a scan for its letters in a row string would accept
        # a grid holding only CATS, and the render would then shade cells for
        # an entry that does not exist.
        outcome = cw_search.search(
            _one_theme_bank(["CATS", "CAT"]),
            _config(rows=5, cols=5, feature="CAT"),
            clock=_still,
        )
        self.assertTrue(outcome.conforming)
        # The whole Run, not just its presence: these are the coordinates the
        # render shades, so pinning them is what a coordinate bug has to move.
        self.assertEqual(
            cw_grid.find_answer(outcome.rows, "CAT"),
            cw_grid.Run(row=1, col=2, direction=cw_grid.DOWN, text="CAT"),
        )

    def test_names_the_missed_constraint(self) -> None:
        # A density window nothing can reach: the outcome must say which
        # constraint failed, not merely that one did.
        outcome = cw_search.search(
            _themed_bank(), _config(min_blocked=0.0, max_blocked=0.0, max_steps=200)
        )
        self.assertFalse(outcome.conforming)
        self.assertTrue(outcome.missed)

    def test_every_run_in_the_result_is_a_bank_answer(self) -> None:
        # The construction guarantee, asserted directly.
        import cw_place

        bank = _themed_bank()
        outcome = cw_search.search(bank, _config())
        allowed = {entry.answer for entry in bank.entries}
        self.assertEqual(cw_place.grid_violations(outcome.rows, allowed), ())


class TestUnsatisfiableRequests(unittest.TestCase):
    """Refused before the search, not after the budget."""

    def test_spends_no_step_on_a_request_pre_flight_refuses(self) -> None:
        # An unthemed bank can never meet a positive theme floor, and this
        # config asks for one, so no amount of searching would help. (A floor
        # of zero is a different request, and tests/test_cli_themeless.py runs
        # it end to end.)
        unthemed = _bank(["ALPHA", "BRAVO"])
        outcome = cw_search.search(unthemed, _config(), clock=_still)
        self.assertEqual(outcome.steps, 0)
        self.assertEqual(outcome.placed, ())
        self.assertFalse(outcome.conforming)
        self.assertEqual(outcome.missed, cw_search.preflight(unthemed, _config()))

    def test_still_returns_a_grid_of_the_requested_size(self) -> None:
        outcome = cw_search.search(
            _bank(["ALPHA"]), _config(rows=4, cols=6), clock=_still
        )
        self.assertEqual(outcome.rows, (cw_grid.BLOCK * 6,) * 4)


class TestSeedPlacement(unittest.TestCase):
    """The one placement with no crossing to anchor it."""

    def test_seeds_with_the_featured_answer(self) -> None:
        featured = cw_search.search(
            _themed_bank(), _config(feature="CHALK"), clock=_still
        )
        plain = cw_search.search(_themed_bank(), _config(), clock=_still)
        # The unfeatured search picks a different word, so a search that merely
        # allowed the feature somewhere would not satisfy this.
        self.assertNotEqual(plain.placed[0].answer, "CHALK")
        self.assertEqual(featured.placed[0].answer, "CHALK")

    def test_seeds_at_the_centered_position(self) -> None:
        outcome = cw_search.search(
            _themed_bank(), _config(rows=7, cols=11, feature="CEDAR"), clock=_still
        )
        seed = outcome.placed[0]
        self.assertEqual(
            (seed.row, seed.col),
            cw_order._centered_start(7, 11, len("CEDAR"), seed.direction),
        )

    def test_seeds_on_an_even_grid(self) -> None:
        # Every other seed test uses odd dimensions, where (n - 1) // 2 and
        # n // 2 agree and the centering arithmetic cannot be told apart from
        # either. On 8 rows the ACROSS row is 3, not 4. A nine-letter answer
        # leaves the DOWN alternative starting at row -1, so `fits` drops it
        # and the winning placement is fixed without appealing to the seed.
        outcome = cw_search.search(
            _one_theme_bank(["CROSSWORD"]),
            _config(rows=8, cols=10, feature="CROSSWORD"),
            clock=_still,
        )
        self.assertTrue(outcome.conforming)
        self.assertEqual(
            outcome.placed[0],
            cw_place.Placement("CROSSWORD", 3, 0, cw_grid.ACROSS),
        )

    def test_seeds_down_when_across_does_not_fit(self) -> None:
        # A 7-letter answer in a 5-wide grid: the centered ACROSS start is at
        # column -1, so only the DOWN alternative survives `fits`.
        outcome = cw_search.search(
            _one_theme_bank(["CRUMPET"]),
            _config(rows=9, cols=5, feature="CRUMPET"),
            clock=_still,
        )
        self.assertEqual(outcome.placed[0].direction, cw_grid.DOWN)
        self.assertEqual((outcome.placed[0].row, outcome.placed[0].col), (1, 2))


class TestCandidateOrdering(unittest.TestCase):
    """The candidate ordering, observed through the grid a search emits.

    TestSortKey (in test_order) pins the key itself; these pin that
    `cw_order.ordered_candidates` actually feeds it both terms. Each case is built so
    the seeded tie-break prefers the candidate that must lose, which is what
    makes a dropped term change the emitted grid rather than leave it to the
    hash. The 9x5 shape puts the seven-letter feature DOWN the middle column
    with only one fitting placement per remaining answer, so the choice under
    test is the only one the node has.
    """

    def _board(self) -> cw_config.FillConfig:
        """The 9x5 board both cases below run on."""
        return _config(
            rows=9, cols=5, seed=_ADVERSARIAL_SEED, max_blocked=80.0, feature="CRUMPET"
        )

    def test_prefers_the_candidate_that_fills_more_cells(self) -> None:
        # BLUES adds four cells, PA one, and both sit in the one satisfied
        # theme, so the fill count is the only term with anything to say.
        bank = _entries_bank(
            (("CRUMPET", "a"), ("BLUES", "a"), ("PA", "a")), {"a": "A"}
        )
        outcome = cw_search.search(bank, self._board(), clock=_still)
        self.assertTrue(outcome.conforming)
        self.assertEqual(outcome.placed[1].answer, "BLUES")

    def test_prefers_an_answer_whose_theme_is_short(self) -> None:
        # BLUES and SHEEP both add four cells, so the fill term ties. The seed
        # has already satisfied theme "a"; theme "b" is still short, so SHEEP
        # must be tried first.
        bank = _entries_bank(
            (("CRUMPET", "a"), ("BLUES", "a"), ("SHEEP", "b")), {"a": "A", "b": "B"}
        )
        outcome = cw_search.search(bank, self._board(), clock=_still)
        self.assertTrue(outcome.conforming)
        self.assertEqual(outcome.placed[1].answer, "SHEEP")


class TestBudgets(unittest.TestCase):
    """Budgets decide whether a grid is reached, never which one."""

    def test_counts_one_step_per_node(self) -> None:
        # An unreachable window, so the cap is what stops the walk. Asserted as
        # equality: a budget checked only at the node that trips it lets every
        # open frame start one more child, and the count overruns.
        outcome = cw_search.search(
            _themed_bank(),
            _config(min_blocked=0.0, max_blocked=0.0, max_steps=3),
            clock=_still,
        )
        self.assertEqual(outcome.steps, 3)

    def test_keeps_the_best_effort_state(self) -> None:
        # Every state here is non-conforming, so the one returned must be the
        # best seen rather than the empty grid the search started from.
        outcome = cw_search.search(
            _themed_bank(),
            _config(min_blocked=0.0, max_blocked=0.0, max_steps=200),
            clock=_still,
        )
        self.assertTrue(outcome.placed)
        for placement in outcome.placed:
            self.assertIsNotNone(cw_grid.find_answer(outcome.rows, placement.answer))

    def test_fills_several_answers_for_a_denser_window(self) -> None:
        outcome = cw_search.search(_themed_bank(), _dense_config(), clock=_still)
        self.assertTrue(outcome.conforming)
        self.assertGreaterEqual(len(outcome.placed), 3)
        self.assertEqual(
            cw_place.grid_violations(
                outcome.rows, {entry.answer for entry in _themed_bank().entries}
            ),
            (),
        )

    def test_conforms_under_a_deeper_theme_floor(self) -> None:
        # The suite's only end-to-end search with min_themes > 1 and
        # min_entries_per_theme > 1, over a bank mixing themed and unthemed
        # answers, which is a legal bank shape. Every other search here
        # meets its floor with the seed placement alone.
        bank = _mixed_bank()
        config = _config(
            min_themes=2,
            min_entries_per_theme=2,
            max_steps=_LONG_STEPS,
            time_budget=_LONG_BUDGET,
        )
        outcome = cw_search.search(bank, config, clock=_still)
        self.assertTrue(outcome.conforming)
        self.assertEqual(cw_accept.themes_meeting_floor(outcome.rows, bank, config), 2)

    def test_a_looser_budget_finds_the_same_grid(self) -> None:
        tight = cw_search.search(_themed_bank(), _dense_config(), clock=_still)
        loose = cw_search.search(
            _themed_bank(), _dense_config(max_steps=0), clock=_still
        )
        self.assertTrue(tight.conforming)
        self.assertTrue(loose.conforming)
        self.assertEqual(tight.rows, loose.rows)
        self.assertEqual(tight.placed, loose.placed)

    def test_skips_a_placement_that_fills_nothing(self) -> None:
        # CAT lies inside CATS, so re-placing it over those cells fills nothing
        # and leaves the state identical: a node whose child is its own
        # parent. Without the zero-progress filter that recurses until the
        # interpreter gives up, so the assertion is that the call returns.
        outcome = cw_search.search(
            _one_theme_bank(["CATS", "CAT"]),
            _config(
                rows=5,
                cols=5,
                min_blocked=0.0,
                max_blocked=0.0,
                max_steps=0,
                time_budget=_LONG_BUDGET,
            ),
            clock=_still,
        )
        self.assertFalse(outcome.conforming)
        self.assertTrue(outcome.placed)


class TestCrossProcessDeterminism(unittest.TestCase):
    """The byte-identical claim, proven where it can actually break."""

    def test_is_identical_under_different_hash_seeds(self) -> None:
        bank = _themed_bank()
        config = _dense_config()
        outcomes = [_run_child(bank, config, seed) for seed in _HASH_SEEDS]
        for outcome in outcomes:
            self.assertTrue(outcome.conforming)
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(
            outcomes[0].rows, cw_search.search(bank, config, clock=_still).rows
        )
