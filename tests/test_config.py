"""Tests for cw_config: every configuration rejection names its own option."""

import unittest
from typing import cast

import cw_config
import cw_grid
import cw_symmetry

# The optional FillConfig fields DEFAULTS covers, read once here so _config()'s
# keyword defaults come from cw_config.DEFAULTS rather than re-spelling a number: a
# fixture holding its own copy of "30.0" cannot notice DEFAULTS changing underneath
# it. TestDefaultsAreValid below separately pins that those values pass validation.
_DEFAULT_MIN_BLOCKED = cast(float, cw_config.DEFAULTS["min_blocked"])
_DEFAULT_MAX_BLOCKED = cast(float, cw_config.DEFAULTS["max_blocked"])
_DEFAULT_MIN_THEMES = cast(int, cw_config.DEFAULTS["min_themes"])
_DEFAULT_MIN_ENTRIES_PER_THEME = cast(int, cw_config.DEFAULTS["min_entries_per_theme"])
_DEFAULT_TIME_BUDGET = cast(float, cw_config.DEFAULTS["time_budget"])
_DEFAULT_MAX_STEPS = cast(int, cw_config.DEFAULTS["max_steps"])
_DEFAULT_LOOK_AHEAD = cast(int, cw_config.DEFAULTS["look_ahead"])


def _config(
    *,
    rows: int = 9,
    cols: int = 9,
    seed: int = 7,
    min_blocked: float = _DEFAULT_MIN_BLOCKED,
    max_blocked: float = _DEFAULT_MAX_BLOCKED,
    min_themes: int = _DEFAULT_MIN_THEMES,
    min_entries_per_theme: int = _DEFAULT_MIN_ENTRIES_PER_THEME,
    time_budget: float = _DEFAULT_TIME_BUDGET,
    max_steps: int = _DEFAULT_MAX_STEPS,
    look_ahead: int = _DEFAULT_LOOK_AHEAD,
    prefer: tuple[str, ...] = (),
    max_two_letter: int | None = None,
    prefer_symmetry: str | None = None,
    masked: frozenset[tuple[int, int]] = frozenset(),
    mask_size: tuple[int, int] = (0, 0),
    start: tuple[str, ...] = (),
    source_size: tuple[int, int] = (0, 0),
) -> cw_config.FillConfig:
    """A valid config with the named fields overridden by keyword.

    Explicit typed keyword parameters rather than `**overrides: object`,
    which would need a blanket `# type: ignore[arg-type]` to unpack into
    `FillConfig`'s typed fields and would type-check a call like
    `_config(rows="nine")` as fine.
    """
    return cw_config.FillConfig(
        rows=rows,
        cols=cols,
        seed=seed,
        min_blocked=min_blocked,
        max_blocked=max_blocked,
        min_themes=min_themes,
        min_entries_per_theme=min_entries_per_theme,
        time_budget=time_budget,
        max_steps=max_steps,
        features=(),
        look_ahead=look_ahead,
        prefer=prefer,
        island_letters=(),
        max_two_letter=max_two_letter,
        prefer_symmetry=prefer_symmetry,
        masked=masked,
        mask_size=mask_size,
        start=start,
        source_size=source_size,
    )


