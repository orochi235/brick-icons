# LDraw Color Codes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `--part-color` take an LDraw color code (`4`) or name (`light_bluish_grey`) instead of only `0xRRGGBB`, resolved against the vendored `LDConfig.ldr`, with a translucent color's `ALPHA` supplying `--opacity` when the user did not set it.

**Architecture:** A new `brick_icons/colors.py` is the only module that knows LDConfig exists. It parses `!COLOUR` lines into a palette and exposes one entry point, `resolve()`, which maps any color spec to a canonical `0xRRGGBB` string plus an optional alpha. `load_config` calls it once and writes the canonical hex back into `part_color`, so both downstream consumers — the LDView `-DefaultColor3=` flag in `render.py:49` and `shade.parse_hex_color` at `cli.py:125` — receive exactly what they receive today. No other module changes.

**Tech Stack:** Python 3.11+, numpy, pytest, shapely. Spec: `docs/superpowers/specs/2026-08-28-printed-parts-design.md`.

**Commands:** run tests with `.venv/bin/python -m pytest -q` (single test with `-k`). Render specimens with `.venv/bin/brick-icons --list specimens.txt --root . --format svg --shading outline --shade-style flat3 --out <dir>`.

**Scope:** This plan is phase 1 of the spec plus two adjacent items — the `_ink_lens_pockets` crash, and the measurement that unblocks phase 2. Phase 2 (decal unwrap) gets its own plan once Task 9 produces real carrier-offset numbers; its central tolerance cannot be chosen honestly before then.

**Ground rules:**
- The hex path must stay bit-for-bit unchanged. `parse_hex_color` keeps its silent gray fallback for malformed hex; only codes and names raise. Task 7 proves this with a byte-diff gate.
- Names in LDConfig are British (`Light_Bluish_Grey`). Lookup folds `gray`≡`grey`, case, and `_`/`-`/space, so both spellings work.
- Do not reformat or re-sort `vendor/ldraw/LDConfig.ldr`. It is vendored upstream data.

---

### Task 1: Baseline — green suite and a specimen snapshot

**Files:** none created in-repo (baseline goes to gitignored `debug/`).

- [ ] **Step 1: Confirm the suite is green before touching anything**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (336 at time of writing). If not, STOP and report — the safety net must be intact first.

- [ ] **Step 2: Render the specimen baseline**

```bash
mkdir -p debug/colorcodes
.venv/bin/brick-icons --list specimens.txt --root . --format svg --shading outline --shade-style flat3 --out debug/colorcodes/baseline
```

Expected: one `.svg` per specimen id in `debug/colorcodes/baseline/`.

- [ ] **Step 3: Verify the renderer is deterministic**

```bash
.venv/bin/brick-icons --list specimens.txt --root . --format svg --shading outline --shade-style flat3 --out debug/colorcodes/baseline2
cd debug/colorcodes
find baseline  -name '*.svg' -exec shasum -a 256 {} + | sed 's/baseline\///'  | sort > baseline.sha
find baseline2 -name '*.svg' -exec shasum -a 256 {} + | sed 's/baseline2\///' | sort > baseline2.sha
diff baseline.sha baseline2.sha && echo DETERMINISTIC
cd ../..
```

Expected: `DETERMINISTIC`. If the hashes differ, STOP — the byte-diff gate in Task 7 is worthless without it.

---

### Task 2: Parse LDConfig into Color records

**Files:**
- Create: `brick_icons/colors.py`
- Test: `tests/test_colors.py`

- [ ] **Step 1: Write the failing test**

