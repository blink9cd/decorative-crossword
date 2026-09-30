"""Tests that the render fetches NOTHING: the self-contained half of the contract.

Kept apart from `test_svg.py` along a conceptual boundary: that file asks
whether the document has the right parts, this one asks whether the document
reaches outside itself.

The shape of these assertions matters more than their content. A BLACKLIST of
forbidden mechanisms only ever covers the ones somebody thought of: `srcset=`
slips past a `src=` check, `<img` past an `<image` one, and a relative
`SYSTEM` identifier past every URL check there is. A WHITELIST of what the
document may contain closes all of those at once, including the mechanisms
nobody has thought of yet.

A whitelist has exactly two blind spots, and both are closed here rather than
left implicit:

* it is only as broad as the documents it runs over -- an `<image>` injected
  into the EMPTY-LAYER branch survives a whitelist proved against one richly
  populated fixture, because that fixture emits no empty layer. Every
  assertion below therefore runs over several genuinely different documents;
* ElementTree's default parser DISCARDS comments and processing instructions,
  so no assertion on the parsed tree can see either. An in-root
  `<?xml-stylesheet href="branding.css"?>` is precisely the `href=` mechanism
  a blacklist named, and it carries no scheme and no `//`. One string-level
  check on the body closes both.
"""

import unittest

import cw_svg
from tests import svg_fixtures as fixtures

#: Everything this render is allowed to draw with.
_ALLOWED_ELEMENTS = frozenset(
    {"svg", "style", "g", "rect", "text", "circle", "polygon"}
)

#: Every attribute it is allowed to carry. The namespace declaration is not in
#: this set because the parser consumes it rather than reporting it as an
#: attribute; it is pinned separately by test_svg.py's namespace test, so its
#: absence here is not an omission.
_ALLOWED_ATTRIBUTES = frozenset(
    {"class", "cx", "cy", "height", "points", "r", "viewBox", "width", "x", "y"}
)

#: The one document that populates every layer, and so is the only one that can
#: pin the whitelists as EQUALITIES rather than subsets.
_RICHEST = "every layer populated"


def _documents() -> dict[str, str]:
    """Several genuinely different rendered documents, keyed by what they are.

    Not one fixture rendered several ways: each entry reaches a code path the
    others do not. "no declared themes" is the one that emits the empty-layer
    branch, and "empty grid" empties the cell and letter layers as well.
    """
    return {
        _RICHEST: cw_svg.render_svg(
            fixtures.wide_request(feature="PEAR", settings={"seed": "7"})
        ),
        "no feature, no settings": cw_svg.render_svg(fixtures.wide_request()),
        "no declared themes": cw_svg.render_svg(
            fixtures.wide_request(themes={}, entry_themes={})
        ),
        "single theme, square grid": cw_svg.render_svg(fixtures.request()),
        "empty grid": cw_svg.render_svg(
            fixtures.request(rows=(), themes={}, entry_themes={})
        ),
        "a theme label full of markup": cw_svg.render_svg(
            fixtures.request(themes={"pets": "Cats & <dogs> & <script>"})
        ),
        # `--empty-blocks` swaps one rule for another, so it reaches a
        # stylesheet no other entry renders. Listed here rather than checked
        # in its own suite so it answers to every containment rule at once,
        # not just the url one it would plausibly have been given.
        "blocked cells drawn empty": cw_svg.render_svg(
            fixtures.wide_request(feature="PEAR", empty_blocks=True)
        ),
    }


def _body(rendered: str) -> str:
    """Everything from the root element onwards."""
    return rendered[rendered.index("<svg") :]


