"""What a part is, in words the wall can badge it with.

One derivation, read by the cell list and the part detail alike. Every tag
comes from something already recorded -- the library's category, the part's
description, the LDraw flags, the id's own shape, or the years, set count and
successor `scripts/fetch-part-years.py` derives -- so a tag is never a
judgment anyone has to keep up to date.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

#: Tags in the order they read best on a badge row: which system a part
#: belongs to, then what is true of the drawing, then what became of it.
TAGS = ("sticker", "minifig", "technic", "duplo", "weird",
        "electric", "magnet", "printed", "composite",
        "obsolete", "retired", "updated", "popular", "obscure")

#: A category maps to a tag of its own name once its LDraw marker is stripped.
_CATEGORY_TAGS = {"sticker": "sticker", "minifig": "minifig",
                  "technic": "technic", "duplo": "duplo",
                  "electric": "electric", "magnet": "magnet"}

#: Themes that were never mainline, matched against the description rather
#: than the category: most of them have no LDraw category at all -- 363
#: Fabuland parts are filed under `Figure` and elsewhere, and naming the
#: category caught 117 of the 584 parts that qualify.
WEIRD_THEMES = frozenset({
    "fabuland", "modulex", "znap", "scala", "belville", "mursten",
    "homemaker", "quatro", "primo", "galidor"})

#: Only the first two words of a description, because a theme name deeper in
#: one is describing a picture: "Tile 1 x 1 with Rainbow and Cloud Pattern" is
#: not a Cloud part. `Figure Fabuland Neck` is why it is two and not one.
_LEAD_WORDS = 2

#: An assembly rather than a single moulding -- `3815c01`. The same shape
#: `lab/cells.py` uses for `base`: a `c` and two characters, at the end.
_COMPOSITE = re.compile(r"c[0-9a-z]{2}$")

#: Appearing in this many sets or fewer is obscure; in this many or more is
#: popular. Between them a part is neither, which is most of them.
OBSCURE_SETS = 2
POPULAR_SETS = 250

#: How long after its last set a part counts as retired. One year of slack:
#: the dumps carry sets a year or two ahead of release, so "last seen last
#: year" is a part still in production, not a retired one.
RETIRED_AFTER_YEARS = 2


def normalize_category(category: str | None) -> str:
    """A category without its LDraw marker: `~Technic` and `=Technic` are both
    Technic -- the prefix says the part is moved or aliased, not what it is."""
    if not category:
        return ""
    return category.lstrip("~=_|").strip().lower()


def is_weird(title: str | None) -> bool:
    """Whether a description opens by naming a sideline theme."""
    if not title:
        return False
    return bool(WEIRD_THEMES.intersection(
        title.lstrip("~=_|").lower().split()[:_LEAD_WORDS]))


def is_composite(part_id: str | None) -> bool:
    return bool(part_id) and _COMPOSITE.search(part_id) is not None


def tags_for(category: str | None, printed: bool, obsolete: bool,
             year_to: int | None = None, sets: int | None = None,
             this_year: int | None = None, *,
             title: str | None = None, part_id: str | None = None,
             successor: str | None = None) -> list[str]:
    """Every tag that applies, in `TAGS` order.

    `year_to` and `sets` are None for a part Rebrickable does not catalog --
    most of the library, once primitives, subparts and unofficial parts are
    counted. That is missing data, not evidence of rarity, so it earns no tag.

    `retired` and `updated` are exclusive: a part that stopped and a part that
    was replaced share a badge slot on the wall, and 2780 is the second.
    """
    if this_year is None:
        this_year = datetime.now(timezone.utc).year
    plain = normalize_category(category)
    out = set()
    if plain in _CATEGORY_TAGS:
        out.add(_CATEGORY_TAGS[plain])
    if printed:
        out.add("printed")
    if obsolete:
        out.add("obsolete")
    if is_weird(title):
        out.add("weird")
    if is_composite(part_id):
        out.add("composite")
    if year_to is not None and year_to <= this_year - RETIRED_AFTER_YEARS:
        out.add("updated" if successor else "retired")
    if sets is not None:
        if sets >= POPULAR_SETS:
            out.add("popular")
        elif sets <= OBSCURE_SETS:
            out.add("obscure")
    return [t for t in TAGS if t in out]