```python
from brick_icons.colors import Color, parse_ldconfig

LDCFG = """\
0 LDraw.org Configuration File
0 // Color definitions
0 !COLOUR Black          CODE     0   VALUE #1B2A34   EDGE #808080
0                              // LEGOID  26 - Black
0 !COLOUR Red            CODE     4   VALUE #B40000   EDGE #333333
0 !COLOUR Light_Bluish_Grey CODE 71   VALUE #969696   EDGE #333333
0 !COLOUR Trans_Red      CODE    36   VALUE #C91A09   EDGE #660D05   ALPHA 128
"""


def test_parse_ldconfig_reads_code_name_value():
    cs = {c.code: c for c in parse_ldconfig(LDCFG.splitlines())}
    assert set(cs) == {0, 4, 71, 36}
    assert cs[4] == Color(code=4, name="Red", rgb=(0xB4, 0x00, 0x00), alpha=255)
    assert cs[71].name == "Light_Bluish_Grey"
    assert cs[71].rgb == (0x96, 0x96, 0x96)


def test_parse_ldconfig_reads_alpha():
    cs = {c.code: c for c in parse_ldconfig(LDCFG.splitlines())}
    assert cs[36].alpha == 128
    assert cs[36].opacity == 128 / 255
    assert cs[0].alpha == 255 and cs[0].opacity == 1.0


def test_color_hex_is_canonical_lowercase():
    assert Color(code=4, name="Red", rgb=(0xB4, 0, 0)).hex == "0xb40000"


def test_parse_ldconfig_ignores_comments_and_legoid_lines():
    assert len(parse_ldconfig(["0 // not a color", "0 // LEGOID 26 - Black"])) == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_colors.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'brick_icons.colors'`

- [ ] **Step 3: Write the minimal implementation**

Create `brick_icons/colors.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_COLOUR = re.compile(
    r"^0\s+!COLOUR\s+(?P<name>\S+)\s+CODE\s+(?P<code>\d+)\s+"
    r"VALUE\s+#(?P<value>[0-9A-Fa-f]{6})",
    re.IGNORECASE)
_ALPHA = re.compile(r"\bALPHA\s+(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class Color:
    code: int
    name: str
    rgb: tuple
    alpha: int = 255

    @property
    def hex(self) -> str:
        return "0x%02x%02x%02x" % tuple(self.rgb)

    @property
    def opacity(self) -> float:
        return self.alpha / 255.0


def parse_ldconfig(lines) -> list[Color]:
    """Every '0 !COLOUR ... CODE n VALUE #rrggbb [... ALPHA a]' line."""
    out = []
    for ln in lines:
        m = _COLOUR.match(ln)
        if not m:
            continue
        v = int(m.group("value"), 16)
        a = _ALPHA.search(ln[m.end():])
        out.append(Color(code=int(m.group("code")), name=m.group("name"),
                         rgb=((v >> 16) & 255, (v >> 8) & 255, v & 255),
                         alpha=int(a.group(1)) if a else 255))
    return out
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_colors.py -q`
Expected: 4 passed

- [ ] **Step 5: Verify it reads the real vendored file**

Run:
```bash
.venv/bin/python -c "
from brick_icons.colors import parse_ldconfig
cs = parse_ldconfig(open('vendor/ldraw/LDConfig.ldr', errors='replace'))
print(len(cs), 'colors')
d = {c.code: c for c in cs}
print(d[4].name, d[4].hex, '|', d[71].name, d[71].hex, '|', d[36].name, d[36].alpha)
"
```
Expected: `322 colors` then `Red 0xb40000 | Light_Bluish_Grey 0x969696 | Trans_Red 128`

- [ ] **Step 6: Commit**

```bash
git add brick_icons/colors.py tests/test_colors.py
git commit -m "parse LDConfig color definitions into Color records"
```

---

### Task 3: Palette lookup by code and by normalized name

**Files:**
- Modify: `brick_icons/colors.py`
- Test: `tests/test_colors.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_colors.py`:

```python
from brick_icons.colors import load_palette, normalize_name


def test_normalize_name_folds_case_separators_and_gray():
    assert normalize_name("Light_Bluish_Grey") == "lightbluishgrey"
    assert normalize_name("light-bluish-gray") == "lightbluishgrey"
    assert normalize_name("Light Bluish Gray") == "lightbluishgrey"
    assert normalize_name("RED") == "red"


def test_load_palette_indexes_both_ways(tmp_path):
    (tmp_path / "LDConfig.ldr").write_text(LDCFG)
    pal = load_palette(tmp_path)
    assert pal.by_code[4].name == "Red"
    assert pal.by_name["red"].code == 4
    assert pal.by_name["lightbluishgrey"].code == 71
    assert pal.by_name["lightbluishgray"].code == 71   # American spelling


def test_load_palette_is_cached(tmp_path):
    (tmp_path / "LDConfig.ldr").write_text(LDCFG)
    assert load_palette(tmp_path) is load_palette(tmp_path)


def test_load_palette_missing_file_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_palette(tmp_path / "nope")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_colors.py -q`
Expected: FAIL with `ImportError: cannot import name 'load_palette'`

- [ ] **Step 3: Write the minimal implementation**

