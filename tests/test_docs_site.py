"""Structural sanity checks for the static project website (docs/index.html).

Not a full browser test - Playwright was used manually during development
to catch real rendering/CSS-specificity bugs (see CHANGELOG), but isn't
added as a project dependency just for a single static page. These checks
instead catch the class of mistake that's easy to introduce when
hand-editing paired EN/FR content blocks: unbalanced tags, duplicate ids,
a French block added without its English twin (or vice versa), and dead
internal links.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar

import pytest

SITE_PATH = Path(__file__).resolve().parent.parent / "docs" / "index.html"


class _SiteParser(HTMLParser):
    """Tracks open/close tag balance, every `id` seen, and how many
    elements are tagged for each language."""

    VOID_ELEMENTS: ClassVar[set[str]] = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.ids: list[str] = []
        self.data_lang_counts: dict[str, int] = {"en": 0, "fr": 0}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        id_value = attrs_dict.get("id")
        if id_value:
            self.ids.append(id_value)
        lang_value = attrs_dict.get("data-lang")
        if lang_value in ("en", "fr"):
            self.data_lang_counts[lang_value] += 1
        if tag not in self.VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        id_value = attrs_dict.get("id")
        if id_value:
            self.ids.append(id_value)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.VOID_ELEMENTS:
            return
        # Deliberately strict, unlike a browser's tolerant error recovery:
        # any mismatch is recorded rather than papered over by popping
        # back to the nearest matching tag, since that kind of recovery
        # can mask exactly the "forgot a closing tag" mistake this check
        # exists to catch (a later, unrelated closing tag ends up being
        # treated as the fix, and the stack balances out by accident).
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            top = self.stack[-1] if self.stack else "<empty>"
            self.errors.append(f"</{tag}> found, but top of stack was <{top}>")


@pytest.fixture(scope="module")
def parsed_site() -> _SiteParser:
    parser = _SiteParser()
    parser.feed(SITE_PATH.read_text(encoding="utf-8"))
    return parser


@pytest.fixture(scope="module")
def site_html() -> str:
    return SITE_PATH.read_text(encoding="utf-8")


def test_site_file_exists() -> None:
    assert SITE_PATH.is_file()


def test_tags_are_balanced(parsed_site: _SiteParser) -> None:
    assert not parsed_site.errors, f"Mismatched closing tag(s): {parsed_site.errors}"
    assert parsed_site.stack == [], f"Unclosed tag(s) at end of document: {parsed_site.stack}"


def test_no_duplicate_ids(parsed_site: _SiteParser) -> None:
    dupes = {i for i in parsed_site.ids if parsed_site.ids.count(i) > 1}
    assert not dupes, f"Duplicate id attribute(s): {dupes}"


def test_english_and_french_content_blocks_match_in_count(parsed_site: _SiteParser) -> None:
    # Not every element needs an EN/FR twin (a handful of identical proper
    # nouns like "GitHub" or "Poetry" are left unwrapped/shared), but the
    # two counts should match exactly - a gap almost always means a block
    # was edited in one language and the other was forgotten.
    en, fr = parsed_site.data_lang_counts["en"], parsed_site.data_lang_counts["fr"]
    assert en == fr, f"EN/FR content block count mismatch: {en} vs {fr}"


def test_internal_anchor_links_resolve(parsed_site: _SiteParser, site_html: str) -> None:
    anchors = set(re.findall(r'href="#([^"]+)"', site_html))
    ids = set(parsed_site.ids)
    missing = anchors - ids
    assert not missing, f'href="#..." target(s) with no matching id: {missing}'


def test_no_leftover_placeholder_text(site_html: str) -> None:
    lowered = site_html.lower()
    for marker in ("todo", "fixme", "replace_with", "lorem ipsum"):
        assert marker not in lowered, f"Found leftover placeholder marker: {marker!r}"


def test_repo_links_point_to_the_same_repository(site_html: str) -> None:
    # All GitHub links should agree on the same owner/repo path - a typo'd
    # link here is easy to miss visually since it still "looks right".
    repos = set(re.findall(r'href="https://github\.com/([^/"]+/[^/"]+?)(?:/blob/|")', site_html))
    assert len(repos) == 1, f"Inconsistent repo paths referenced: {repos}"
