"""What a part is, in words the wall can badge it with.

One derivation, read by the cell list and the part detail alike. Every tag
comes from something already recorded -- the library's category, the LDraw
flags, or the years and set count `scripts/fetch-part-years.py` derives -- so
a tag is never a judgment anyone has to keep up to date.
"""
from __future__ import annotations

from datetime import datetime, timezone

#: Tags in the order they read best on a badge row.
TAGS = ("sticker", "minifig", "technic", "duplo", "printed", "obsolete",
        "retired", "popular", "obscure")

#: A category maps to a tag of its own name once its LDraw marker is stripped.
_CATEGORY_TAGS = {"sticker": "sticker", "minifig": "minifig",
                  "technic": "technic", "duplo": "duplo"}

#: Themes that were never mainline. A part from one of these is obscure
#: whatever its set count says -- 40 Modulex sets is not 40 LEGO sets.
OBSCURE_CATEGORIES = frozenset({
    "fabuland", "modulex", "znap", "scala", "belville", "mursten",
    "homemaker", "quatro", "primo", "galidor", "cloud"})

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


def tags_for(category: str | None, printed: bool, obsolete: bool,
             year_to: int | None = None, sets: int | None = None,
             this_year: int | None = None) -> list[str]:
    """Every tag that applies, in `TAGS` order.

    `year_to` and `sets` are None for a part Rebrickable does not catalog --
    most of the library, once primitives, subparts and unofficial parts are
    counted. That is missing data, not evidence of rarity, so it earns no tag.
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
    if plain in OBSCURE_CATEGORIES:
        out.add("obscure")
    if year_to is not None and year_to <= this_year - RETIRED_AFTER_YEARS:
        out.add("retired")
    if sets is not None:
        if sets >= POPULAR_SETS:
            out.add("popular")
        elif sets <= OBSCURE_SETS:
            out.add("obscure")
    return [t for t in TAGS if t in out]