Append to `brick_icons/colors.py`:

```python
@dataclass(frozen=True)
class Palette:
    by_code: dict = field(default_factory=dict)
    by_name: dict = field(default_factory=dict)


def normalize_name(name: str) -> str:
    """Fold case, separators, and the gray/grey split. LDConfig spells it
    British; both spellings must resolve."""
    s = str(name).strip().lower()
    for ch in "_- ":
        s = s.replace(ch, "")
    return s.replace("gray", "grey")


@lru_cache(maxsize=8)
def _palette_for(path_str: str) -> Palette:
    path = Path(path_str)
    colors = parse_ldconfig(path.read_text(errors="replace").splitlines())
    return Palette(by_code={c.code: c for c in colors},
                   by_name={normalize_name(c.name): c for c in colors})


def load_palette(ldraw_dir) -> Palette:
    """Colors from <ldraw_dir>/LDConfig.ldr, cached per path."""
    return _palette_for(str(Path(ldraw_dir) / "LDConfig.ldr"))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_colors.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/colors.py tests/test_colors.py
git commit -m "index the LDraw palette by code and normalized name"
```

---

### Task 4: resolve() — the spec precedence rule

**Files:**
- Modify: `brick_icons/colors.py`
- Test: `tests/test_colors.py`

The rule, in order: an `0x`/`#` prefix or six hex digits is hex; one to three decimal digits is a code; anything else is a name; no match raises.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_colors.py`:

```python
import pytest
from brick_icons.colors import UnknownColorError, resolve


@pytest.fixture
def ld(tmp_path):
    (tmp_path / "LDConfig.ldr").write_text(LDCFG)
    return tmp_path


def test_resolve_hex_forms_pass_through(ld):
    for spec in ("0xc91a09", "#c91a09", "c91a09", "0xC91A09"):
        assert resolve(spec, ld) == ("0xc91a09", None)


def test_resolve_code(ld):
    assert resolve("4", ld) == ("0xb40000", None)
    assert resolve("71", ld) == ("0x969696", None)


def test_resolve_code_carries_alpha(ld):
    assert resolve("36", ld) == ("0xc91a09", 128)


def test_resolve_name(ld):
    assert resolve("red", ld) == ("0xb40000", None)
    assert resolve("Light Bluish Gray", ld) == ("0x969696", None)
    assert resolve("trans_red", ld) == ("0xc91a09", 128)


def test_six_digits_is_hex_but_short_digits_are_a_code(ld):
    # the precedence rule that keeps existing configs working
    assert resolve("000016", ld) == ("0x000016", None)   # hex, not code 16
    assert resolve("0x16", ld) == ("0x000016", None)     # explicit hex
    assert resolve("4", ld) == ("0xb40000", None)        # code, not hex 0x04


def test_unknown_code_and_name_raise(ld):
    with pytest.raises(UnknownColorError, match="999"):
        resolve("999", ld)
    with pytest.raises(UnknownColorError, match="chartreuse"):
        resolve("chartreuse", ld)


def test_malformed_hex_is_treated_as_a_name_and_raises(ld):
    with pytest.raises(UnknownColorError):
        resolve("0xzzzzzz", ld)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_colors.py -q`
Expected: FAIL with `ImportError: cannot import name 'UnknownColorError'`

- [ ] **Step 3: Write the minimal implementation**

Append to `brick_icons/colors.py`:

```python
_HEX6 = re.compile(r"^[0-9a-f]{6}$")
_CODE = re.compile(r"^\d{1,3}$")


class UnknownColorError(ValueError):
    """A --part-color spec that is neither hex, an LDraw code, nor a name."""


def resolve(spec, ldraw_dir) -> tuple:
    """Any color spec -> ('0xrrggbb', alpha or None).

    Precedence matters: a bare '16' is LDraw code 16, but '000016' is hex,
    so existing 0xRRGGBB-era configs keep their meaning.
    """
    s = str(spec).strip()
    body = s[2:] if s[:2].lower() == "0x" else s.lstrip("#")
    explicit_hex = s[:2].lower() == "0x" or s.startswith("#")
    if explicit_hex or _HEX6.match(body.lower()):
        if _HEX6.match(body.lower()):
            return "0x" + body.lower(), None
        if explicit_hex and re.match(r"^[0-9a-f]{1,6}$", body.lower()):
            return "0x%06x" % int(body, 16), None
    pal = load_palette(ldraw_dir)
    if _CODE.match(s):
        c = pal.by_code.get(int(s))
        if c is None:
            raise UnknownColorError(f"no LDraw color with code {s}")
        return c.hex, (c.alpha if c.alpha != 255 else None)
    c = pal.by_name.get(normalize_name(s))
    if c is None:
        raise UnknownColorError(
            f"unknown color {spec!r}: expected 0xRRGGBB, an LDraw code "
            f"(0-511), or a color name (see --list-colors)")
    return c.hex, (c.alpha if c.alpha != 255 else None)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_colors.py -q`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/colors.py tests/test_colors.py
git commit -m "resolve color specs by hex, LDraw code, or name"
```

