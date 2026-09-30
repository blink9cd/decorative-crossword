"""The distinct-run rule as a property: the search's construction guarantee.

Stated over generated banks, seeds and grid sizes rather than over examples --
for any bank and any seed, every maximal run
of two or more filled cells in the emitted grid is a distinct bank answer, and
no filled cell lies outside such a run. The shape and acceptance invariants
that travel with it are here too.

Determinism is `test_search_determinism.py`; the bank parser's property is
`test_properties.py`, which holds the `test_fuzz_parse_bank` paired with its
`# fuzz-target` marker. The generated input space and the independent run scan
this suite asserts over are in
`property_strategies/`, in their own folder rather than in `tests/` for the
reason that module's docstring records.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook. The bootstrap below puts `property_strategies/`, the project
root and `src/` on `sys.path`, so a focused
`python -m unittest tests.test_search_properties` from the project directory
resolves everything too.
"""

from __future__ import annotations

import sys
import unittest
from fractions import Fraction
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "property_strategies"))
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_accept  # noqa: E402 - import follows the sys.path bootstrap above
import cw_config  # noqa: E402 - same bootstrap
import cw_grid  # noqa: E402 - same bootstrap
import cw_search  # noqa: E402 - same bootstrap

# Aliased to the private spellings the test bodies use, so the shared machinery
# is defined once, in property_strategies.
from property_strategies import PERCENT as _PERCENT  # noqa: E402 - same bootstrap
from property_strategies import (  # noqa: E402 - same bootstrap
    BUDGET_SENSITIVE_REQUEST as _BUDGET_SENSITIVE_REQUEST,
)
from property_strategies import (  # noqa: E402 - same bootstrap
    DUPLICATE_RUN_REQUEST as _DUPLICATE_RUN_REQUEST,
)
from property_strategies import (  # noqa: E402 - same bootstrap
    ORPHAN_CELL_REQUEST as _ORPHAN_CELL_REQUEST,
)
from property_strategies import Request as _Request  # noqa: E402 - same bootstrap
from property_strategies import fill_requests as _fill_requests  # noqa: E402 - same
from property_strategies import filled_cells as _filled_cells  # noqa: E402 - same
from property_strategies import frozen_clock as _frozen_clock  # noqa: E402 - same
from property_strategies import scan_runs as _scan_runs  # noqa: E402 - same


# Hypothesis settings come from a REGISTERED profile, loaded at import
# and before any class body, never an `@settings` decorator. A `@given` test
# snapshots its settings when it is DECORATED, so the load has to have happened
# by the time the class body below executes.
#
# Its own profile NAME, not one any other property module registers:
# `load_profile` sets a single global default, so two modules sharing one name
# would leave the last import deciding what both had already snapshotted. A
# distinct name per module makes each module's settings independent of the order
# unittest happens to import them in, and lets any one be tuned without the
# others silently inheriting it.
#
# `derandomize=True` fixes the example sequence, so the in-suite run cannot
# flake. `deadline=None` because a per-example wall-clock deadline would let a
# loaded machine report slowness as a falsification.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_search_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_search_properties")