class TestNothingIsFetched(unittest.TestCase):
    """No document this render can produce reaches outside its own file."""

    def test_uses_only_the_elements_it_needs(self) -> None:
        for description, rendered in _documents().items():
            with self.subTest(document=description):
                drawn = {
                    node.tag.rpartition("}")[2]
                    for node in fixtures.parse(rendered).iter()
                }
                self.assertLessEqual(drawn, _ALLOWED_ELEMENTS)

    def test_the_richest_document_draws_every_allowed_element(self) -> None:
        # The subset checks above cannot notice an allowance nothing uses, so a
        # mechanism quietly added to the whitelist would never be questioned.
        # Pinning the fullest document as an equality is what keeps the list
        # honest about what is actually drawn.
        drawn = {
            node.tag.rpartition("}")[2]
            for node in fixtures.parse(_documents()[_RICHEST]).iter()
        }
        self.assertEqual(drawn, set(_ALLOWED_ELEMENTS))

    def test_uses_only_the_attributes_it_needs(self) -> None:
        for description, rendered in _documents().items():
            with self.subTest(document=description):
                carried = {
                    name
                    for node in fixtures.parse(rendered).iter()
                    for name in node.keys()
                }
                self.assertLessEqual(carried, _ALLOWED_ATTRIBUTES)

    def test_the_richest_document_carries_every_allowed_attribute(self) -> None:
        carried = {
            name
            for node in fixtures.parse(_documents()[_RICHEST]).iter()
            for name in node.keys()
        }
        self.assertEqual(carried, set(_ALLOWED_ATTRIBUTES))

    def test_nothing_precedes_the_root_but_the_xml_declaration(self) -> None:
        # The parser drops a doctype, so no assertion on the tree can see one.
        # An external DTD -- `<!DOCTYPE svg SYSTEM "branding.dtd">` -- is a
        # fetch whose relative identifier carries no scheme and no `//`, so the
        # URL check cannot see it either. This is where it is visible.
        for description, rendered in _documents().items():
            with self.subTest(document=description):
                self.assertEqual(
                    rendered[: rendered.index("<svg")].strip(),
                    '<?xml version="1.0" encoding="UTF-8"?>',
                )

    def test_no_instruction_or_comment_appears_inside_the_document(self) -> None:
        # The parser discards processing instructions and comments alike, so
        # both are invisible to the whitelists above and to the prologue check
        # below the root. `<?xml-stylesheet type="text/css" href="branding.css"?>`
        # placed inside the root is a fetch with no scheme, no `//`, and no
        # element or attribute for a whitelist to reject.
        for description, rendered in _documents().items():
            with self.subTest(document=description):
                body = _body(rendered)
                self.assertNotIn("<?", body)
                self.assertNotIn("<!", body)

    def test_the_stylesheet_fetches_nothing(self) -> None:
        # Neither whitelist can reach inside the stylesheet, which is one text
        # node. Every rule this render emits has the shape
        # `selector{property:value}` -- no at-rule and no function call -- and
        # CSS reaches outside the file only through one or the other
        # (`@import`, `@font-face`, `url(...)`). Asserting the SHAPE rather
        # than naming the three keeps it a whitelist.
        for description, rendered in _documents().items():
            with self.subTest(document=description):
                style = fixtures.stylesheet(rendered)
                self.assertIn("sans-serif", style)
                self.assertNotIn("@", style)
                self.assertNotIn("(", style)

    def test_references_no_external_url(self) -> None:
        # Self-contained: it must open from a file:// path on a machine with no
        # network. The SVG namespace URI is an identifier
        # rather than a fetch -- and a document missing it renders blank -- so it
        # is removed before the check instead of being allowed to pass one.
        for description, rendered in _documents().items():
            with self.subTest(document=description):
                without_namespace = rendered.replace(cw_svg.SVG_NAMESPACE, "")
                self.assertNotIn("http://", without_namespace)
                self.assertNotIn("https://", without_namespace)
                self.assertNotIn("//", without_namespace)

    def test_names_only_generic_font_families(self) -> None:
        # A generic family is resolved by the viewer; a named font file is not.
        for description, rendered in _documents().items():
            with self.subTest(document=description):
                self.assertIn("sans-serif", rendered)
                self.assertNotIn(".woff", rendered)
                self.assertNotIn(".ttf", rendered)


if __name__ == "__main__":
    unittest.main()
