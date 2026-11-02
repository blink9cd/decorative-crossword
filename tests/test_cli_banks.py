"""Grouped suite: `--bank` given more than once, at the process boundary.

`fill` and `gaps` merge every `--bank` into one bank, in the order the flags are
given. What the merge decides is `test_bank_merge.py`'s; these cases prove each
handler hands over every bank (to the merge, to the output-path check and to
the repeated-file check), and that everything downstream of the bank sees the
merged one: a `--feature`, a `--prefer`, the `--excluded-terms` screen, the
report, `gaps`' vocabulary and its answer pairs.

**Flag order orders the report, never the grid.** The search sorts its
candidates on a ranking and a seeded hash of each placement
(`cw_order.ordered_candidates`), which no two candidates share, and the emitted
document follows the grid's own runs, so a grid is the same bytes whichever
bank comes first, and measured so. What the order does reach is every report
block that lists the bank, which is what `TestFillOrder` pins, beside the grid
bytes staying put.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import tempfile
import unittest
from pathlib import Path

import decorative_crossword
from tests import cli_fixtures
from tests.test_cli_gaps import GapsSpace

#: The answer only the second bank holds. It names theme `a`, which only the
#: first bank declares, and crosses that bank's answers on a 9x9 grid.
SECOND_ANSWER = "LANCE"

#: Ten letters, so it never fits the 9x9 grid and is always listed unplaced:
#: where it sits in that list is where its bank sits in the merge.
UNPLACEABLE = "XYLOPHONES"

#: A per-grid bank's entries: the answer above, and one that can never be placed.
#: Their own constant so a hand-merged bank can spread them under their own type.
NAMES_ENTRIES: list[dict[str, str]] = [
    {"answer": SECOND_ANSWER, "theme": "a"},
    {"answer": UNPLACEABLE},
]

#: The per-grid bank itself, declaring no theme of its own.
NAMES_BANK: dict[str, object] = {"themes": {}, "entries": NAMES_ENTRIES}


def _write(path: Path, payload: dict[str, object]) -> Path:
    """Write `payload` as JSON at `path`; return the path."""
    path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
    return path


def _with_banks(argv: list[str], *banks: Path) -> list[str]:
    """`argv` with its one `--bank` pair replaced by one pair per bank, in order."""
    index = argv.index("--bank")
    argv[index : index + 2] = [part for bank in banks for part in ("--bank", str(bank))]
    return argv


def _unplaced(printed: str) -> list[str]:
    """The answers the report lists as unplaced, in the order listed."""
    lines = printed.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Unplaced"))
    block = lines[start + 1 : lines.index("", start)]
    return [line.split(" - ")[0].strip() for line in block]


class BanksSpace(cli_fixtures.Workspace):
    """The shared workspace, plus a second bank beside its first."""

    def __init__(self, folder: str, names: dict[str, object] | None = None) -> None:
        """Write both banks into `folder`."""
        super().__init__(folder)
        self.names = _write(self.root / "names.json", names or NAMES_BANK)

    def merged(self, *extra: str) -> list[str]:
        """A `fill` argv giving the first bank, then the second."""
        return self.fill("--bank", str(self.names), *extra)


class TestFillMerges(cli_fixtures.QuietCase):
    """One `fill` run draws on every bank it is given."""

    def test_a_grid_draws_answers_from_both_banks(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = BanksSpace(folder)
            code = decorative_crossword.main(space.merged("--feature", SECOND_ANSWER))
            clues = space.clues()
        self.assertEqual(code, 0)
        self.assertEqual(clues[SECOND_ANSWER]["theme"], "a")
        first_bank = {entry["answer"] for entry in cli_fixtures.ENTRIES}
        self.assertTrue(first_bank & set(clues), "no answer of the first bank placed")

    def test_the_report_names_each_bank_in_order_with_its_count(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = BanksSpace(folder)
            decorative_crossword.main(space.merged("--feature", SECOND_ANSWER))
        self.assertIn(
            f"Merged 2 bank files, in the order given: {space.bank} (9 entries), "
            f"{space.names} (2 entries).",
            self.printed.splitlines(),
        )
        self.assertIn("Placed 7 of 11 bank entries.", self.printed.splitlines())

    def test_a_bank_of_one_entry_is_counted_in_the_singular(self) -> None:
        names: dict[str, object] = {
            "themes": {},
            "entries": [{"answer": SECOND_ANSWER, "theme": "a"}],
        }
        with tempfile.TemporaryDirectory() as folder:
            space = BanksSpace(folder, names)
            decorative_crossword.main(space.merged())
        self.assertIn(f"{space.names} (1 entry).", self.printed)

    def test_a_lone_bank_prints_no_merge_line(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            decorative_crossword.main(cli_fixtures.Workspace(folder).fill())
        self.assertNotIn("bank files", self.printed)

    def test_an_identical_record_in_both_banks_is_counted_once(self) -> None:
        names: dict[str, object] = {
            "themes": {},
            "entries": [{"answer": "AMBER", "theme": "a"}, {"answer": SECOND_ANSWER}],
        }
        with tempfile.TemporaryDirectory() as folder:
            code = decorative_crossword.main(BanksSpace(folder, names).merged())
        self.assertEqual(code, 0)
        self.assertIn("of 10 bank entries.", self.printed)


class TestFillOrder(cli_fixtures.QuietCase):
    """The flag order orders the report's lists and leaves the grid's bytes alone."""

    def test_flag_order_orders_the_report_and_not_the_grid(self) -> None:
        grids: list[bytes] = []
        listed: list[list[str]] = []
        with tempfile.TemporaryDirectory() as folder:
            space = BanksSpace(folder)
            for banks in ((space.bank, space.names), (space.names, space.bank)):
                start = len(self.printed)
                argv = _with_banks(space.fill("--feature", SECOND_ANSWER), *banks)
                self.assertEqual(decorative_crossword.main(argv), 0)
                grids.append(space.out.read_bytes())
                listed.append(_unplaced(self.printed[start:]))
        self.assertEqual(grids[0], grids[1])
        self.assertEqual(listed[0][-1], UNPLACEABLE)
        self.assertEqual(listed[1][0], UNPLACEABLE)
        self.assertEqual(listed[0][:-1], listed[1][1:])

    def test_two_banks_write_what_one_bank_holding_both_writes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = BanksSpace(folder)
            together = _write(
                space.root / "together.json",
                {
                    "themes": cli_fixtures.THEMES,
                    "entries": [*cli_fixtures.ENTRIES, *NAMES_ENTRIES],
                },
            )
            merged_out = space.root / "merged.json"
            decorative_crossword.main(space.merged("--out", str(merged_out)))
            single = _with_banks(space.fill(), together)
            decorative_crossword.main(single)
            self.assertEqual(merged_out.read_bytes(), space.out.read_bytes())


class TestFillRefusals(cli_fixtures.QuietCase):
    """Every disagreement between banks, and every misused bank path, is exit 2."""

    def assert_refused(self, space: BanksSpace, argv: list[str], *named: str) -> None:
        """The run exits 2, writes no grid, prints no report, and names each of `named`."""
        self.assertEqual(decorative_crossword.main(argv), 2)
        self.assertFalse(space.out.exists())
        self.assertEqual(self.printed, "")
        for part in named:
            self.assertIn(part, self.errors)

    def test_an_answer_recorded_differently_in_two_banks_is_refused(self) -> None:
        names: dict[str, object] = {
            "themes": {},
            "entries": [{"answer": "AMBER", "theme": "a", "clue": "Fossil resin"}],
        }
        with tempfile.TemporaryDirectory() as folder:
            space = BanksSpace(folder, names)
            self.assert_refused(
                space, space.merged(), "'AMBER'", str(space.bank), str(space.names)
            )

    def test_a_theme_declared_differently_in_two_banks_is_refused(self) -> None:
        names: dict[str, object] = {
            "themes": {"a": {"label": "A", "summary": "Some other summary"}},
            "entries": [{"answer": SECOND_ANSWER, "theme": "a"}],
        }
        with tempfile.TemporaryDirectory() as folder:
            space = BanksSpace(folder, names)
            self.assert_refused(
                space, space.merged(), "theme 'a'", str(space.bank), str(space.names)
            )

    def test_the_same_bank_given_twice_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = BanksSpace(folder)
            (space.root / "sub").mkdir()
            again = space.root / "sub" / ".." / "bank.json"
            self.assert_refused(space, space.fill("--bank", str(again)), "twice")

    def test_out_naming_either_bank_is_refused(self) -> None:
        # Both, because each catches a different broken handler: one handing
        # over only the last bank (what a non-repeating flag keeps) lets the
        # first be written over, and one handing over only the first lets the
        # second be.
        with tempfile.TemporaryDirectory() as folder:
            space = BanksSpace(folder)
            for target in (space.bank, space.names):
                with self.subTest(bank=target.name):
                    before = target.read_bytes()
                    code = decorative_crossword.main(space.merged("--out", str(target)))
                    self.assertEqual(target.read_bytes(), before)
                    self.assertEqual(code, 2)
                    self.assertIn(f"names the --bank file {target}", self.errors)


class TestFillScreens(cli_fixtures.QuietCase):
    """The flags that check answers against the bank check the merged one."""

    def test_prefer_sees_an_answer_only_the_second_bank_holds(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            code = decorative_crossword.main(
                BanksSpace(folder).merged("--prefer", SECOND_ANSWER)
            )
        self.assertIn(code, (0, 1))
        self.assertNotIn("not in the bank", self.errors)

    def test_excluded_terms_screen_the_second_bank(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = BanksSpace(folder)
            terms = space.excluded(SECOND_ANSWER.lower())
            code = decorative_crossword.main(
                space.merged("--excluded-terms", str(terms))
            )
        self.assertIn(code, (0, 1))
        self.assertIn(
            f"  {SECOND_ANSWER} - its answer matches the excluded term "
            f"{SECOND_ANSWER.lower()!r}",
            self.printed.splitlines(),
        )


class TestGapsMerges(cli_fixtures.QuietCase):
    """`gaps` draws its vocabulary, and its answer pairs, from every bank."""

    def argv(self, space: GapsSpace, second: Path, *extra: str) -> list[str]:
        """A `gaps` argv giving the grid's own bank, then `second`."""
        return space.argv("--bank", str(space.bank), "--bank", str(second), *extra)

    def test_a_gap_only_the_second_bank_pays_is_ready(self) -> None:
        # AGO pays the `A?O` gap with G; the first bank pays only `C?D`, with O.
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            second = _write(
                space.root / "names.json",
                {"themes": {}, "entries": [{"answer": "AGO"}]},
            )
            code = decorative_crossword.main(self.argv(space, second))
        self.assertEqual(code, 0)
        self.assertIn("take G", self.printed)
        self.assertIn("take O", self.printed)

    def test_answer_pairs_join_against_the_second_bank(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            second = _write(
                space.root / "names.json",
                {"themes": {}, "entries": [{"answer": "CATDOG"}]},
            )
            decorative_crossword.main(self.argv(space, second))
        # The first bank's own gap too: a run that kept only the last --bank
        # would join against CATDOG and lose COD.
        self.assertIn("= CATDOG", self.printed)
        self.assertIn("take O", self.printed)

    def test_a_disagreement_between_banks_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            second = _write(
                space.root / "names.json",
                {"themes": {}, "entries": [{"answer": "CAT", "clue": "Pet"}]},
            )
            code = decorative_crossword.main(self.argv(space, second))
        self.assertEqual(code, 2)
        self.assertIn(str(space.bank), self.errors)
        self.assertIn(str(second), self.errors)

    def test_the_same_bank_given_twice_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            code = decorative_crossword.main(self.argv(space, space.bank))
        self.assertEqual(code, 2)
        self.assertIn("twice", self.errors)
        self.assertEqual(self.printed, "")

    def test_out_naming_either_bank_is_refused(self) -> None:
        # Both banks, for the reason `fill`'s case gives.
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            second = _write(
                space.root / "names.json",
                {"themes": {}, "entries": [{"answer": "AGO"}]},
            )
            for target in (space.bank, second):
                with self.subTest(bank=target.name):
                    before = target.read_bytes()
                    code = decorative_crossword.main(
                        self.argv(space, second, "--out", str(target))
                    )
                    self.assertEqual(target.read_bytes(), before)
                    self.assertEqual(code, 2)
                    self.assertIn(f"names the --bank file {target}", self.errors)


if __name__ == "__main__":
    unittest.main()
