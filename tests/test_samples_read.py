"""The `shade`, `gaps` and `preview --empty-blocks` samples regenerate, and still say what they are there to say.

Kept apart from the fill samples' suite, `tests/test_samples.py`, on the one seam these
share: each reads the grid another sample produced rather than running `fill`, which is
why none runs from the `_CASES` table the fill samples share. Each command below is the
second copy of one `samples/README.md` prints, for the reason that suite's docstring
gives.
"""

import tempfile
from pathlib import Path

import cw_svg
import decorative_crossword
from tests import cli_fixtures, samples_fixtures, svg_fixtures

#: The grid every command in this suite reads.
_SHADE_SOURCE = "large_square"

#: The word the shade sample places, and what the tool must still say about it.
#: Pinned as a triple so a drift in the CHOOSER -- which cells it picks, and
#: therefore how far they spread and what they cost -- fails here rather than
#: quietly changing what the sample demonstrates. The committed SVG is compared
#: byte for byte beside it, but the SVG alone would not say WHY those cells
#: were the right ones.
_HIDDEN_WORD = "LANTERN"

#: What the sample exists to demonstrate, pinned so a drift in the ANALYSIS
#: fails here rather than quietly changing what a reader is shown. The shared
#: pattern is the whole argument for grouping: three separate blocked cells
#: are one idea, and a report that split them into three lines would be the
#: wall of coordinates this subcommand exists to avoid.
_GAPS_SHARED_PATTERN = "?C"
_GAPS_SHARED_COUNT = 3
_GAPS_CEILING = "58.6"
_HIDDEN_ROWS_SPANNED = 6
_HIDDEN_CLUSTERING = 3