---

### Task 5: Wire resolve() into load_config, with alpha feeding opacity

**Files:**
- Modify: `brick_icons/config.py:96-118` (the body of `load_config`)
- Test: `tests/test_config.py`

`load_config` must learn which keys the caller set explicitly, so a trans color only supplies `opacity` when the user did not.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
import pytest


def test_part_color_code_resolves_to_hex():
    cfg = load_config(overrides={"part_color": "4"}, root=".")
    assert cfg.part_color == "0xb40000"


def test_part_color_name_resolves_to_hex():
    cfg = load_config(overrides={"part_color": "light bluish gray"}, root=".")
    assert cfg.part_color == "0x969696"


def test_part_color_hex_is_unchanged():
    cfg = load_config(overrides={"part_color": "0xc91a09"}, root=".")
    assert cfg.part_color == "0xc91a09"


def test_trans_code_sets_opacity():
    cfg = load_config(overrides={"part_color": "36"}, root=".")
    assert cfg.part_color == "0xc91a09"
    assert cfg.opacity == pytest.approx(128 / 255)


def test_explicit_opacity_beats_trans_alpha():
    cfg = load_config(overrides={"part_color": "36", "opacity": 0.9}, root=".")
    assert cfg.opacity == 0.9


def test_toml_opacity_beats_trans_alpha(tmp_path):
    t = tmp_path / "labels.toml"
    t.write_text('opacity = 0.8\n')
    cfg = load_config(toml_path=str(t), overrides={"part_color": "36"}, root=".")
    assert cfg.opacity == 0.8


def test_opaque_code_leaves_opacity_alone():
    cfg = load_config(overrides={"part_color": "4"}, root=".")
    assert cfg.opacity == 1.0


def test_unknown_color_raises():
    from brick_icons.colors import UnknownColorError
    with pytest.raises(UnknownColorError):
        load_config(overrides={"part_color": "chartreuse"}, root=".")
```

These use the real vendored `vendor/ldraw/LDConfig.ldr` via `root="."`, so run them from the repo root.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: FAIL — `test_part_color_code_resolves_to_hex` gets `'4'` instead of `'0xb40000'`

- [ ] **Step 3: Write the minimal implementation**

In `brick_icons/config.py`, add the import at the top:

```python
from . import colors
```

Then replace the body of `load_config` from its first line through the `launcher` block with:

```python
def load_config(toml_path=None, overrides=None, root="."):
    data = dict(DEFAULTS)
    explicit = set()
    if toml_path and Path(toml_path).exists():
        with open(toml_path, "rb") as f:
            from_toml = tomllib.load(f)
        data.update(from_toml)
        explicit |= set(from_toml)
    if overrides:
        given = {k: v for k, v in overrides.items() if v is not None}
        data.update(given)
        explicit |= set(given)

    root = Path(root)
    if data.get("label_mm"):
        w_mm, h_mm = data["label_mm"]
        data["width"] = round(w_mm / MM_PER_INCH * data["dpi"])
        data["height"] = round(h_mm / MM_PER_INCH * data["dpi"])

    ldraw_dir = root / data["ldraw_dir"]
    if data["part_color"]:
        hex_str, alpha = colors.resolve(data["part_color"], ldraw_dir)
        data["part_color"] = hex_str
        if alpha is not None and "opacity" not in explicit:
            data["opacity"] = alpha / 255.0

    launcher = data["ldview_launcher"]
    if launcher is None:
        launcher = default_ldview_launcher()
```

And in the `Config(...)` construction, replace the `ldraw_dir=` argument so it reuses the value computed above:

```python
        ldraw_dir=ldraw_dir,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: all pass (8 new + 7 existing)

