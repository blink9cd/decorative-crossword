"""cw_select: what a search state is worth, and choosing among conforming grids.

A search can reach several grids that meet every constraint. `fill` keeps walking
for `--look-ahead` nodes past the first and keeps the best by `grid_score`: most
letters, then answers named by `--prefer`, then the grid's worst rating, then its
matching cell pairs under `--prefer-symmetry`, then themed entries, then the
`--absorb-entries` source entries still standing. That ORDER is the rule.
Letters come first because density is what a decorative grid is judged on at a
glance; a named preference comes next because it is the operator's instruction for
this one run; the worst rating is their standing judgment of word quality, written
into the bank, which nothing this tool measures could stand in for; themes break what
is left. Keeping a source entry
comes last, so growing one happens whenever it pays on any other level and never
merely because the walk happened to try it first.

Symmetry (`cw_symmetry`) sits below the worst rating and above themes, and its count
is fine-grained -- dozens of values against a rating's five -- so while it is asked
for, the levels under it rarely decide. Below the rating, a word rated a clunker
still loses however balanced its grid, while symmetry keeps nearly every other tie,
because ratings are coarse. Above themes, because a kind is asked for in this run
and the themed count is a default nobody asked for. Without the flag the level is
zero for every grid, so it never moves a choice.

The rating level reads the WORST entry, never an average. Averaging hides one clunker
behind a row of good words, and a reader notices the clunker. An unrated answer counts
as `cw_bank.NEUTRAL_RATING`, so a bank that rates nothing ties every grid on this
level, and the level never moves a choice.

The window is counted in NODES from the FIRST conforming grid, and a better grid does
not reopen it. Nodes rather than seconds, so the grid chosen is a function of the
request and not of the machine; from the first grid rather than from each better one,
so a long run of small improvements cannot keep a search open indefinitely. A tie keeps
the grid found first, which is what makes a look-ahead that finds nothing better leave
a run's output exactly as it was.

`Snapshot` lives here rather than beside the walk because it is the unit a selection
is made of: one state, its acceptance verdict, and its best-effort rank.

Determinism: the one set here is a membership test that is never iterated, and the
one dict is read by key, never iterated.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import cw_accept
import cw_bank
import cw_config
import cw_grid
import cw_place
import cw_symmetry

#: A conforming grid's worth, compared as a tuple: letters, preferred answers
#: present, worst rating, matching cell pairs under the asked-for symmetry, themed
#: entries, growable source entries still standing.
GridScore = tuple[int, int, int, int, int, int]


@dataclass(frozen=True)
class Snapshot:
    """One valid grid state, kept so it can be returned after backtracking.

    `rows` and `placed` are immutable copies rather than views of the live
    grid, which is what lets the search undo a placement and still return the
    state it found underneath it.
    """

    rows: tuple[str, ...]
    placed: tuple[cw_place.Placement, ...]
    missed: tuple[str, ...]
    rank: tuple[int, float, int]


def snapshot(
    rows: tuple[str, ...],
    placed: tuple[cw_place.Placement, ...],
    bank: cw_bank.Bank,
    config: cw_config.FillConfig,
) -> Snapshot:
    """Capture one state, with its acceptance verdict and its best-effort rank.

    The rank orders the best NON-conforming state: theme floor met, then
    distance from the density window, then entries placed. Higher is better,
    so the distance is negated. Conforming states are ordered by `grid_score`
    instead.
    """
    return Snapshot(
        rows=rows,
        placed=placed,
        missed=cw_accept.missed_constraints(rows, bank, config),
        rank=(
            cw_accept.themes_meeting_floor(rows, bank, config),
            -cw_accept.density_distance(rows, config),
            len(cw_grid.runs_from_rows(rows)),
        ),
    )


def worst_rating(rows: Sequence[str], bank: cw_bank.Bank) -> int:
    """The lowest rating among the grid's entries, an unrated one counting as neutral.

    A run the bank holds no rating for -- unrated, or not a bank answer at all,
    which `fill` never writes -- reads as `cw_bank.NEUTRAL_RATING`, and so does a
    grid with no entries, since nothing in it is worse. The report names this
    same figure, so it is computed here once.
    """
    rated = {
        entry.answer: entry.rating for entry in bank.entries if entry.rating is not None
    }
    return min(
        (
            rated.get(run.text, cw_bank.NEUTRAL_RATING)
            for run in cw_grid.runs_from_rows(rows)
        ),
        default=cw_bank.NEUTRAL_RATING,
    )


def grid_score(
    rows: Sequence[str],
    bank: cw_bank.Bank,
    prefer: Sequence[str],
    growable: Sequence[cw_grid.Run] = (),
    symmetry: str | None = None,
) -> GridScore:
    """A conforming grid's worth, level by level: letters first, kept entries last.

    Compared as a tuple, so each count only matters when every earlier one
    ties. The balance count is `cw_symmetry.matching_pairs` under `symmetry`,
    the `--prefer-symmetry` kind; without one it is zero for every grid, so it
    chooses nothing. Themed entries are counted by `cw_accept.theme_counts`, the
    one place that decides which runs carry a theme. The last count is how many
    of `growable` -- the source entries `--absorb-entries` lets grow
    (`cw_board.growable_runs`) -- the grid still holds as their exact runs.
    Without that flag `growable` is empty and the count is zero for every grid,
    so it chooses nothing either.
    """
    letters = sum(1 for row in rows for cell in row if cell != cw_grid.BLOCK)
    runs = cw_grid.runs_from_rows(rows)
    entries = [run.text for run in runs]
    preferred = sum(1 for answer in prefer if answer in entries)
    balanced = 0 if symmetry is None else cw_symmetry.matching_pairs(rows, symmetry)[0]
    themed = sum(cw_accept.theme_counts(rows, bank).values())
    standing = sum(1 for run in growable if run in runs)
    return letters, preferred, worst_rating(rows, bank), balanced, themed, standing


@dataclass
class Selection:
    """The best conforming grid seen so far, and the window it is chosen within.

    Not frozen: offers arrive as the walk proceeds. `compared` counts DISTINCT
    grids, because two placement orders can reach the same one and the report
    says how many grids were compared, not how many times.
    """

    look_ahead: int
    chosen: Snapshot | None = None
    compared: int = 0
    _score: GridScore = field(default=(0, 0, 0, 0, 0, 0), init=False)
    _closes_at: int | None = field(default=None, init=False)
    _seen: set[tuple[str, ...]] = field(default_factory=set, init=False)

    def offer(self, candidate: Snapshot, score: GridScore, steps: int) -> None:
        """Consider one conforming grid, reached at node `steps`.

        The first opens the window. Later ones replace the choice only on a
        strictly higher score, so a tie keeps the grid found first.
        """
        if candidate.rows not in self._seen:
            self._seen.add(candidate.rows)
            self.compared += 1
        if self.chosen is None:
            self._closes_at = steps + self.look_ahead
        elif score <= self._score:
            return
        self.chosen = candidate
        self._score = score

    def closed(self, steps: int) -> bool:
        """Whether node `steps` lies past the window; never before the first offer."""
        return self._closes_at is not None and steps >= self._closes_at