class TestValidateFillConfig(unittest.TestCase):
    """A contradictory configuration is refused before any search starts."""

    def test_accepts_a_valid_config(self) -> None:
        # validate_fill_config is declared -> None, so assertIsNone on its
        # result would assert nothing the type system doesn't already
        # guarantee; the real claim is "does not raise".
        cw_config.validate_fill_config(_config())

    def test_rejects_min_above_max_blocked(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(min_blocked=50.0, max_blocked=40.0))
        self.assertIn("--min-blocked", str(caught.exception))

    def test_rejects_blocked_above_one_hundred(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(max_blocked=101.0))
        self.assertIn("--max-blocked", str(caught.exception))

    def test_accepts_a_blocked_ceiling_of_exactly_one_hundred(self) -> None:
        # The ceiling is part of the documented scale, 0-100, and the
        # rejection above pins it only from the other side: it uses
        # 101.0, so setting `_MAX_BLOCKED_PERCENT` to 90 leaves the whole suite
        # green while the tool starts refusing a documented input. This is the
        # case that fails when the constant moves down.
        cw_config.validate_fill_config(_config(max_blocked=100.0))

    def test_rejects_negative_blocked(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(min_blocked=-1.0))
        self.assertIn("--min-blocked", str(caught.exception))

    def test_rejects_non_positive_rows(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(rows=0))
        self.assertIn("--rows", str(caught.exception))

    def test_rejects_non_positive_cols(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(cols=-3))
        self.assertIn("--cols", str(caught.exception))

    def test_rejects_negative_time_budget(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(time_budget=-0.5))
        self.assertIn("--time-budget", str(caught.exception))

    def test_rejects_negative_max_steps(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(max_steps=-1))
        self.assertIn("--max-steps", str(caught.exception))

    def test_rejects_both_budgets_unlimited(self) -> None:
        # Zero reads as "no limit" on BOTH budgets, which makes their
        # combination the one request that has nothing at all to stop it.
        # Refused here, loudly and before any searching, rather than left to
        # look like a hang -- the whole point of giving `--time-budget` a zero
        # is a run bounded by something DETERMINISTIC, so the node cap has to
        # be present for the clock to be dropped.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(time_budget=0.0, max_steps=0))
        message = str(caught.exception)
        self.assertIn("--time-budget", message)
        self.assertIn("--max-steps", message)

    def test_rejects_negative_min_themes(self) -> None:
        # One test per floor, each asserting its own flag, so a copy-paste that
        # made this branch's message say "--min-entries-per-theme" would be
        # caught rather than hidden behind a second, still-passing assertion.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(min_themes=-1))
        self.assertIn("--min-themes", str(caught.exception))

    def test_accepts_a_min_themes_of_zero(self) -> None:
        # A bank whose `themes` map is empty is legal, so the floor has to
        # have an off position: every positive floor is one such
        # a bank can never reach. Paired with the rejection above so that the
        # boundary is pinned from both sides: a `<= 0` cut fails this test,
        # and a relaxation to `< -1` fails the one above.
        cw_config.validate_fill_config(_config(min_themes=0))

    def test_rejects_non_positive_min_entries_per_theme(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(min_entries_per_theme=0))
        self.assertIn("--min-entries-per-theme", str(caught.exception))

    def test_rejects_a_negative_look_ahead(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(look_ahead=-1))
        self.assertIn("--look-ahead", str(caught.exception))

    def test_accepts_a_look_ahead_of_zero(self) -> None:
        # Zero keeps the first conforming grid, so it has to stay a legal
        # request, and the boundary is pinned from this side as well as from
        # the refusal above.
        cw_config.validate_fill_config(_config(look_ahead=0))

    def test_rejects_a_negative_two_letter_cap(self) -> None:
        with self.assertRaisesRegex(cw_config.ConfigError, "--max-two-letter"):
            cw_config.validate_fill_config(_config(max_two_letter=-1))

    def test_accepts_a_two_letter_cap_of_zero(self) -> None:
        # Zero is a real cap, not "no cap": a consumer that allows no two-letter
        # entry on a wide grid needs exactly that request, so a positive-only rule
        # would refuse it. The claim is "does not raise", as
        # `test_accepts_a_valid_config` states.
        cw_config.validate_fill_config(_config(max_two_letter=0))

    def test_rejects_an_answer_preferred_twice(self) -> None:
        # A repeat would count one answer twice when grids are compared, which
        # is a preference the operator did not state.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(prefer=("CAT", "CAT")))
        message = str(caught.exception)
        self.assertIn("--prefer", message)
        self.assertIn("'CAT'", message)
        self.assertIn("twice", message)

    def test_accepts_every_symmetry_kind(self) -> None:
        # The claim is "does not raise", as `test_accepts_a_valid_config` states.
        for kind in cw_symmetry.KINDS:
            with self.subTest(kind=kind):
                cw_config.validate_fill_config(_config(prefer_symmetry=kind))

    def test_rejects_a_symmetry_kind_it_does_not_know(self) -> None:
        # argparse's choices refuse this at the command line; a config built
        # directly would otherwise reach the search and fail on a lookup there.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(prefer_symmetry="diagonal"))
        message = str(caught.exception)
        self.assertIn("--prefer-symmetry", message)
        self.assertIn("'diagonal'", message)
        self.assertIn("rotational", message)


