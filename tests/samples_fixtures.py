"""Where the samples live, and the names of the samples that read another sample's grid.

Named `*_fixtures.py` rather than `test_*.py` so the aggregator's discovery skips
it and it carries no floor of its own -- like every `*_fixtures.py` module
here. The fill samples' suite checks that every folder under `samples/` is
pinned, and `test_samples_read.py` runs the samples that read another sample's
grid, so both need the folder and those folder names from one place.
"""

from pathlib import Path

#: The committed samples live beside the project root, not beside this file.
SAMPLES = Path(__file__).resolve().parent.parent / "samples"

#: The `shade` sample, rather than a `fill` one: it holds a word
#: list and a render, and reads the grid `large_square` already produced. It
#: does not carry a grid of its own on purpose -- the demonstration is the
#: whole chain, fill then shade, and a second copy of that grid would be a
#: second thing to keep in step with the tool.
SHADE_SAMPLE = "hidden_word"

#: The `gaps` sample: it reads the same grid `large_square`
#: produced, against that grid's own bank, and holds only the render -- the
#: report is stdout, so what it must still say is pinned by the suite that runs it.
GAPS_SAMPLE = "gaps"

#: The `preview --empty-blocks` sample: it reads the same grid `large_square`
#: produced and holds only the render. A read sample rather than a `fill` one
#: deliberately -- the flag changes the DRAWING and not the search, so running
#: a search to show it would demonstrate the wrong half, and a fill sample
#: would also owe `test_samples.py` a grid shape and a density no other
#: sample has.
SILHOUETTE_SAMPLE = "silhouette"
