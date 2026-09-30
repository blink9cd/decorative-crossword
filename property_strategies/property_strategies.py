"""The input space the search property suites explore, and their own run scan.

Nothing here asserts anything about the subject: the property suites in `tests/`
hold the assertions, and this module holds what they are asserted over. The
`scan_runs` below is the load-bearing piece -- it re-derives the distinct-run
rule's notion of a maximal run with a regex and its own coordinate arithmetic,
rather than calling `cw_grid.runs_from_rows`, because a property that asserted
the subject's own reading of the rule could not fail when that reading is the
thing that is wrong. The constants it borrows (`BLOCK`, `MIN_RUN`) are shared
values with one home, not the scanning logic under test.

**Why its own folder rather than `tests/`.** The suites import it by bare
name, and a bare-name import of a module inside `tests/` makes `mypy` report
the same file under two module names, because `tests/` is a package; a folder
that is NOT a package gives it one. Loose at the project root it would share
the entry point's folder, and this project gives each module that has
companions a folder of its own. This one has a companion: its sibling
`test_property_strategies.py` is its unit test, and it tests `scan_runs`
directly rather than only through the properties it serves.

Entry point assumptions: imported by bare name after the importer has put this
file's own directory on `sys.path`; the bootstrap below adds the project root
and `src/` for itself, so a direct import works from either caller.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_bank  # noqa: E402 - import follows the sys.path bootstrap above
import cw_config  # noqa: E402 - same bootstrap
import cw_feature  # noqa: E402 - same bootstrap
import cw_grid  # noqa: E402 - same bootstrap

#: One generated fill request: a bank, and the configuration to search it under.
#: Named so each suite can annotate its parameter without respelling the pair.
Request = tuple[cw_bank.Bank, cw_config.FillConfig]

# --- What the generated requests are made of ---------------------------------

#: A deliberately small alphabet. Four letters make crossings -- and therefore
#: the accidental perpendicular pairs the rule forbids -- far likelier than
#: twenty-six would, which is the pressure these properties exist to apply.
LETTERS = "ABCD"

#: Grid side bounds, drawn INDEPENDENTLY for rows and cols so NON-SQUARE grids
#: are in range -- the shape this project's defects have repeatedly hidden in.
MIN_SIDE = 5
MAX_SIDE = 7

#: One generated answer, never longer than the SHORTEST grid a request can ask
#: for. Derived from `MIN_SIDE` rather than repeated as a number, because the
#: relation is what matters: an answer that fits every drawn grid is what keeps
#: pre-flight from refusing on length and leaving a property asserting nothing.
_ANSWER = st.text(alphabet=LETTERS, min_size=cw_grid.MIN_RUN, max_size=MIN_SIDE)

#: Bank size bounds. Two answers are enough to cross; more than seven mostly
#: buys search time rather than new shapes.
MIN_ANSWERS = 2
MAX_ANSWERS = 7

#: The theme keys a generated bank may declare.
THEME_KEYS = ("a", "b", "c")

#: Blocked-percentage ceilings. A grid starts fully blocked and empties as
#: answers land, so the lower the ceiling the more entries the search must get
#: onto the board before a grid conforms. All three are worth drawing: the
#: loosest lets the search stop after one placement, and the tightest pushes it
#: into the crossing-heavy grids where those accidental perpendicular pairs
#: actually arise.
MAX_BLOCKED_CHOICES = (100.0, 85.0, 70.0)

#: No floor on blocked percentage: every grid these banks can build is sparse,
#: so a positive floor would be satisfied by construction and explore nothing.
MIN_BLOCKED = 0.0

#: Node budgets. The smallest is the SMALLEST that can work: `_budget_spent`
#: cuts the node that reaches the cap before it does anything, so a budget of N
#: leaves N-1 productive nodes, and three leaves exactly two -- the empty root
#: and the first placement under it. That is deliberate. A budget merely larger
#: than a typical search never cuts and so tests nothing: at forty nodes the cut
#: fired on two examples in four hundred, where three fires on most of them, and
#: a cut walk is the exit-1 path, whose grid the distinct-run rule binds
#: exactly as it binds a conforming one.
STEP_BUDGETS = (3, 60, 600)

#: How much larger the second budget is in the budget-independence property.
BUDGET_MULTIPLIER = 4

#: A wall-clock budget no property search can reach. Every search the property
#: suites run is given `frozen_clock`, so its elapsed time is always 0.0 and the
#: only budget that can stop a walk is the deterministic step cap.
UNREACHABLE_TIME_BUDGET = 3600.0

#: Percent, for turning a blocked-cell count into the figure density bounds.
PERCENT = 100

#: One maximal filled stretch, found by the regex below rather than by
#: `cw_grid._runs_in_line`'s accumulator -- see the module docstring.
_FILLED_STRETCH = re.compile(
    f"[^{re.escape(cw_grid.BLOCK)}]{{{cw_grid.MIN_RUN},}}",
)


def frozen_clock() -> float:
    """A clock stuck at zero, so no search given it can reach its wall-clock budget.

    `tests/search_fixtures.py` defines this as `still`. It is restated rather
    than imported so that this module, which the suites import, depends on
    nothing in the `tests` package.
    """
    return 0.0


class ScannedRun(NamedTuple):
    """A run this module found for itself: what it spells and where it lies."""

    text: str
    cells: tuple[tuple[int, int], ...]


def scan_runs(rows: tuple[str, ...]) -> tuple[ScannedRun, ...]:
    """Every maximal filled run of `cw_grid.MIN_RUN`-plus cells in `rows`.

    An independent reading of the distinct-run rule (module docstring): each scan
    line is matched with a regex and each match's offsets are turned back into
    grid coordinates here, so a defect in the subject's own run accumulator or
    in its direction table cannot hide inside this check as well.

    Assumes `rows` is rectangular; `test_the_emitted_grid_has_the_requested_shape`
    is what establishes that separately rather than this function assuming it
    quietly.
    """
    width = len(rows[0]) if rows else 0
    # (start cell, step per character, the characters along that line).
    lines: list[tuple[tuple[int, int], tuple[int, int], str]] = [
        ((index, 0), (0, 1), text) for index, text in enumerate(rows)
    ]
    lines += [
        ((0, index), (1, 0), "".join(row[index] for row in rows))
        for index in range(width)
    ]
    found: list[ScannedRun] = []
    for (start_row, start_col), (step_row, step_col), line in lines:
        for match in _FILLED_STRETCH.finditer(line):
            start = match.start()
            found.append(
                ScannedRun(
                    text=match.group(),
                    cells=tuple(
                        (
                            start_row + step_row * (start + offset),
                            start_col + step_col * (start + offset),
                        )
                        for offset in range(len(match.group()))
                    ),
                )
            )
    return tuple(found)


def filled_cells(rows: tuple[str, ...]) -> set[tuple[int, int]]:
    """Every cell in `rows` that holds a letter rather than a block."""
    return {
        (row_index, col_index)
        for row_index, row in enumerate(rows)
        for col_index, cell in enumerate(row)
        if cell != cw_grid.BLOCK
    }


#: The look-aheads a drawn request may carry. Zero is the first conforming grid;
#: the others make the walk keep going past it, so the properties also hold for
#: a grid CHOSEN among several rather than only for the first one found.
LOOK_AHEADS = (0, 3, 40)

#: Where a drawn pin goes: across the top-left corner. It is legal for every
#: request this strategy can draw, without a check: every drawn answer is at
#: most `MIN_SIDE` letters, so it always fits the top row, and a board holding
#: one answer holds exactly one run, which is that answer. A pin anywhere the
#: strategy had to test first would be a second copy of the validation it is
#: meant to feed.
ORIGIN_ACROSS = cw_feature.Anchor(0, 0, cw_grid.ACROSS)


@st.composite
def fill_requests(draw: st.DrawFn) -> Request:
    """A bank and a fill configuration that pre-flight will not refuse.

    What this CAN draw, stated because a property is only as good as its input
    space: `MIN_ANSWERS`-`MAX_ANSWERS` unique answers of
    `cw_grid.MIN_RUN`-`MIN_SIDE` letters over `LETTERS`; **non-square grids**,
    rows and cols drawn independently over `MIN_SIDE`-`MAX_SIDE`; **multi-theme
    banks** -- one to `len(THEME_KEYS)` declared themes, answers spread across
    them, and some answers unthemed; any seed, negative included; no featured
    answer, one bare one, or one pinned across the top-left corner; every
    ceiling in `MAX_BLOCKED_CHOICES`; and every budget in `STEP_BUDGETS`, the
    smallest of which cuts the walk short.

    What it deliberately CANNOT draw, first and above all, is a request
    pre-flight refuses: that comes back with an empty grid, on which every
    invariant below holds for free, so a strategy drawing them would leave these
    properties asserting nothing.
    `test_every_generated_request_is_accepted_and_searchable` is the pin that
    keeps that true as this strategy changes. Three narrower exclusions follow
    from it: a per-theme floor above one would make most requests unsatisfiable
    for banks this small; an answer longer than the grid would be refused on
    length; and entries carry no clue text, because nothing the search reads
    touches one. A positive `--min-blocked` is excluded for the OPPOSITE reason,
    and is not a pre-flight matter at all -- see `MIN_BLOCKED`.

    Two limits are named so they are not mistaken for coverage. **Most drawn
    grids hold one entry**: over 400 draws, 104 held two or more runs, and all
    126 draws at the smallest step budget held exactly one -- and a one-entry
    grid can exercise neither the rule's distinctness clause nor an
    accidental perpendicular pair. And **the tool's own default acceptance
    profile is entirely outside this space**: `cw_config.DEFAULTS` asks for a
    blocked band, a theme count and a per-theme floor, none of which banks this
    small could meet. Both are deliberate trades for a search that finishes in
    milliseconds; the defaults are exercised by the CLI and acceptance suites
    instead.
    """
    answers = draw(
        st.lists(_ANSWER, min_size=MIN_ANSWERS, max_size=MAX_ANSWERS, unique=True)
    )
    # The first answer is always themed, so at least one declared theme carries
    # an entry and a --min-themes of 1 is always reachable. Without it most
    # examples would fail pre-flight's theme-reach check.
    slots: list[str | None] = [draw(st.sampled_from(THEME_KEYS))]
    slots += draw(
        st.lists(
            st.sampled_from((*THEME_KEYS, None)),
            min_size=len(answers) - 1,
            max_size=len(answers) - 1,
        )
    )
    # sorted(), not the set itself: a Bank's theme map is walked by the search
    # (`_short_themes`), and a dict built by iterating a set takes its key order
    # from the hash seed -- so a fixture built that way would hand two processes
    # two different banks, undercutting what `test_search_determinism` asserts.
    declared = {
        key: cw_bank.ThemeInfo(label=key.upper(), summary=f"All about {key}")
        for key in sorted({s for s in slots if s is not None})
    }
    bank = cw_bank.Bank(
        themes=declared,
        entries=tuple(
            cw_bank.BankEntry(answer=answer, theme=theme, clue=None)
            for answer, theme in zip(answers, slots, strict=True)
        ),
    )
    config = cw_config.FillConfig(
        rows=draw(st.integers(min_value=MIN_SIDE, max_value=MAX_SIDE)),
        cols=draw(st.integers(min_value=MIN_SIDE, max_value=MAX_SIDE)),
        seed=draw(st.integers()),
        min_blocked=MIN_BLOCKED,
        max_blocked=draw(st.sampled_from(MAX_BLOCKED_CHOICES)),
        # The lower bound is 1 for NON-VACUITY, not for reachability -- 0 is a
        # legal floor, and trivially reachable. `MIN_BLOCKED` is 0.0 and
        # `MAX_BLOCKED_CHOICES` includes 100.0, and an EMPTY grid is 100%
        # blocked, which is inside [0, 100].
        # So for a drawn request with `max_blocked=100.0` and no feature, an
        # unmet theme floor is the only thing left that stops the empty root
        # conforming at step 1 -- and that needs `min_themes >= 1`. Measured on
        # a 5x6 two-answer request at that ceiling: min_themes=0 returns 0 runs
        # at step 1; min_themes=1 returns 1 run at step 2. At the lower bound
        # every property here -- distinct runs, no orphan cell, a conforming
        # grid meets every constraint -- would hold on an empty grid for free.
        # `test_every_generated_request_is_accepted_and_searchable` is what
        # would fail if this bound moved: it asserts `scan_runs` is non-empty.
        min_themes=draw(st.integers(min_value=1, max_value=len(declared))),
        min_entries_per_theme=1,
        time_budget=UNREACHABLE_TIME_BUDGET,
        max_steps=draw(st.sampled_from(STEP_BUDGETS)),
        features=draw(
            st.one_of(
                st.just(()),
                st.sampled_from(answers).map(
                    lambda answer: (cw_feature.Feature(answer, None),)
                ),
                st.sampled_from(answers).map(
                    lambda answer: (cw_feature.Feature(answer, ORIGIN_ACROSS),)
                ),
            )
        ),
        look_ahead=draw(st.sampled_from(LOOK_AHEADS)),
        prefer=(),
        island_letters=(),
    )
    return bank, config


#: The regression seed for the budget-independence claim, pinned as
#: an `@example` rather than left to the draw. Every field is one this strategy
#: could itself have drawn -- and every field the strategy owns a named source
#: for is DERIVED from it rather than restated, so that claim cannot go quietly
#: false when a bound moves. `test_property_strategies` checks the rest.
#:
#: It exists because a plausible mutation LOOKS
#: budget-independent and is not: truncating each node's ranked candidate list
#: to a prefix. At a prefix of one the walk is the leftmost spine, which IS an
#: initial segment of the wider walk's preorder, so both budgets reach the same
#: first conforming node; above one that argument fails, because a subtree the
#: narrow walk exhausts fruitlessly can yield, under the wider walk, a
#: conforming state EARLIER in preorder than the narrow walk's winner. Reached
#: by the draw only near three thousand examples; pinned, it costs one.
BUDGET_SENSITIVE_REQUEST = (
    cw_bank.Bank(
        themes={
            "a": cw_bank.ThemeInfo("A", "All about a"),
            "b": cw_bank.ThemeInfo("B", "All about b"),
        },
        entries=tuple(
            cw_bank.BankEntry(answer=answer, theme=theme, clue=None)
            for answer, theme in (
                ("BB", "a"),
                ("AAA", "a"),
                ("BBD", "a"),
                ("AA", "a"),
                ("BC", "a"),
                ("CBB", "a"),
                ("BA", "b"),
            )
        ),
    ),
    cw_config.FillConfig(
        rows=MIN_SIDE,
        cols=MIN_SIDE,
        seed=0,
        min_blocked=MIN_BLOCKED,
        max_blocked=MAX_BLOCKED_CHOICES[0],
        min_themes=2,
        min_entries_per_theme=1,
        time_budget=UNREACHABLE_TIME_BUDGET,
        max_steps=STEP_BUDGETS[-1],
        features=(cw_feature.Feature("BBD", None),),
        look_ahead=LOOK_AHEADS[0],
        prefer=(),
        island_letters=(),
    ),
)


#: The regression seed for the distinct-run rule's DISTINCTNESS clause -- "no answer may
#: appear twice in the grid" -- which the draw alone reaches too rarely to rely
#: on. Measured over 3,000 draws: a grid carrying a duplicate run comes up in
#: 1.8% of them, against 12.5% for a run that is not a bank answer at all. So
#: the membership half of the rule is reached by the draw many times over in
#: a hundred examples and the distinctness half is a coin flip: whether deleting
#: `grid_violations`' distinctness check is caught changes with unrelated edits,
#: because `derandomize=True` seeds from the test's own source text, so editing
#: a `@given` test's signature reshuffles every input it sees. A seed is the
#: only thing that survives that.
DUPLICATE_RUN_REQUEST = (
    cw_bank.Bank(
        themes={
            "a": cw_bank.ThemeInfo("A", "All about a"),
            "b": cw_bank.ThemeInfo("B", "All about b"),
            "c": cw_bank.ThemeInfo("C", "All about c"),
        },
        entries=tuple(
            cw_bank.BankEntry(answer=answer, theme=theme, clue=None)
            for answer, theme in (
                ("AA", "c"),
                ("DA", "b"),
                ("CCDCA", "a"),
                ("DDC", "a"),
            )
        ),
    ),
    cw_config.FillConfig(
        rows=MAX_SIDE,
        cols=MIN_SIDE,
        seed=-754,
        min_blocked=MIN_BLOCKED,
        max_blocked=MAX_BLOCKED_CHOICES[-1],
        min_themes=1,
        min_entries_per_theme=1,
        time_budget=UNREACHABLE_TIME_BUDGET,
        max_steps=STEP_BUDGETS[1],
        features=(cw_feature.Feature("DA", None),),
        look_ahead=LOOK_AHEADS[0],
        prefer=(),
        island_letters=(),
    ),
)

#: The regression seed for the distinct-run rule's THIRD invariant -- no filled cell may
#: lie outside an entry. `cw_place.grid_violations` is documented as SILENT
#: about that shape (`cw_place.py`, its own docstring): a lone letter touching
#: nothing forms no run, so the subject's own check passes it, and only a scan
#: comparing covered cells against filled ones sees it. Unpinned, the property
#: holding that scan caught the fault only when the draw happened to produce
#: one -- a property of one REVISION of the test and not of the test, which is
#: the lesson the seed above records, reaching here too.
#:
#: Measured against a single-fault mutant of `cw_place.apply_placement` that
#: records every cell of the span as newly filled, so undoing a placement erases
#: a crossing entry's letters and strands one: over this test as it stands plus
#: 40 revisions of it differing only by one inert body statement, the mutant
#: survived the whole module 2 of those 41 times unpinned, and 0 of 41 with this
#: seed. The perturbation has to be a STATEMENT: measured on this very test,
#: adding an inert comment to its body leaves its generated draws identical,
#: while an inert statement replaces every one of them.
ORPHAN_CELL_REQUEST = (
    cw_bank.Bank(
        themes={
            "a": cw_bank.ThemeInfo("A", "All about a"),
            "b": cw_bank.ThemeInfo("B", "All about b"),
            "c": cw_bank.ThemeInfo("C", "All about c"),
        },
        entries=tuple(
            cw_bank.BankEntry(answer=answer, theme=theme, clue=None)
            for answer, theme in (("AB", "a"), ("AAA", "b"), ("AAAC", "c"))
        ),
    ),
    cw_config.FillConfig(
        rows=MIN_SIDE,
        cols=MIN_SIDE,
        seed=0,
        min_blocked=MIN_BLOCKED,
        max_blocked=MAX_BLOCKED_CHOICES[0],
        min_themes=len(THEME_KEYS),
        min_entries_per_theme=1,
        time_budget=UNREACHABLE_TIME_BUDGET,
        max_steps=STEP_BUDGETS[1],
        features=(),
        look_ahead=LOOK_AHEADS[0],
        prefer=(),
        island_letters=(),
    ),
)

#: Every pinned seed, so `test_property_strategies` holds each to the strategy's
#: declared bounds without a per-seed line to forget to add.
PINNED_REQUESTS = (
    BUDGET_SENSITIVE_REQUEST,
    DUPLICATE_RUN_REQUEST,
    ORPHAN_CELL_REQUEST,
)