class TestMaskSize(unittest.TestCase):
    """A `--mask` picture must be exactly the size of the grid it shapes."""

    def test_accepts_a_mask_matching_the_grid(self) -> None:
        cw_config.validate_fill_config(
            _config(rows=4, cols=5, masked=frozenset({(0, 0)}), mask_size=(4, 5))
        )

    def test_accepts_a_mask_that_forbids_nothing(self) -> None:
        # An empty set of cells is a legal picture and still fixes the size, so
        # the check may not read "was anything masked" as "was a mask given".
        cw_config.validate_fill_config(_config(rows=4, cols=5, mask_size=(4, 5)))

    def test_accepts_no_mask_at_all(self) -> None:
        cw_config.validate_fill_config(_config(rows=4, cols=5))

    def test_rejects_a_mask_with_the_wrong_number_of_rows(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(rows=4, cols=5, mask_size=(3, 5)))
        message = str(caught.exception)
        self.assertIn("--mask", message)
        self.assertIn("3x5", message)
        self.assertIn("4x5", message)

    def test_rejects_a_mask_with_the_wrong_number_of_columns(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(_config(rows=4, cols=5, mask_size=(4, 9)))
        message = str(caught.exception)
        self.assertIn("4x9", message)
        self.assertIn("4x5", message)

    def test_the_refusal_names_the_grown_grid_not_the_source(self) -> None:
        # The grid a mask must match is the one a fill ENDS on. A source grown
        # past the picture is the case this catches, and naming the source's
        # size instead would send the operator to the wrong file.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(
                _config(
                    rows=9,
                    cols=9,
                    start=("AB.......", *(("." * 9,) * 8)),
                    source_size=(1, 2),
                    mask_size=(7, 7),
                )
            )
        self.assertIn("9x9", str(caught.exception))


class TestMaskedSourceLetters(unittest.TestCase):
    """A `--source` letter in a masked cell is the operator's contradiction."""

    def test_rejects_a_source_letter_in_a_masked_cell(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(
                _config(
                    rows=2,
                    cols=2,
                    start=("A.", ".."),
                    source_size=(2, 2),
                    masked=frozenset({(0, 0)}),
                    mask_size=(2, 2),
                )
            )
        message = str(caught.exception)
        self.assertIn("--source", message)
        self.assertIn("--mask", message)
        self.assertIn("0,0", message)

    def test_accepts_a_source_whose_letters_avoid_the_mask(self) -> None:
        cw_config.validate_fill_config(
            _config(
                rows=2,
                cols=2,
                start=("A.", ".."),
                source_size=(2, 2),
                masked=frozenset({(1, 1)}),
                mask_size=(2, 2),
            )
        )

    def test_a_mask_of_the_wrong_size_is_named_before_any_letter(self) -> None:
        # Ordering: on a picture that does not match the grid, a cell of it
        # names nothing the operator can find, so the size is reported first.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_fill_config(
                _config(
                    rows=2,
                    cols=2,
                    start=("A.", ".."),
                    source_size=(2, 2),
                    masked=frozenset({(0, 0)}),
                    mask_size=(3, 3),
                )
            )
        self.assertIn("3x3", str(caught.exception))


class TestDefaults(unittest.TestCase):
    """DEFAULTS is the single source the parser and the doc both read."""

    def test_carries_every_optional_option_of_every_subcommand(self) -> None:
        """The whole map, so an option added without a default here is caught.

        `cell`, `min_length` and `top` are options of subcommands other than
        `fill` rather than `FillConfig` fields: DEFAULTS is the single source
        for every subcommand's optionals, not for one struct's fields.
        """
        self.assertEqual(
            sorted(cw_config.DEFAULTS),
            [
                "cell",
                "look_ahead",
                "max_blocked",
                "max_steps",
                "min_blocked",
                "min_entries_per_theme",
                "min_length",
                "min_themes",
                "time_budget",
                "top",
            ],
        )


class TestDefaultsAreValid(unittest.TestCase):
    """DEFAULTS is validated, not merely declared."""

    def test_defaults_alone_form_a_valid_configuration(self) -> None:
        """Every value DEFAULTS supplies must itself satisfy validate_fill_config.

        Built straight from `cw_config.DEFAULTS` rather than through
        `_config()`, so a copy-paste bug in that wiring cannot hide this check
        too.
        """
        config = cw_config.FillConfig(
            rows=9,
            cols=9,
            seed=7,
            min_blocked=cast(float, cw_config.DEFAULTS["min_blocked"]),
            max_blocked=cast(float, cw_config.DEFAULTS["max_blocked"]),
            min_themes=cast(int, cw_config.DEFAULTS["min_themes"]),
            min_entries_per_theme=cast(
                int, cw_config.DEFAULTS["min_entries_per_theme"]
            ),
            time_budget=cast(float, cw_config.DEFAULTS["time_budget"]),
            max_steps=cast(int, cw_config.DEFAULTS["max_steps"]),
            features=(),
            look_ahead=cast(int, cw_config.DEFAULTS["look_ahead"]),
            prefer=(),
            island_letters=(),
        )
        cw_config.validate_fill_config(config)


