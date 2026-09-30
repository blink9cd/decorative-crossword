"""Determinism as a property: the search says the same thing twice.

Over every generated seed rather than one pinned one -- the same seed, bank and
configuration reproduce the same outcome, in the claim's precise form: the
budgets decide only WHETHER the search reaches a conforming grid, never WHICH
grid it reaches.

The distinct-run invariant is `test_search_properties.py`.
The generated input space, and the regression seed pinned below, are in
`property_strategies/`; the seed lives there rather than here because the
non-vacuity property in the sibling suite pins it as well, and one seed with
two readers has one home.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook. The bootstrap below puts `property_strategies/`, the project
root and `src/` on `sys.path`, so a focused
`python -m unittest tests.test_search_determinism` from the project directory
resolves everything too.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "property_strategies"))
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import dataclasses  # noqa: E402 - import follows the sys.path bootstrap above
import cw_search  # noqa: E402 - same bootstrap

# Aliased to the private spellings the test bodies use (see the sibling suite).
from property_strategies import (  # noqa: E402 - same bootstrap
    BUDGET_MULTIPLIER as _BUDGET_MULTIPLIER,
)
from property_strategies import (  # noqa: E402 - same bootstrap
    BUDGET_SENSITIVE_REQUEST as _BUDGET_SENSITIVE_REQUEST,
)
from property_strategies import Request as _Request  # noqa: E402 - same bootstrap
from property_strategies import fill_requests as _fill_requests  # noqa: E402 - same
from property_strategies import frozen_clock as _frozen_clock  # noqa: E402 - same


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
    "crossword_search_determinism",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_search_determinism")


class TestDeterminismProperties(unittest.TestCase):
    """Determinism over every generated seed, not just the pinned one.

    Neither property here can flake on a loaded machine, and two mechanics are
    what rule that out. Every search is given `_frozen_clock`, so the wall-clock
    budget is unreachable and the only budget that can stop a walk is
    `--max-steps` -- a count of nodes, which a busy machine does not change. And
    the profile loaded at import sets `deadline=None`, so Hypothesis's own
    per-example timer cannot turn slowness into a reported falsification either.

    What they cannot see, stated so the gap is not mistaken for coverage: both
    runs happen in ONE process, where a `hash()`-derived ordering is stable.
    The cross-process half of the claim is pinned by
    `test_search.TestCrossProcessDeterminism`, which spawns children under
    different PYTHONHASHSEED values.
    """

    @given(_fill_requests())
    def test_the_same_inputs_reproduce_the_same_outcome(
        self, request: _Request
    ) -> None:
        bank, config = request
        first = cw_search.search(bank, config, clock=_frozen_clock)
        second = cw_search.search(bank, config, clock=_frozen_clock)
        # SearchOutcome is a frozen dataclass, so this compares every field of
        # the outcome -- not just the rows.
        self.assertEqual(first, second)

    @given(_fill_requests())
    @example(_BUDGET_SENSITIVE_REQUEST)
    def test_a_larger_step_budget_reaches_the_same_grid(
        self, request: _Request
    ) -> None:
        # Determinism stated precisely: the budgets decide only WHETHER the
        # search reaches a conforming grid, never WHICH grid. A run that exits 0
        # under the smaller budget therefore has to exit 0 on the same grid
        # under the larger one -- the node order is a pure function of the
        # inputs, so the larger budget re-walks the smaller one's prefix.
        #
        # With one stated exception, cw_search's own: a budget that closes the
        # run inside the look-ahead window keeps the best grid seen so far, and
        # a roomier one may keep a better. The outcome says so, so the claim is
        # checked exactly where it is made -- on a tight run whose look-ahead
        # was NOT cut -- rather than dropped.
        bank, config = request
        roomier = dataclasses.replace(
            config, max_steps=config.max_steps * _BUDGET_MULTIPLIER
        )
        tight = cw_search.search(bank, config, clock=_frozen_clock)
        loose = cw_search.search(bank, roomier, clock=_frozen_clock)
        self.assertLessEqual(
            tight.steps, loose.steps, "a larger budget can only cut later"
        )
        if not tight.conforming or tight.look_ahead_cut:
            return
        self.assertTrue(loose.conforming)
        self.assertEqual(tight.rows, loose.rows)
        self.assertEqual(tight.placed, loose.placed)


if __name__ == "__main__":
    unittest.main()