class TestGridInvariantProperties(unittest.TestCase):
    """The distinct-run rule over generated banks and seeds, not over examples."""

    # The pinned seed goes through this one too. `test_search_determinism`'s
    # budget property returns early unless the tight run conforms, so nothing
    # there would notice the day the pin stopped producing a searchable grid --
    # it would simply stop testing, silently. This is the same non-vacuity pin
    # the module already applies to the drawn space, applied to the seed.
    @given(_fill_requests())
    @example(_BUDGET_SENSITIVE_REQUEST)
    @example(_DUPLICATE_RUN_REQUEST)
    @example(_ORPHAN_CELL_REQUEST)
    def test_every_generated_request_is_accepted_and_searchable(
        self, request: _Request
    ) -> None:
        bank, config = request
        # The CLI would accept this configuration: the properties below explore
        # the real input space rather than one no operator could ask for.
        cw_config.validate_fill_config(config)
        self.assertEqual(
            cw_accept.preflight(bank, config),
            (),
            "a refused request returns an empty grid, on which every other "
            "property in this module would hold vacuously",
        )
        outcome = cw_search.search(bank, config, clock=_frozen_clock)
        self.assertTrue(
            _scan_runs(outcome.rows),
            "a request pre-flight did not refuse must put at least one answer "
            "on the board",
        )

    # Pinned because the draw reaches this clause far more rarely than the
    # membership half sitting beside it in the same assertion. The rates, and
    # what makes them a property of one REVISION of this test rather than of
    # the test, are recorded once where the seed itself lives:
    # `property_strategies.DUPLICATE_RUN_REQUEST`.
    @given(_fill_requests())
    @example(_DUPLICATE_RUN_REQUEST)
    def test_every_run_is_a_distinct_bank_answer(self, request: _Request) -> None:
        bank, config = request
        outcome = cw_search.search(bank, config, clock=_frozen_clock)
        allowed = {entry.answer for entry in bank.entries}
        texts = [run.text for run in _scan_runs(outcome.rows)]
        for text in texts:
            self.assertIn(text, allowed, f"run {text!r} is not a bank answer")
        self.assertEqual(
            len(texts), len(set(texts)), f"an answer appears twice in {texts}"
        )

    # Pinned for the reason the seed above is: the shape this assertion exists
    # for is rare in the draw, so an unpinned kill is a property of one revision
    # of this test rather than of the test. The mutant it was measured against,
    # and the survival counts either side of the pin, are recorded once, on
    # `property_strategies.ORPHAN_CELL_REQUEST`.
    @given(_fill_requests())
    @example(_ORPHAN_CELL_REQUEST)
    def test_no_filled_cell_lies_outside_an_entry(self, request: _Request) -> None:
        # The rule's third invariant, which `cw_place.grid_violations` is
        # documented as being SILENT about: a lone letter touching nothing forms
        # no run, so the subject's own check passes it. Only a scan that
        # compares covered cells against filled ones can see it.
        bank, config = request
        outcome = cw_search.search(bank, config, clock=_frozen_clock)
        covered = {cell for run in _scan_runs(outcome.rows) for cell in run.cells}
        self.assertEqual(_filled_cells(outcome.rows), covered)

    @given(_fill_requests())
    def test_the_emitted_grid_has_the_requested_shape(self, request: _Request) -> None:
        bank, config = request
        outcome = cw_search.search(bank, config, clock=_frozen_clock)
        self.assertEqual(len(outcome.rows), config.rows)
        self.assertEqual(
            sorted({len(row) for row in outcome.rows}),
            [config.cols],
            "every row must be exactly --cols wide, and the grid rectangular",
        )

    @given(_fill_requests())
    def test_a_conforming_grid_meets_every_acceptance_constraint(
        self, request: _Request
    ) -> None:
        # The three acceptance constraints, re-derived from the grid here
        # rather than read back out of `outcome.missed`: `missed` is what the
        # search decides conformance WITH, so trusting it would let a dropped
        # check report a clean grid and be believed.
        bank, config = request
        outcome = cw_search.search(bank, config, clock=_frozen_clock)
        if not outcome.conforming:
            return
        runs = _scan_runs(outcome.rows)
        # Exact, as acceptance judges it: a float quotient lands a hair either
        # side of a bound the grid sits exactly on, and would call a grid the
        # search rightly accepted out of its window. Each bound is the decimal
        # the flag spells, which `str` of the float recovers.
        blocked = Fraction(
            sum(row.count(cw_grid.BLOCK) for row in outcome.rows) * _PERCENT,
            config.rows * config.cols,
        )
        self.assertGreaterEqual(blocked, Fraction(str(config.min_blocked)))
        self.assertLessEqual(blocked, Fraction(str(config.max_blocked)))
        index = bank.by_answer()
        counts: dict[str, int] = {}
        for run in runs:
            entry = index.get(run.text)
            if entry is not None and entry.theme is not None:
                counts[entry.theme] = counts.get(entry.theme, 0) + 1
        deep_enough = sum(
            1 for count in counts.values() if count >= config.min_entries_per_theme
        )
        self.assertGreaterEqual(deep_enough, config.min_themes)
        for feature in config.features:
            self.assertIn(feature.answer, [run.text for run in runs])


if __name__ == "__main__":
    unittest.main()