class TestHiddenWordSample(cli_fixtures.QuietCase):
    """The `shade` sample regenerates, and still says what it is there to say."""

    def _shade(self, *extra: str) -> int:
        """Run one shade command against the committed source grid."""
        return decorative_crossword.main(
            [
                "shade",
                "--source",
                str(samples_fixtures.SAMPLES / _SHADE_SOURCE / "grid_source.json"),
                *extra,
            ]
        )

    def test_the_render_regenerates_byte_identically(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "hidden.svg"
            self.assertEqual(self._shade("--word", _HIDDEN_WORD, "--out", str(out)), 0)
            self.assertEqual(
                out.read_bytes(),
                (
                    samples_fixtures.SAMPLES
                    / samples_fixtures.SHADE_SAMPLE
                    / "hidden.svg"
                ).read_bytes(),
                f"samples/{samples_fixtures.SHADE_SAMPLE}/hidden.svg has drifted -- regenerate "
                "it with the command in samples/README.md",
            )

    def test_the_placed_word_still_scatters(self) -> None:
        """The sample's whole point is the CONTRAST it demonstrates.

        A chooser that started clustering would still produce a report and an
        SVG, and the byte comparison above would catch the change without
        saying what broke. This says it: the sample word still spreads across
        many rows and costs almost nothing, at the figures pinned above.
        """
        self.assertEqual(self._shade("--word", _HIDDEN_WORD), 0)
        self.assertIn(
            f"{_HIDDEN_WORD}: {len(_HIDDEN_WORD)} cells across "
            f"{_HIDDEN_ROWS_SPANNED} row(s), clustering {_HIDDEN_CLUSTERING}",
            self.printed,
        )

    def test_the_word_list_command_ranks_that_word_first(self) -> None:
        code = self._shade(
            "--words",
            str(samples_fixtures.SAMPLES / samples_fixtures.SHADE_SAMPLE / "words.txt"),
            "--exclude-grid-answers",
        )
        self.assertEqual(code, 0)
        self.assertIn(f"{_HIDDEN_WORD} - {len(_HIDDEN_WORD)} letters", self.printed)
        # Scoped to the candidates block by its own heading rather than to the
        # first indented line anywhere: several blocks carry indented detail,
        # and the claim here is about the RANKING, not about the report's
        # overall shape.
        lines = self.printed.splitlines()
        heading = next(
            index
            for index, line in enumerate(lines)
            if line.startswith("Hidden-word candidates")
        )
        self.assertIn(_HIDDEN_WORD, lines[heading + 1])

    def test_the_word_list_shows_the_skip_and_the_exclusion(self) -> None:
        """Both are documented behaviors, and the sample exists to show them."""
        self._shade(
            "--words",
            str(samples_fixtures.SAMPLES / samples_fixtures.SHADE_SAMPLE / "words.txt"),
            "--exclude-grid-answers",
        )
        self.assertIn("Skipped word-list lines", self.printed)
        self.assertIn("Already answers in this grid", self.printed)


class TestGapsSample(cli_fixtures.QuietCase):
    """The `gaps` sample regenerates, and still says what it is there to say."""

    def _gaps(self, *extra: str) -> int:
        """Run one gaps command against the committed source grid and bank."""
        return decorative_crossword.main(
            [
                "gaps",
                "--source",
                str(samples_fixtures.SAMPLES / _SHADE_SOURCE / "grid_source.json"),
                "--bank",
                str(samples_fixtures.SAMPLES / _SHADE_SOURCE / "bank.json"),
                *extra,
            ]
        )

    def test_the_render_regenerates_byte_identically(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "gaps.svg"
            self.assertEqual(self._gaps("--out", str(out)), 0)
            self.assertEqual(
                out.read_bytes(),
                (
                    samples_fixtures.SAMPLES / samples_fixtures.GAPS_SAMPLE / "gaps.svg"
                ).read_bytes(),
                f"samples/{samples_fixtures.GAPS_SAMPLE}/gaps.svg has drifted -- regenerate it "
                "with the command in samples/README.md",
            )

    def test_one_pattern_still_serves_several_gaps(self) -> None:
        """Grouping is the sample's whole point, so it is asserted, not implied."""
        self.assertEqual(self._gaps(), 0)
        self.assertIn(
            f"{_GAPS_SHARED_PATTERN} - {_GAPS_SHARED_COUNT} gaps", self.printed
        )

    def test_the_report_still_names_a_runnable_ceiling(self) -> None:
        """The half that closes the loop: a bank answer alone changes nothing."""
        self._gaps()
        self.assertIn(f"--max-blocked {_GAPS_CEILING}", self.printed)

    def test_the_cap_still_bites_and_says_so(self) -> None:
        """A sparse grid is exactly where --top earns its keep."""
        self._gaps()
        self.assertIn("cheapest of", self.printed)

    def test_this_bank_pays_for_none_of_them(self) -> None:
        """The honest outcome on a real grid, and the reason the tool exists.

        Every gap here needs an answer that does not yet exist, which is the
        demand-on-the-bank the tool's one rule already implies -- made
        specific. A vocabulary that started paying for one would change what
        the sample demonstrates, so it is pinned rather than assumed.
        """
        self._gaps()
        self.assertIn("0 ready now", self.printed)


class TestSilhouetteSample(cli_fixtures.QuietCase):
    """The `preview --empty-blocks` sample regenerates, and still shows the look."""

    def _preview(self, out: Path, *extra: str) -> int:
        """Draw the committed source grid into `out`, with `extra`."""
        return decorative_crossword.main(
            [
                "preview",
                "--source",
                str(samples_fixtures.SAMPLES / _SHADE_SOURCE / "grid_source.json"),
                "--out",
                str(out),
                *extra,
            ]
        )

    def test_the_render_regenerates_byte_identically(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "shape.svg"
            self.assertEqual(self._preview(out, "--empty-blocks"), 0)
            self.assertEqual(
                out.read_bytes(),
                (
                    samples_fixtures.SAMPLES
                    / samples_fixtures.SILHOUETTE_SAMPLE
                    / "shape.svg"
                ).read_bytes(),
                f"samples/{samples_fixtures.SILHOUETTE_SAMPLE}/shape.svg has drifted "
                "-- regenerate it with the command in samples/README.md",
            )

    def test_the_committed_sample_paints_no_block(self) -> None:
        """What the sample exists to show, asserted rather than implied."""
        committed = (
            samples_fixtures.SAMPLES / samples_fixtures.SILHOUETTE_SAMPLE / "shape.svg"
        ).read_text(encoding="utf-8")
        self.assertNotIn(cw_svg.BLOCK_CLASS, svg_fixtures.cell_classes(committed))
        self.assertIn(cw_svg.EMPTY_BLOCK_CLASS, svg_fixtures.cell_classes(committed))

    def test_the_same_grid_without_the_flag_still_paints_blocks(self) -> None:
        """The control: the sample differs by the FLAG, not by its source grid."""
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "filled.svg"
            self.assertEqual(self._preview(out), 0)
            classes = svg_fixtures.cell_classes(out.read_text(encoding="utf-8"))
            self.assertIn(cw_svg.BLOCK_CLASS, classes)