- [ ] **Step 5: Run the whole suite for regressions**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass. `test_defaults` asserts `cfg.ldraw_dir == Path("/proj/vendor/ldraw")` — the `ldraw_dir=ldraw_dir` change must keep that true.

- [ ] **Step 6: Commit**

```bash
git add brick_icons/config.py tests/test_config.py
git commit -m "resolve --part-color codes and names at config load"
```

---

### Task 6: --list-colors

**Files:**
- Modify: `brick_icons/cli.py:31` (argument), `brick_icons/cli.py:273-283` (`main`)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_list_colors_prints_table_and_exits_ok(capsys):
    from brick_icons import cli
    assert cli.main(["--list-colors", "--root", "."]) == 0
    out = capsys.readouterr().out
    assert "0xb40000" in out and "Red" in out
    assert "Trans_Red" in out and "alpha 128" in out
    assert out.splitlines()[0].split()[0] == "0"      # sorted by code


def test_list_colors_needs_no_parts(capsys):
    from brick_icons import cli
    # without --list-colors this would return 2 ("no parts given")
    assert cli.main(["--list-colors", "--root", "."]) == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k list_colors -q`
Expected: FAIL with `SystemExit: 2` (argparse rejects the unknown `--list-colors`)

- [ ] **Step 3: Write the minimal implementation**

In `_parse_args`, beside the other flags:

```python
    p.add_argument("--list-colors", dest="list_colors", action="store_true",
                   default=False,
                   help="print the LDraw palette (code, name, hex) and exit")
```

In `main`, before the parts check:

```python
def main(argv=None) -> int:
    args = _parse_args(argv)
    if args.list_colors:
        from . import colors
        pal = colors.load_palette(Path(args.root) / "vendor/ldraw")
        for code in sorted(pal.by_code):
            c = pal.by_code[code]
            tail = "" if c.alpha == 255 else f"  alpha {c.alpha}"
            print(f"{c.code:<4} {c.name:<34} {c.hex}{tail}")
        return 0
    cfg = _config_from_args(args)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k list_colors -q`
Expected: 2 passed

- [ ] **Step 5: Eyeball the real output**

Run: `.venv/bin/brick-icons --list-colors | head -20`
Expected: a code/name/hex table starting at code 0 (Black), with `alpha 128` on the Trans_ rows.

- [ ] **Step 6: Commit**

```bash
git add brick_icons/cli.py tests/test_cli.py
git commit -m "add --list-colors to print the LDraw palette"
```

---

### Task 7: Prove the hex path is byte-identical

**Files:** none modified — this is the regression gate.

- [ ] **Step 1: Re-render the specimens**

```bash
.venv/bin/brick-icons --list specimens.txt --root . --format svg --shading outline --shade-style flat3 --out debug/colorcodes/after
```

- [ ] **Step 2: Diff against the Task 1 baseline**

```bash
cd debug/colorcodes
find after -name '*.svg' -exec shasum -a 256 {} + | sed 's/after\///' | sort > after.sha
diff baseline.sha after.sha && echo "BYTE-IDENTICAL"
cd ../..
```

Expected: `BYTE-IDENTICAL`. Any difference means the config rewiring changed rendering — STOP and find it before continuing. Specimens carry no `--part-color`, so nothing about them should move.

- [ ] **Step 3: Prove a code and its hex render identically**

```bash
.venv/bin/brick-icons 3001 --root . --format svg --shading outline --shade-style flat3 \
  --part-color 4 --out debug/colorcodes/bycode
.venv/bin/brick-icons 3001 --root . --format svg --shading outline --shade-style flat3 \
  --part-color 0xb40000 --out debug/colorcodes/byhex
cmp debug/colorcodes/bycode/3001.svg debug/colorcodes/byhex/3001.svg && echo "CODE == HEX"
```

Expected: `CODE == HEX`

---

### Task 8: Document the new spec forms

**Files:**
- Modify: `README.md` (the `--part-color` entry in the options documentation)

- [ ] **Step 1: Find the current wording**

Run: `grep -n "part-color" README.md`

- [ ] **Step 2: Replace the option's description with**

```markdown
`--part-color SPEC` — the brick color. Accepts `0xRRGGBB` / `#RRGGBB`, an
LDraw color code (`4` = Red, `71` = Light Bluish Grey), or a color name
(`red`, `light_bluish_grey`, `light bluish gray` — case, separators and the
gray/grey spelling all fold). `--list-colors` prints the whole palette.
A translucent color supplies `--opacity` from its LDConfig `ALPHA` unless you
pass `--opacity` yourself, so `--part-color trans_red` is a one-flag trans
brick.

