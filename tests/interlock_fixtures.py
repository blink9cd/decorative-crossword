"""Fixtures for the interlocked-grid suites: one dense grid no partial run can fake.

The grid has the shape of a dense hand-made 5x5 the search must be able to reach.
Every cell carries a different letter, so every run is a nonsense string that
exists only as itself, and no partial run can ever be an answer by accident.

Named `*_fixtures.py` rather than `test_*.py` so the aggregator's discovery skips
it, like every `*_fixtures.py` module here.
"""

import cw_grid

#: The target. `.` is a block; the top-left corner is a block too, because an
#: orphan letter is something the search itself never produces.
TARGET = ("..ABC", ".DEFG", "HIJKL", "MNOPQ", "RST.U")

#: Every run in the target, read off it rather than written out a second time.
RUNS = tuple(cw_grid.runs_from_rows(TARGET))

#: A bank of exactly the target's runs, and nothing that could stand in for one.
ANSWERS = tuple(run.text for run in RUNS)

#: The target reflected across its diagonal. Every ACROSS run becomes a DOWN run,
#: so the same bank fills it just as legally.
TRANSPOSED = tuple("".join(row[col] for row in TARGET) for col in range(len(TARGET[0])))

#: Four blocked cells of 25: the target's own density, so only a full fill conforms.
TARGET_BLOCKED = 16.0

#: A second letter for the one cell the bottom row and the first column share.
#: With these two answers in the bank the pinned grid has exactly two fills,
#: tied on letters and differing only in which pair of answers they use.
ALTERNATE_ANSWERS = ("VST", "HMV")

#: The other of those two fills.
ALTERNATE = ("..ABC", ".DEFG", "HIJKL", "MNOPQ", "VST.U")


def run_at(direction: str, index: int) -> cw_grid.Run:
    """The target's run along row or column `index` in `direction`."""
    return next(
        run
        for run in RUNS
        if run.direction == direction
        and (run.row if direction == cw_grid.ACROSS else run.col) == index
    )


def pinned_lines() -> tuple[cw_grid.Run, ...]:
    """The middle column and two rows through it -- the lines a name grid would pin.

    Pinning them fixes the orientation, which an empty board leaves to the seed.
    """
    return (
        run_at(cw_grid.DOWN, 2),
        run_at(cw_grid.ACROSS, 3),
        run_at(cw_grid.ACROSS, 1),
    )
