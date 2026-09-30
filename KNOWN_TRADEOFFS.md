# Known trade-offs in `decorative_crossword`

Things that were seen, judged, and **deliberately left in place**. Each was a real observation;
each was carried rather than fixed, for the reason given.

**This file exists to answer one question: is this a bug, or a decision?** Everything below is a
decision. If you are about to "fix" one of these, read its reason first — the reasoning was done
once, with the code in front of it, and is cheaper to read than to redo.

| Subject | Carried because |
| --- | --- |
| `tests/test_properties.py`, its Hypothesis profile | `max_examples` is left at Hypothesis's default rather than raised — a tuning preference, and `derandomize=True` already makes the run reproducible. |
| `src/cw_bank.py`, `parse_bank` | `MappingProxyType` blocks `json.dumps`/`pickle`/`deepcopy` of a `Bank`. Nothing in the tree does any of them (the child-process test converts explicitly), and it fails loudly and locally on first use. |
| `tests/test_config.py`, `test_defaults_alone_form_a_valid_configuration` | Test-name overclaim; the docstring beside it already scopes the claim correctly. |
| `src/cw_config.py`, `_validate_blocked_bounds` | The literal `0` twice: 0 is the mathematical floor of a percentage, not a tunable, so the drift risk is not symmetric with `100`'s. |
| `src/cw_config.py`, module docstring | The "why the omitted clauses are omitted" prose is durable *why*, so it stays. |
| `src/cw_place.py`, `_STEPS` | A public `cw_grid.step_for(direction)` is a design change with its own surface and tests; the current derivation is correct and its comment explains itself. |
| `src/cw_search.py`, `_judge_and_walk` | `>` vs `>=` on a tied best-effort rank; deterministic either way and no committed artifact pins an exit-1 grid. |
| `src/cw_accept.py`, `_theme_reach_reason` | `theme(s)` / `answer(s)` is the project's consistent convention — the SVG caption uses the same form (`0 theme(s) x 1 entry(s)`), pinned by a test. Changing one and not the other would be worse. |
| `tests/test_search.py`, `test_seeds_at_the_centered_position` | Tautological on the arithmetic axis but still pins that the search *uses* `_centered_start`; the real values are pinned by `test_seeds_on_an_even_grid`. |
| `src/cw_emit.py`, `_write_via_temp_file` | `os.fdopen` failure leaking the staging descriptor — unreachable for a fixed `"utf-8"` encoding, and the path is unlinked either way. |
| `src/cw_emit.py`, `_write_via_temp_file` | A `PermissionError` from the `finally`'s unlink would replace the cause; both are `OSError`, so the caller still sees `EmitError`. |
| `src/cw_commands.py`, `_caption_settings` | Same pluralization convention as `_theme_reach_reason`'s. |
| `tests/test_svg_visibility.py`, `TestColorVisibility` | The swatch's stroke has no visibility check of its own. Both strokes come from one shared local, `stroke` in `cw_svg_style.stylesheet`, the swatch keeps its tint fill, and — decisively — the class docstring's enumeration honestly does *not* claim it. An honest enumeration with a known gap is not a false universal. |
| `src/cw_command_base.py`, `REFUSALS` | True of every anticipated fault; the propagation of an *unanticipated* exception is deliberate design, pinned in place elsewhere. |
| `property_strategies/property_strategies.py`, `DUPLICATE_RUN_REQUEST` | "the test's own source text" is imprecise rather than wrong, and its operative claim is measured-true. Weigh it against the same file's deliberate refusal to state an unmeasured mechanism. |
