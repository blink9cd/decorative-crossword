"""Every committed sample regenerates byte-identically from its own bank.

The samples are a hand-verification deliverable: a reader runs one command and
compares what lands on disk with what is committed beside the bank. That is
only worth anything if the committed files are still what the tool produces,
so this suite regenerates each one into a temporary folder and compares bytes.
A sample that has drifted from the tool is a test failure here rather than a
stale file nobody opens. The samples that read another sample's grid rather than
running `fill` are checked by `tests/test_samples_read.py`. What each `fill` sample
exists to show is read back out of its grid from the commands pinned here: the
`--source` samples' by `tests/test_samples_source.py`, most of the others' by
`tests/test_samples_content.py`, and the rest below.

`_CASES` below is the second copy of each invocation -- `samples/README.md`
carries the first, written for a human to paste. That duplication is
deliberate and is the cheapest form the rule can take: the README is prose
nothing executes, and a test that read the commands *out* of the README
would pass just as happily against a README that had drifted from the tool.
Pinning them here makes the drift fail the build; `samples/README.md` points
back here, so a reader who changes one knows to change the other.
"""

import json
import tempfile
import unittest
from pathlib import Path

import decorative_crossword
import cw_grid
import cw_mask
from tests import cli_fixtures, samples_fixtures


#: The budget every sample is pinned with, and the reason it is not the CLI's
#: default. `--time-budget 0` drops the wall clock; the node cap replaces it.
#: Without the pair, a sample's only stopping condition is elapsed real time,
#: which makes the byte comparisons below a measure of how busy the machine is
#: -- `wide` and `large_square` finish in about four seconds against a 30s
#: default, so under roughly 7x load the clock wins and the tool returns a
#: different, non-conforming grid. The cap is set well above what any case
#: needs (the largest spends about ten thousand nodes) because it is there to
#: bound a runaway, not to detect drift: the byte comparison already does that.
#: Sized against its own worst case: a case that conforms to nothing runs the
#: cap out in 23s here, under the 30s clock it replaces, while an ordinary case
#: stops on the answer instead of on the machine.
_PINNED_BUDGET = ["--time-budget", "0", "--max-steps", "50000"]

#: The pins `name_grid` gives, each one `--feature` value. Named once so the
#: command below and the test reading the committed grid cannot drift onto two
#: different positions -- the position IS what that sample demonstrates.
_NAME_GRID_PINS = ("JANE@0,0,across", "DOE@1,4,down")

#: The line `name_grid`'s phrase list must draw from its report: the two pins, joined.
_NAME_GRID_PAIR = "  JANE, across from (0, 0) + DOE, down from (1, 4) = JANEDOE"

#: What `best_grid` adds to `name_grid`'s bank and pins: an answer to prefer,
#: and the letters its islands may take. Named once so its command and the tests
#: reading its grid cannot drift apart.
_BEST_GRID_PREFER = "JOE"
_BEST_GRID_ISLAND_LETTERS = "AIX"

#: The kind `symmetric_grid` asks `--prefer-symmetry` for, named once so its
#: command and the test re-running it without the flag cannot drift apart.
_SYMMETRIC_GRID_KIND = "rotational"

#: What `two_banks` shows: the two answers only its second bank holds, both
#: featured, and that bank, which its command gives as a second --bank.
_TWO_BANKS_NAMES = ("JANE", "DOE")
_TWO_BANKS_SECOND = samples_fixtures.SAMPLES / "two_banks" / "names.json"

#: What `phrase_grid` features: two answers its bank writes as more than one
#: word, given AS WRITTEN, so the command itself shows a flag reaching an
#: answer through its space and its hyphen.
_PHRASE_GRID_FEATURES = ("HELLO THERE", "ATTA-BOY")

#: The pin `heart_mask` gives. Its column is the one column of the heart that
#: is free the whole way down, so a seven-letter answer pinned there is what
#: draws the point -- the shape's own feature, not decoration.
_HEART_MASK_FEATURE = "PROMISE@1,5,down"