Note: codes resolve against the vendored `vendor/ldraw/LDConfig.ldr`, whose
values track current LDraw and differ from the hexes used in the gallery
above — code `4` is `#B40000`, not the `0xc91a09` in the red brick.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "document LDraw codes and names in --part-color"
```

---

### Task 9: Fix the zero-stroke crash in _ink_lens_pockets

**Files:**
- Modify: `brick_icons/shade.py:923`
- Test: `tests/test_shade.py`

`_ink_lens_pockets` returns a bare `[]` on its no-drawn-ink path while its only
caller unpacks two values (`shade.py:1230`), so any opaque part rendered with
`--line-width 0 --silhouette-width 0` dies. `4740` escapes it because
`--opacity 0.55` sets `cull=False` and takes another branch.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_shade.py`:

```python
def test_ink_lens_pockets_returns_a_pair_when_there_is_no_ink():
    from brick_icons import shade
    # zero-width strokes: no ink for a pocket to hide inside. The caller
    # unpacks two values, so the early return must be a pair.
    got = shade._ink_lens_pockets(None, None, [], None, 0, 0)
    assert isinstance(got, tuple) and len(got) == 2
    assert got == ([], [])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_shade.py -k ink_lens_pockets_returns_a_pair -q`
Expected: FAIL — `assert isinstance([], tuple)`

- [ ] **Step 3: Write the minimal implementation**

In `brick_icons/shade.py`, in `_ink_lens_pockets`, change the early return:

```python
    if ink is None or ink.is_empty or base is None or base.is_empty:
        return [], []             # no drawn ink (e.g. zero-width strokes):
                                  # nothing for a pocket to hide inside
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_shade.py -k ink_lens_pockets_returns_a_pair -q`
Expected: 1 passed

- [ ] **Step 5: Verify the real command now works**

```bash
.venv/bin/brick-icons 3941p01 --root . --format svg --shading outline \
  --shade-style flat3 --part-color 0xc91a09 --line-width 0 --silhouette-width 0 \
  --out debug/colorcodes/nostroke
```
Expected: `done: 3941p01`, and `debug/colorcodes/nostroke/3941p01.svg` exists.

- [ ] **Step 6: Confirm the byte-diff gate still holds**

```bash
.venv/bin/brick-icons --list specimens.txt --root . --format svg --shading outline --shade-style flat3 --out debug/colorcodes/after9
cd debug/colorcodes
find after9 -name '*.svg' -exec shasum -a 256 {} + | sed 's/after9\///' | sort > after9.sha
diff baseline.sha after9.sha && echo "BYTE-IDENTICAL"
cd ../..
```

Expected: `BYTE-IDENTICAL` — no specimen uses zero-width strokes, so the changed branch is never reached for them.

- [ ] **Step 7: Commit**

```bash
git add brick_icons/shade.py tests/test_shade.py
git commit -m "return a pair from _ink_lens_pockets when no ink is drawn"
```

---

### Task 10: Measure carrier offsets to unblock phase 2

**Files:**
- Create: `scripts/measure-decal-offsets.py`

Phase 2 binds a decal facet to its carrier surface when the facet sits within
some tolerance of it. That tolerance is the design's one unknown: too tight and
decals never bind, too loose and it swallows standoff geometry that is meant to
stand proud. This task measures the real distribution instead of guessing.

- [ ] **Step 1: Write the script**

Create `scripts/measure-decal-offsets.py`:

```python
"""Distance from each printed part's pattern geometry to its carrier surface.

Phase 2 of docs/superpowers/specs/2026-08-28-printed-parts-design.md needs a
binding tolerance. For every '1 <code> ...' subfile reference in a printed
part, this reports the reference's distance from the part's axis alongside the
radii of the cylinders/cones in the same file, so the offsets can be compared
across parts. One line per part as it goes (these runs are slow).
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

CURVED = ("cyli", "con", "ndis", "disc", "chrd", "ring")


def refs(path: Path):
    for ln in path.read_text(errors="replace").splitlines():
        tok = ln.split()
        if len(tok) >= 15 and tok[0] == "1":
            name = tok[14].replace("\\", "/").split("/")[-1].lower()
            yield int(tok[1]), tuple(float(x) for x in tok[2:5]), name


def main(argv):
    parts_dir = Path(argv[1]) if len(argv) > 1 else Path("vendor/ldraw/parts")
    ids = argv[2:] or ["3941p01", "3062bp01", "3942bp01", "4740p01",
                       "3960p01", "6141p01"]
    for i, pid in enumerate(ids, 1):
        f = parts_dir / f"{pid}.dat"
        if not f.exists():
            print(f"[{i}/{len(ids)}] {pid}: MISSING")
            continue
        body, decal = [], []
        for code, (x, y, z), name in refs(f):
            if not any(k in name for k in CURVED):
                continue
            r = math.hypot(x, z)
            (body if code == 16 else decal).append((r, name, code))
        br = sorted({round(r, 3) for r, _, _ in body})
        dr = sorted({round(r, 3) for r, _, _ in decal})
        gap = (min(abs(d - b) for b in br) if br else float("nan"))
        print(f"[{i}/{len(ids)}] {pid}: body radii {br[:5]} | "
              f"decal radii {dr[:5]} | "
              f"min decal-to-body gap {gap:.3f} LDU"
              if dr and br else
              f"[{i}/{len(ids)}] {pid}: body {br[:5]} decal {dr[:5]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 2: Run it on the sample set**

Run: `.venv/bin/python scripts/measure-decal-offsets.py`
Expected: one line per part, each naming the body radii, the decal radii, and the gap between them. `3941p01` should show a body radius near 20 and decal references near 19.6.

- [ ] **Step 3: Record what it found**

Append a short section to
`docs/superpowers/specs/2026-08-28-printed-parts-design.md` under phase 2,
stating the observed gaps and whether a single tolerance separates decal
offsets from genuine standoff geometry. If the distribution is bimodal or the
gaps vary by more than an order of magnitude across parts, say so plainly —
that finding changes the phase 2 design and must not be smoothed over.

- [ ] **Step 4: Commit**

```bash
git add scripts/measure-decal-offsets.py docs/superpowers/specs/2026-08-28-printed-parts-design.md
git commit -m "measure decal-to-carrier offsets across printed parts"
```

---

### Task 11: Add printed parts to the specimen set (gated on review)

**Files:**
- Modify: `specimens.txt`

**Gate:** do this only after a human has looked at the printed-part contact
sheet and agreed which parts are worth carrying. Printed parts currently render
as embossed outlines, so they are a *baseline* here — something for phase 2 to
improve on — not a demonstration of finished work. Do not add them to
`docs/gallery/` or the README table until phase 2 lands.

- [ ] **Step 1: Add the agreed ids to `specimens.txt`**

Under a new section, using the file's existing comment style:

```
# --- Printed decoration (phase 2 baseline: these render as embossing today) ---
3941p01 # 2x2 round brick, printed panel on a cylinder wall
3942bp01        # cone 2x2x2, printed band on a tapered wall
3068bp00        # tile 2x2, printed on a flat face (no carrier curvature)
```

Replace these ids with whichever the reviewer picked.

- [ ] **Step 2: Confirm they render**

Run: `.venv/bin/brick-icons --list specimens.txt --root . --format svg --shading outline --shade-style flat3 --out debug/colorcodes/specimens-new`
Expected: one `.svg` per id including the new ones, no traceback.

- [ ] **Step 3: Re-baseline the byte-diff gate**

The specimen set changed, so the Task 1 baseline no longer covers it:

```bash
cd debug/colorcodes
find specimens-new -name '*.svg' -exec shasum -a 256 {} + | sed 's/specimens-new\///' | sort > baseline-v2.sha
cd ../..
```

Note in the commit message that `baseline-v2.sha` supersedes the Task 1 baseline.

- [ ] **Step 4: Commit**

```bash
git add specimens.txt
git commit -m "add printed parts to the specimen set"
```

---

## Done when

- `--part-color 4`, `--part-color red`, and `--part-color 0xb40000` all render the same brick.
- `--part-color 36` produces a translucent brick without a separate `--opacity`.
- `--list-colors` prints all 322 colors.
- The specimen byte-diff gate passes against the Task 1 baseline.
- `--line-width 0 --silhouette-width 0` no longer crashes.
- Phase 2's binding tolerance is backed by measurement rather than a guess.