def _shade_config(
    *,
    min_length: int = cast(int, cw_config.DEFAULTS["min_length"]),
    top: int = cast(int, cw_config.DEFAULTS["top"]),
    exclude_grid_answers: bool = False,
    word: str | None = None,
    cell: int = cast(int, cw_config.DEFAULTS["cell"]),
) -> cw_config.ShadeConfig:
    """A valid `shade` config with the named fields overridden by keyword.

    Its defaults come from `cw_config.DEFAULTS` for the reason `_config`'s do:
    a fixture holding its own copy of a number cannot notice that number
    changing underneath it.
    """
    return cw_config.ShadeConfig(
        min_length=min_length,
        top=top,
        exclude_grid_answers=exclude_grid_answers,
        word=word,
        cell=cell,
    )


class TestValidateShadeConfig(unittest.TestCase):
    """Every `shade` rejection names the option at fault."""

    def test_accepts_the_defaults(self) -> None:
        cw_config.validate_shade_config(_shade_config())

    def test_accepts_a_word_and_the_exclusion_together(self) -> None:
        """Two flags that CONTRADICT are refused by the handler, not by range.

        This validator's job is whether each value is usable on its own, so a
        pairing it has no view on must pass here -- otherwise the handler's own
        refusal, which is the one that can explain itself, becomes unreachable.
        """
        cw_config.validate_shade_config(
            _shade_config(word="NOTEBOOK", exclude_grid_answers=True)
        )

    def test_rejects_a_min_length_below_the_two_letter_floor(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_shade_config(_shade_config(min_length=1))
        self.assertIn("--min-length", str(caught.exception))

    def test_accepts_a_min_length_at_the_floor(self) -> None:
        """Paired with the rejection above so the boundary is pinned both ways."""
        cw_config.validate_shade_config(_shade_config(min_length=cw_grid.MIN_RUN))

    def test_rejects_a_negative_top(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_shade_config(_shade_config(top=-1))
        self.assertIn("--top", str(caught.exception))

    def test_accepts_a_top_of_zero(self) -> None:
        """Zero is 'no limit', the same reading `--max-steps` already has."""
        cw_config.validate_shade_config(_shade_config(top=0))

    def test_rejects_a_word_below_the_two_letter_floor(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_shade_config(_shade_config(word="A"))
        self.assertIn("--word", str(caught.exception))

    def test_rejects_a_word_outside_a_to_z(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_shade_config(_shade_config(word="CAT-NAP"))
        self.assertIn("--word", str(caught.exception))

    def test_rejects_a_non_positive_cell_in_either_mode(self) -> None:
        """One rule, not a mode-dependent one -- see `validate_shade_config`."""
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_shade_config(_shade_config(cell=0))
        self.assertIn("--cell", str(caught.exception))


class TestValidateCell(unittest.TestCase):
    """`preview --cell` is the one knob that can write an unrenderable file."""

    def test_accepts_the_default(self) -> None:
        cw_config.validate_cell(cast(int, cw_config.DEFAULTS["cell"]))

    def test_rejects_a_zero_cell(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_cell(0)
        self.assertIn("--cell", str(caught.exception))

    def test_rejects_a_negative_cell(self) -> None:
        with self.assertRaises(cw_config.ConfigError):
            cw_config.validate_cell(-5)

    def test_accepts_the_largest_cell(self) -> None:
        cw_config.validate_cell(cw_config.MAX_CELL)

    def test_rejects_a_cell_past_the_largest_naming_the_ceiling(self) -> None:
        past = cw_config.MAX_CELL + 1
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_cell(past)
        self.assertEqual(
            str(caught.exception),
            f"--cell must be at most {cw_config.MAX_CELL}, got {past}",
        )


def _gaps_config(**overrides: object) -> cw_config.GapsConfig:
    """A valid `gaps` configuration, with named fields overridden per case."""
    fields: dict[str, object] = {
        "top": cast(int, cw_config.DEFAULTS["top"]),
        "include_absorbing": False,
        "cell": cast(int, cw_config.DEFAULTS["cell"]),
    }
    fields.update(overrides)
    return cw_config.GapsConfig(**fields)  # type: ignore[arg-type]


class TestValidateGapsConfig(unittest.TestCase):
    """`gaps` has two numeric knobs, and each refusal names its own flag."""

    def test_accepts_the_defaults(self) -> None:
        cw_config.validate_gaps_config(_gaps_config())

    def test_accepts_a_zero_top_as_no_limit(self) -> None:
        """Zero reads as "no limit", the same as `--max-steps` and shade's `--top`."""
        cw_config.validate_gaps_config(_gaps_config(top=0))

    def test_rejects_a_negative_top(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_gaps_config(_gaps_config(top=-1))
        self.assertIn("--top", str(caught.exception))

    def test_rejects_a_non_positive_cell(self) -> None:
        """`--cell` is checked whether or not this run gives `--out`, as in shade."""
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_config.validate_gaps_config(_gaps_config(cell=0))
        self.assertIn("--cell", str(caught.exception))