#: The exact invocation behind each committed sample, minus the three path
#: options every case shares. Kept here rather than only in the README so a
#: drifting sample is a test failure, not a stale document.
_CASES: dict[str, list[str]] = {
    "small_square": ["--seed", "11", "--rows", "7", "--cols", "7", *_PINNED_BUDGET],
    "wide": [
        "--seed",
        "23",
        "--rows",
        "7",
        "--cols",
        "13",
        "--min-blocked",
        "40",
        "--max-blocked",
        "60",
        *_PINNED_BUDGET,
    ],
    "large_square": [
        "--seed",
        "5",
        "--rows",
        "13",
        "--cols",
        "13",
        "--max-blocked",
        "60",
        "--feature",
        "LEARNING",
        *_PINNED_BUDGET,
    ],
    "name_grid": [
        "--seed",
        "1",
        "--rows",
        "7",
        "--cols",
        "9",
        "--max-blocked",
        "55",
        "--min-entries-per-theme",
        "2",
        *(arg for pin in _NAME_GRID_PINS for arg in ("--feature", pin)),
        "--phrases",
        str(samples_fixtures.SAMPLES / "name_grid" / "phrases.txt"),
        # 450, not the default 500: the last fifty nodes reach a 37-letter grid
        # at 41.3% blocked, which rounds onto small_square's density, and the
        # set exists to show densities apart (test_the_densities_differ).
        "--look-ahead",
        "450",
        *_PINNED_BUDGET,
    ],
    "best_grid": [
        "--seed",
        "1",
        "--rows",
        "9",
        "--cols",
        "9",
        "--max-blocked",
        "55",
        "--min-entries-per-theme",
        "2",
        *(arg for pin in _NAME_GRID_PINS for arg in ("--feature", pin)),
        "--prefer",
        _BEST_GRID_PREFER,
        "--island-letters",
        _BEST_GRID_ISLAND_LETTERS,
        *_PINNED_BUDGET,
    ],
    "rated_grid": [
        "--seed",
        "1",
        "--rows",
        "6",
        "--cols",
        "8",
        "--max-blocked",
        "55",
        "--min-entries-per-theme",
        "2",
        *(arg for pin in _NAME_GRID_PINS for arg in ("--feature", pin)),
        *_PINNED_BUDGET,
    ],
    "symmetric_grid": [
        "--seed",
        "2",
        "--rows",
        "8",
        "--cols",
        "8",
        "--max-blocked",
        "55",
        "--min-entries-per-theme",
        "2",
        *(arg for pin in _NAME_GRID_PINS for arg in ("--feature", pin)),
        "--prefer-symmetry",
        _SYMMETRIC_GRID_KIND,
        *_PINNED_BUDGET,
    ],
    "partial_grid": [
        "--seed",
        "3",
        "--source",
        str(samples_fixtures.SAMPLES / "partial_grid" / "source.json"),
        "--max-blocked",
        "55",
        *_PINNED_BUDGET,
    ],
    # Seed 4 because a consumer may cap two-letter entries by width; seed 1
    # conforms here too, but with seven of them.
    "grown_grid": [
        "--seed",
        "4",
        "--source",
        str(samples_fixtures.SAMPLES / "grown_grid" / "source.json"),
        "--rows",
        "8",
        "--cols",
        "10",
        "--min-blocked",
        "35",
        "--max-blocked",
        "50",
        "--feature",
        "DOE@7,7,across",
        *_PINNED_BUDGET,
    ],
    "two_banks": [
        "--bank",
        str(_TWO_BANKS_SECOND),
        "--seed",
        "2",
        "--rows",
        "7",
        "--cols",
        "8",
        *(arg for name in _TWO_BANKS_NAMES for arg in ("--feature", name)),
        *_PINNED_BUDGET,
    ],
    "absorbed_grid": [
        "--seed",
        "1",
        "--source",
        str(samples_fixtures.SAMPLES / "absorbed_grid" / "source.json"),
        "--min-blocked",
        "20",
        "--max-blocked",
        "50",
        "--min-themes",
        "1",
        "--min-entries-per-theme",
        "2",
        "--absorb-entries",
        *_PINNED_BUDGET,
    ],
    "phrase_grid": [
        "--seed",
        "3",
        "--rows",
        "10",
        "--cols",
        "11",
        "--max-blocked",
        "60",
        *(arg for name in _PHRASE_GRID_FEATURES for arg in ("--feature", name)),
        *_PINNED_BUDGET,
    ],
    "heart_mask": [
        "--mask",
        str(samples_fixtures.SAMPLES / "heart_mask" / "shape.txt"),
        "--seed",
        "5",
        "--min-blocked",
        "20",
        "--max-blocked",
        "50",
        "--min-entries-per-theme",
        "2",
        "--feature",
        _HEART_MASK_FEATURE,
        # The one fill sample that draws its blocks as holes, because it is the
        # one whose point is the silhouette: with them inked the shape is a
        # rectangle with a heart inside it rather than a heart. The flag is NOT
        # implied by --mask, which is why it is written out here.
        "--empty-blocks",
        *_PINNED_BUDGET,
    ],
}

