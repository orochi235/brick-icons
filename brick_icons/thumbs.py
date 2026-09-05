"""Thumbnails for the corpus wall: per-part rasters and the sheets holding them.

A cell's index is its position in part-id order over every part, so a render
landing later writes one cell rather than renumbering the sheet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

SHEET_LEVELS = (8, 32)
LOOSE_LEVEL = 128
# The mip chain stops at the coarsest level, so it cannot bleed and needs no
# padding. Every finer sheet does.
GUTTER = 2


@dataclass(frozen=True)
class Geometry:
    count: int
    level: int
    cols: int
    rows: int
    gutter: int

    @property
    def pitch(self) -> int:
        return self.level + 2 * self.gutter

    @property
    def size(self) -> int:
        return self.cols * self.pitch

    def cell_box(self, index: int) -> tuple[int, int, int, int]:
        """The cell's pixel box on the sheet, gutters excluded."""
        if not 0 <= index < self.cols * self.rows:
            raise IndexError(f"cell {index} is outside a {self.cols}x{self.rows} grid")
        col, row = index % self.cols, index // self.cols
        x = col * self.pitch + self.gutter
        y = row * self.pitch + self.gutter
        return (x, y, x + self.level, y + self.level)


def geometry(count: int, level: int) -> Geometry:
    cols = max(1, math.ceil(math.sqrt(count)))
    rows = max(1, math.ceil(count / cols))
    gutter = 0 if level == min(SHEET_LEVELS) else GUTTER
    return Geometry(count=count, level=level, cols=cols, rows=rows, gutter=gutter)