#: The answer `large_square` nominates with `--feature`. Named once so the
#: case above and the test that looks for it in the grid cannot drift onto two
#: different words.
_FEATURED = "LEARNING"


def _rows_of(name: str) -> list[str]:
    """The committed grid rows for one sample."""
    document = json.loads(
        (samples_fixtures.SAMPLES / name / "grid_source.json").read_text("utf-8")
    )
    rows: list[str] = document["rows"]
    return rows


class TestSamplesRegenerate(cli_fixtures.QuietCase):
    """A committed sample matches what the tool produces today.

    Driven through `decorative_crossword.main` rather than a subprocess: the
    entry point is what the README's command reaches anyway, and an in-process
    call keeps the assertion on the bytes rather than on a shell.
    """

    def _regenerate_into(self, name: str, folder: str) -> tuple[Path, Path]:
        """Run one sample's own command into `folder`; return the two outputs."""
        out = Path(folder) / "grid_source.json"
        svg = Path(folder) / "preview.svg"
        argv = [
            "fill",
            "--bank",
            str(samples_fixtures.SAMPLES / name / "bank.json"),
            "--out",
            str(out),
            "--preview",
            str(svg),
            *_CASES[name],
        ]
        self.assertEqual(
            decorative_crossword.main(argv),
            0,
            f"samples/{name} no longer conforms -- the tool's report is above",
        )
        return out, svg

    def _assert_matches(self, name: str) -> None:
        """Regenerate `name` and compare both artifacts byte for byte."""
        with tempfile.TemporaryDirectory() as folder:
            out, svg = self._regenerate_into(name, folder)
            for produced, committed in (
                (out, "grid_source.json"),
                (svg, "preview.svg"),
            ):
                self.assertEqual(
                    produced.read_bytes(),
                    (samples_fixtures.SAMPLES / name / committed).read_bytes(),
                    f"samples/{name}/{committed} has drifted -- regenerate it "
                    "with the command in samples/README.md",
                )

    def test_small_square_regenerates_byte_identically(self) -> None:
        self._assert_matches("small_square")

    def test_wide_regenerates_byte_identically(self) -> None:
        self._assert_matches("wide")

    def test_large_square_regenerates_byte_identically(self) -> None:
        self._assert_matches("large_square")

    def test_name_grid_regenerates_byte_identically(self) -> None:
        self._assert_matches("name_grid")

    def test_name_grid_reports_the_pair_its_phrase_list_joins(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self._regenerate_into("name_grid", folder)
        self.assertIn(_NAME_GRID_PAIR, self.printed.splitlines())

    def test_best_grid_regenerates_byte_identically(self) -> None:
        self._assert_matches("best_grid")

    def test_best_grid_reports_the_grid_it_writes(self) -> None:
        # Its two islands are letters on disk and in the preview's caption, so
        # the report counts them: 32 of 81 blocked, not the 34 the search chose.
        with tempfile.TemporaryDirectory() as folder:
            self._regenerate_into("best_grid", folder)
        self.assertIn(
            "Grid 9x9: 49 filled cells, 39.5% blocked (requested 30.0-55.0%).",
            self.printed.splitlines(),
        )

    def test_rated_grid_regenerates_byte_identically(self) -> None:
        self._assert_matches("rated_grid")

    def test_symmetric_grid_regenerates_byte_identically(self) -> None:
        self._assert_matches("symmetric_grid")

    def test_partial_grid_regenerates_byte_identically(self) -> None:
        self._assert_matches("partial_grid")

    def test_grown_grid_regenerates_byte_identically(self) -> None:
        self._assert_matches("grown_grid")

    def test_two_banks_regenerates_byte_identically(self) -> None:
        self._assert_matches("two_banks")

    def test_absorbed_grid_regenerates_byte_identically(self) -> None:
        self._assert_matches("absorbed_grid")

    def test_phrase_grid_regenerates_byte_identically(self) -> None:
        self._assert_matches("phrase_grid")

    def test_heart_mask_regenerates_byte_identically(self) -> None:
        self._assert_matches("heart_mask")

    def test_the_heart_mask_grid_leaves_every_masked_cell_empty(self) -> None:
        # The sample's whole claim, checked on the committed grid rather than on
        # the run: 41 of this grid's 88 cells may never hold a letter, and a
        # regeneration that honored only some of them would still match bytes
        # with a committed grid that had the same fault.
        rows = _rows_of("heart_mask")
        picture = (samples_fixtures.SAMPLES / "heart_mask" / "shape.txt").read_text(
            "utf-8"
        )
        mask = cw_mask.parse_mask(picture, "heart_mask")
        self.assertEqual((mask.rows, mask.cols), (len(rows), len(rows[0])))
        for row, col in sorted(mask.cells):
            self.assertEqual(rows[row][col], cw_grid.BLOCK, f"cell {row},{col}")

    def test_every_case_is_bounded_by_nodes_rather_than_by_a_wall_clock(self) -> None:
        # The wiring guard behind every byte comparison above: each case must
        # drop the clock and name the deterministic cap that replaces it, for
        # the reason _PINNED_BUDGET gives. Asserted on the argv rather than on
        # the outcome because a regenerated sample proves nothing about the run
        # that produced it.
        for name, argv in _CASES.items():
            with self.subTest(sample=name):
                self.assertIn("--time-budget", argv)
                self.assertEqual(argv[argv.index("--time-budget") + 1], "0")
                self.assertIn("--max-steps", argv)
                self.assertGreater(int(argv[argv.index("--max-steps") + 1]), 0)


class TestSampleShape(unittest.TestCase):
    """The set demonstrates the options, rather than one code path three times."""

    def test_every_sample_folder_has_a_pinned_case(self) -> None:
        """A folder added to samples/ without a case here would go unchecked."""
        folders = {
            path.name for path in samples_fixtures.SAMPLES.iterdir() if path.is_dir()
        }
        self.assertEqual(
            folders,
            set(_CASES)
            | {
                samples_fixtures.SHADE_SAMPLE,
                samples_fixtures.GAPS_SAMPLE,
                samples_fixtures.SILHOUETTE_SAMPLE,
            },
            "samples/ and the pinned cases disagree on which samples exist; an "
            "unpinned sample is one nothing regenerates",
        )

    def test_every_pinned_case_is_compared_byte_for_byte(self) -> None:
        """A case with no comparison pins a command whose output nothing checks."""
        uncompared = [
            name
            for name in _CASES
            if not hasattr(
                TestSamplesRegenerate, f"test_{name}_regenerates_byte_identically"
            )
        ]
        self.assertEqual(
            uncompared,
            [],
            "these pinned cases have no byte comparison, so their committed "
            "samples could drift from the tool unnoticed",
        )

    def test_wide_is_not_square(self) -> None:
        """--rows and --cols are two options, not one size wearing two names."""
        rows = _rows_of("wide")
        self.assertNotEqual(len(rows), len(rows[0]))

    def test_every_fill_sample_has_its_own_shape(self) -> None:
        """No two `fill` samples share a grid shape."""
        sizes = {(len(rows), len(rows[0])) for rows in map(_rows_of, _CASES)}
        self.assertEqual(len(sizes), len(_CASES))

    def test_the_densities_differ(self) -> None:
        """The blocked percentages land in visibly different places.

        Without this, every sample could sit at the default density and
        the set would demonstrate --min-blocked / --max-blocked not at all.
        """
        achieved = {round(cw_grid.blocked_percent(_rows_of(name))) for name in _CASES}
        self.assertEqual(len(achieved), len(_CASES))

    def test_the_large_sample_actually_places_the_featured_answer(self) -> None:
        """--feature is a hard constraint, so the answer must be IN the grid.

        Read off the grid's own runs, which is where the operator will look
        for it, rather than trusting the report the run printed.
        """
        self.assertIsNotNone(cw_grid.find_answer(_rows_of("large_square"), _FEATURED))
