# Lab Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local HTTP server that renders brick-icons parts on demand through the CLI's own code path, and serves the corpus lists, part search, golden status and defect store the lab frontend needs.

**Architecture:** `cli.py`'s argparse parser becomes the single source of truth for render parameters — the server derives its config schema from it and executes the argv it was handed through `build_parser().parse_args()` → `_config_from_args` → `process_one`. Renders are cached on disk under `out/lab/<sha of argv>/`. FastAPI serves JSON routes plus SSE for long jobs.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, pytest with `fastapi.testclient`. No new runtime dependency for `brick_icons` itself — the server lives behind a `lab` optional-dependency extra.

**Spec:** `docs/superpowers/specs/2026-08-31-corpus-lab-design.md`

---

## File Structure

| file | responsibility |
|---|---|
| `brick_icons/cli.py` (modify) | gains `build_parser()`; `_parse_args` calls it |
| `brick_icons/lab/__init__.py` | empty package marker |
| `brick_icons/lab/schema.py` | argparse parser → JSON config schema |
| `brick_icons/lab/cache.py` | argv → cache key → directory, and listing what a render wrote |
| `brick_icons/lab/runner.py` | run one argv through the CLI path; collect artifacts |
| `brick_icons/lab/corpus.py` | read the corpus lists |
| `brick_icons/lab/partindex.py` | index and search the LDraw library by id and description |
| `brick_icons/lab/defects.py` | read/write `tests/goldens/defects.toml` |
| `brick_icons/lab/diff.py` | raster diff with connected-component count |
| `brick_icons/lab/jobs.py` | in-process job registry with progress events |
| `brick_icons/lab/app.py` | FastAPI app: the routes |
| `brick_icons/lab/__main__.py` | `python -m brick_icons.lab` |
| `tests/test_lab_*.py` | one test module per source module above |

Each module is importable and testable without the server; `app.py` only wires them to routes.

---

## Task 1: Expose the CLI's parser

The server cannot derive a schema from a parser that is built and thrown away inside a function. Splitting it changes no behavior.

**Files:**
- Modify: `brick_icons/cli.py:14-81`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_build_parser_is_the_parser_parse_args_uses():
    p = cli.build_parser()
    dests = {a.dest for a in p._actions}
    assert {"parts", "engine", "shading", "shade_style", "angle"} <= dests


def test_parse_args_still_reads_a_command():
    args = cli._parse_args(["3001", "--engine", "occt", "--angle", "30,25"])
    assert args.parts == ["3001"]
    assert args.engine == "occt"
    assert args.angle == "30,25"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli.py -k build_parser -v`
Expected: FAIL with `AttributeError: module 'brick_icons.cli' has no attribute 'build_parser'`

- [ ] **Step 3: Split the function**

In `brick_icons/cli.py`, rename `def _parse_args(argv):` to `def build_parser():`, remove its trailing `return p.parse_args(argv)` and end it with `return p`. Then add directly below it:

```python
def _parse_args(argv):
    return build_parser().parse_args(argv)
```

- [ ] **Step 4: Run the CLI test module**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: PASS, including every pre-existing test in the module

- [ ] **Step 5: Commit**

```bash
git add brick_icons/cli.py tests/test_cli.py
git commit -m "expose the CLI parser as build_parser"
```

---

## Task 2: Derive the config schema from the parser

**Files:**
- Create: `brick_icons/lab/__init__.py` (empty)
- Create: `brick_icons/lab/schema.py`
- Test: `tests/test_lab_schema.py`

The frontend builds its control panel from this. A field's `dest` is its key, and `flag` is what goes back into argv.

- [ ] **Step 1: Write the failing test**

Create `tests/test_lab_schema.py`:

```python
"""The schema is derived, never written by hand: a flag the CLI grows must
appear in the lab's control panel without anyone editing the frontend."""
from brick_icons import cli
from brick_icons.lab import schema


def test_every_optional_flag_appears():
    fields = {f["key"]: f for f in schema.config_schema()}
    parser_dests = {a.dest for a in cli.build_parser()._actions
                    if a.option_strings and a.dest != "help"}
    assert parser_dests == set(fields)


def test_carries_flag_choices_and_help():
    fields = {f["key"]: f for f in schema.config_schema()}
    assert fields["engine"]["flag"] == "--engine"
    assert fields["engine"]["choices"] == ["naive", "occt"]
    assert fields["shade_style"]["flag"] == "--shade-style"
    assert "outline" in fields["shading"]["choices"]
    assert fields["opacity"]["help"]


def test_types_are_named_for_the_frontend():
    fields = {f["key"]: f for f in schema.config_schema()}
    assert fields["render_px"]["type"] == "int"
    assert fields["opacity"]["type"] == "float"
    assert fields["weld_corners"]["type"] == "bool"
    assert fields["angle"]["type"] == "str"


def test_nargs_fields_report_their_arity():
    fields = {f["key"]: f for f in schema.config_schema()}
    assert fields["label_mm"]["nargs"] == 2
    assert fields["levels"]["nargs"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brick_icons.lab'`

- [ ] **Step 3: Write the implementation**

Create `brick_icons/lab/__init__.py` as an empty file. Create `brick_icons/lab/schema.py`:

```python
"""The lab's config schema, read off the CLI's own parser.

Nothing here lists parameters. A flag added to `cli.build_parser` shows up in
the lab with no other change, which is the only way the two stay in step.
"""
from __future__ import annotations

import argparse

from .. import cli

_TYPES = {int: "int", float: "float", str: "str"}


def _type_name(action) -> str:
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "bool"
    return _TYPES.get(action.type, "str")


def config_schema() -> list[dict]:
    """One entry per optional flag: key, flag, type, choices, help, nargs."""
    out = []
    for a in cli.build_parser()._actions:
        if not a.option_strings or a.dest == "help":
            continue
        nargs = a.nargs if isinstance(a.nargs, int) else None
        out.append({
            "key": a.dest,
            "flag": a.option_strings[0],
            "type": _type_name(a),
            "choices": list(a.choices) if a.choices else None,
            "help": a.help or "",
            "nargs": nargs,
            "default": a.default,
        })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_schema.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/__init__.py brick_icons/lab/schema.py tests/test_lab_schema.py
git commit -m "derive the lab config schema from the CLI parser"
```

---

## Task 3: Build argv from a config dict, and prove the round trip

**Files:**
- Modify: `brick_icons/lab/schema.py`
- Test: `tests/test_lab_schema.py`

The frontend shows this argv as the copy-able command, and the server executes
it. Building it server-side means one implementation, not two.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lab_schema.py`:

```python
def test_builds_argv_in_flag_order():
    argv = schema.to_argv("3001", {"engine": "occt", "shading": "outline"})
    assert argv[0] == "3001"
    assert "--engine" in argv and argv[argv.index("--engine") + 1] == "occt"
    assert "--shading" in argv and argv[argv.index("--shading") + 1] == "outline"


def test_omits_none_and_renders_flags_as_bare_switches():
    argv = schema.to_argv("3001", {"engine": None, "weld_corners": True})
    assert "--engine" not in argv
    assert "--weld-corners" in argv
    assert argv[argv.index("--weld-corners"):] == ["--weld-corners"]


def test_a_false_switch_is_absent_not_negated():
    assert "--weld-corners" not in schema.to_argv("3001", {"weld_corners": False})


def test_multi_value_flags_expand():
    argv = schema.to_argv("3001", {"label_mm": [40.0, 20.0]})
    i = argv.index("--label-mm")
    assert argv[i + 1:i + 3] == ["40.0", "20.0"]


def test_argv_round_trips_through_the_cli(tmp_path):
    """The whole point: what the lab runs parses to what the CLI would."""
    cfgd = {"engine": "occt", "shading": "outline", "shade_style": "flat3",
            "angle": "30,25", "opacity": 0.55}
    argv = schema.to_argv("3941", cfgd)
    args = cli._parse_args(argv)
    assert args.parts == ["3941"]
    assert (args.engine, args.shading, args.shade_style) == ("occt", "outline", "flat3")
    assert args.angle == "30,25"
    assert args.opacity == 0.55


def test_an_unknown_key_is_rejected_rather_than_dropped():
    import pytest
    with pytest.raises(KeyError):
        schema.to_argv("3001", {"not_a_flag": 1})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_schema.py -k argv -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'to_argv'`

- [ ] **Step 3: Write the implementation**

Append to `brick_icons/lab/schema.py`:

```python
def to_argv(part: str, config: dict) -> list[str]:
    """`part` plus one flag per set config key, in schema order.

    A None value means "leave it to the config file", so it is omitted rather
    than passed as an empty string. A false switch is likewise absent: argparse
    store_true flags have no negative form.
    """
    fields = {f["key"]: f for f in config_schema()}
    unknown = set(config) - set(fields)
    if unknown:
        raise KeyError(f"not CLI flags: {sorted(unknown)}")
    argv = [part]
    for key, field in fields.items():
        if key not in config:
            continue
        value = config[key]
        if value is None:
            continue
        if field["type"] == "bool":
            if value:
                argv.append(field["flag"])
            continue
        argv.append(field["flag"])
        values = value if isinstance(value, (list, tuple)) else [value]
        argv.extend(str(v) for v in values)
    return argv
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_schema.py -v`
Expected: PASS, 10 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/schema.py tests/test_lab_schema.py
git commit -m "build CLI argv from a lab config dict"
```

---

## Task 4: Cache renders by argv

**Files:**
- Create: `brick_icons/lab/cache.py`
- Test: `tests/test_lab_cache.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_lab_cache.py`:

```python
from brick_icons.lab import cache


def test_same_argv_gives_the_same_key():
    a = cache.key(["3001", "--engine", "occt"])
    b = cache.key(["3001", "--engine", "occt"])
    assert a == b


def test_different_argv_gives_a_different_key():
    assert cache.key(["3001"]) != cache.key(["3002"])
    assert cache.key(["3001"]) != cache.key(["3001", "--engine", "occt"])


def test_key_is_order_insensitive_across_flags():
    """`--engine occt --shading outline` and the reverse are one render."""
    a = cache.key(["3001", "--engine", "occt", "--shading", "outline"])
    b = cache.key(["3001", "--shading", "outline", "--engine", "occt"])
    assert a == b


def test_key_is_filesystem_safe():
    k = cache.key(["3001", "--angle", "30,25"])
    assert k.isalnum() and len(k) == 16


def test_dir_for_is_under_the_root(tmp_path):
    d = cache.dir_for(["3001"], root=tmp_path)
    assert tmp_path in d.parents


def test_artifacts_lists_what_a_render_wrote(tmp_path):
    d = cache.dir_for(["3001"], root=tmp_path)
    d.mkdir(parents=True)
    (d / "3001.svg").write_text("<svg/>")
    (d / "3001.gray.png").write_bytes(b"")
    names = {a["name"] for a in cache.artifacts(d)}
    assert names == {"3001.svg", "3001.gray.png"}


def test_artifacts_is_empty_for_a_missing_dir(tmp_path):
    assert cache.artifacts(tmp_path / "nope") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brick_icons.lab.cache'`

- [ ] **Step 3: Write the implementation**

Create `brick_icons/lab/cache.py`:

```python
"""Rendered artifacts, keyed by the argv that produced them.

The key sorts the flags so that two commands that differ only in the order
their flags were typed hit one cache entry rather than two.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

DEFAULT_ROOT = Path("out/lab")


def _canonical(argv: list[str]) -> str:
    parts = [a for a in argv if not a.startswith("--")]
    flags, i = [], 0
    while i < len(argv):
        if argv[i].startswith("--"):
            j = i + 1
            while j < len(argv) and not argv[j].startswith("--"):
                j += 1
            flags.append(" ".join(argv[i:j]))
            i = j
        else:
            i += 1
    return "\x00".join([*parts, *sorted(flags)])


def key(argv: list[str]) -> str:
    return hashlib.sha256(_canonical(argv).encode()).hexdigest()[:16]


def dir_for(argv: list[str], root: Path | str = DEFAULT_ROOT) -> Path:
    return Path(root) / key(argv)


def artifacts(directory: Path) -> list[dict]:
    """Every file in a cache dir, as name and byte size."""
    if not Path(directory).is_dir():
        return []
    return sorted(
        ({"name": p.name, "bytes": p.stat().st_size}
         for p in Path(directory).iterdir() if p.is_file()),
        key=lambda a: a["name"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_cache.py -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/cache.py tests/test_lab_cache.py
git commit -m "cache lab renders by canonicalized argv"
```

---

## Task 5: Run one render through the CLI's own path

**Files:**
- Create: `brick_icons/lab/runner.py`
- Test: `tests/test_lab_runner.py`

`3005` (1x1 brick) is the fast part the golden harness already uses for its
smoke mode, so it is what the tests render.

- [ ] **Step 1: Write the failing test**

Create `tests/test_lab_runner.py`:

```python
"""A lab render is the CLI's render: same parser, same Config, same
process_one. Anything else and the app drifts from the command line."""
import pytest

from brick_icons.lab import runner


def test_runs_and_writes_an_svg(tmp_path, ldraw_dir):
    result = runner.render(["3005", "--format", "svg", "--shading", "outline"],
                           root=tmp_path)
    assert result["ok"]
    assert "3005.svg" in {a["name"] for a in result["artifacts"]}
    assert result["seconds"] > 0


def test_reports_the_argv_it_actually_ran(tmp_path, ldraw_dir):
    argv = ["3005", "--format", "svg", "--shading", "outline"]
    result = runner.render(argv, root=tmp_path)
    assert result["argv"] == argv
    assert result["command"].startswith("brick-icons 3005 ")


def test_second_run_is_served_from_cache(tmp_path, ldraw_dir):
    argv = ["3005", "--format", "svg", "--shading", "outline"]
    first = runner.render(argv, root=tmp_path)
    second = runner.render(argv, root=tmp_path)
    assert first["cached"] is False
    assert second["cached"] is True


def test_force_reruns_a_cached_render(tmp_path, ldraw_dir):
    argv = ["3005", "--format", "svg", "--shading", "outline"]
    runner.render(argv, root=tmp_path)
    again = runner.render(argv, root=tmp_path, force=True)
    assert again["cached"] is False


def test_a_bad_flag_is_an_error_not_a_crash(tmp_path):
    result = runner.render(["3005", "--nonsense"], root=tmp_path)
    assert result["ok"] is False
    assert "nonsense" in result["error"]


def test_a_missing_part_is_an_error(tmp_path, ldraw_dir):
    result = runner.render(["definitely-not-a-part"], root=tmp_path)
    assert result["ok"] is False
    assert result["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brick_icons.lab.runner'`

- [ ] **Step 3: Write the implementation**

Create `brick_icons/lab/runner.py`:

```python
"""Run one lab render.

The path is the CLI's: `build_parser().parse_args` for the argv, then
`_config_from_args`, then `process_one`. `process_one` returns nothing and
writes several files, so the render gets its own cache directory and the
artifacts are whatever appeared in it.
"""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from .. import cli
from . import cache


def _command(argv: list[str]) -> str:
    return " ".join(["brick-icons", *argv])


def render(argv: list[str], root: Path | str = cache.DEFAULT_ROOT,
           force: bool = False) -> dict:
    out_dir = cache.dir_for(argv, root=root)
    existing = cache.artifacts(out_dir)
    if existing and not force:
        return {"ok": True, "cached": True, "argv": argv,
                "command": _command(argv), "key": cache.key(argv),
                "artifacts": existing, "seconds": 0.0, "error": None}
    if force and out_dir.exists():
        shutil.rmtree(out_dir)

    parser = cli.build_parser()
    parser.exit_on_error = False

    def failed(message: str) -> dict:
        return {"ok": False, "cached": False, "argv": argv,
                "command": _command(argv), "key": cache.key(argv),
                "artifacts": [], "seconds": 0.0, "error": message}

    # `parse_args` on an unknown flag calls `parser.error`, which raises
    # SystemExit(2) -- whose str() is "2", losing the message the caller needs.
    try:
        args, extra = parser.parse_known_args(argv)
    except (argparse.ArgumentError, SystemExit) as e:
        return failed(f"bad arguments: {e}")
    if extra:
        return failed(f"unrecognized arguments: {' '.join(extra)}")

    started = time.perf_counter()
    try:
        cfg = cli._config_from_args(args)
        parts = cli._gather_parts(args)
        if not parts:
            raise ValueError("no part given")
        cli.process_one(cfg, parts[0], out_dir)
    except Exception as e:                          # noqa: BLE001
        return {"ok": False, "cached": False, "argv": argv,
                "command": _command(argv), "key": cache.key(argv),
                "artifacts": cache.artifacts(out_dir),
                "seconds": time.perf_counter() - started,
                "error": f"{type(e).__name__}: {e}"}

    return {"ok": True, "cached": False, "argv": argv,
            "command": _command(argv), "key": cache.key(argv),
            "artifacts": cache.artifacts(out_dir),
            "seconds": time.perf_counter() - started, "error": None}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_runner.py -v`
Expected: PASS, 6 tests. The two rendering tests take a few seconds each.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/runner.py tests/test_lab_runner.py
git commit -m "run a lab render through the CLI's parse-config-render path"
```

---

## Task 6: Read the corpus lists

**Files:**
- Create: `brick_icons/lab/corpus.py`
- Test: `tests/test_lab_corpus.py`

Four sources, three formats: `parts.txt` (bare ids, whole-line comments),
`specimens.txt` (ids with inline trailing comments), `tests/goldens/manifest.toml`
(named lists under `[parts]`), and `tests/goldens/decal-corpus.txt`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_lab_corpus.py`:

```python
from pathlib import Path

from brick_icons.lab import corpus

ROOT = Path(__file__).resolve().parent.parent


def test_lists_every_source():
    names = {c["name"] for c in corpus.lists(root=ROOT)}
    assert {"parts", "specimens", "manifest:all", "manifest:unprinted",
            "manifest:spread"} <= names


def test_parts_txt_drops_comments_and_blanks():
    got = {c["name"]: c for c in corpus.lists(root=ROOT)}["parts"]
    assert "3001" in got["parts"]
    assert not any(p.startswith("#") for p in got["parts"])
    assert "" not in got["parts"]


def test_specimens_strips_inline_comments():
    got = {c["name"]: c for c in corpus.lists(root=ROOT)}["specimens"]
    assert "3941" in got["parts"]
    assert not any(" " in p for p in got["parts"])


def test_manifest_lists_come_from_the_toml():
    got = {c["name"]: c for c in corpus.lists(root=ROOT)}["manifest:spread"]
    assert got["parts"][0] == "3005"
    assert "3649" in got["parts"]


def test_a_missing_source_is_skipped_not_fatal(tmp_path):
    assert corpus.lists(root=tmp_path) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_corpus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brick_icons.lab.corpus'`

- [ ] **Step 3: Write the implementation**

Create `brick_icons/lab/corpus.py`:

```python
"""The corpus lists, read where they already live.

The lab reads these and never writes them: which parts belong in which list is
a curation decision that stays in the files and in review.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

_TEXT_SOURCES = {
    "parts": "parts.txt",
    "specimens": "specimens.txt",
    "decal-corpus": "tests/goldens/decal-corpus.txt",
}
_MANIFEST = "tests/goldens/manifest.toml"


def _ids(path: Path) -> list[str]:
    out = []
    for line in path.read_text().splitlines():
        token = line.split("#")[0].strip()
        if token:
            out.append(token.split()[0])
    return out


def lists(root: Path | str = ".") -> list[dict]:
    """Every corpus list, as name, source path and part ids."""
    root = Path(root)
    out = []
    for name, rel in _TEXT_SOURCES.items():
        path = root / rel
        if path.exists():
            out.append({"name": name, "source": rel, "parts": _ids(path)})
    manifest = root / _MANIFEST
    if manifest.exists():
        data = tomllib.loads(manifest.read_text())
        for name, parts in data.get("parts", {}).items():
            out.append({"name": f"manifest:{name}", "source": _MANIFEST,
                        "parts": list(parts)})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_corpus.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/corpus.py tests/test_lab_corpus.py
git commit -m "read the corpus lists for the lab"
```

---

## Task 7: Index and search the LDraw library

**Files:**
- Create: `brick_icons/lab/partindex.py`
- Test: `tests/test_lab_partindex.py`

Line 1 of an LDraw `.dat` is `0 <description>`. Searching it is what makes
`slope 45` find a part whose id you do not remember. Per the project's own
rule, the description line is also the authority on whether a part is printed —
never the id.

- [ ] **Step 1: Write the failing test**

Create `tests/test_lab_partindex.py`:

```python
import pytest

from brick_icons.lab import partindex


@pytest.fixture(scope="module")
def index(ldraw_dir):
    return partindex.build(ldraw_dir)


def test_indexes_the_whole_parts_directory(index):
    assert len(index) > 20000


def test_carries_the_description_line(index):
    assert "Brick  2 x  4" in index["3001"]["description"]


def test_flags_printed_parts_from_the_description_not_the_id(index):
    assert index["3040bp08"]["printed"] is True
    assert index["3001"]["printed"] is False


def test_search_matches_an_id_prefix(index):
    hits = [h["id"] for h in partindex.search(index, "3941")]
    assert "3941" in hits


def test_search_matches_words_in_the_description(index):
    hits = [h["id"] for h in partindex.search(index, "brick 2 x 4")]
    assert "3001" in hits


def test_search_ranks_an_exact_id_first(index):
    assert partindex.search(index, "3001")[0]["id"] == "3001"


def test_search_is_capped(index):
    assert len(partindex.search(index, "brick", limit=25)) == 25


def test_empty_query_returns_nothing(index):
    assert partindex.search(index, "  ") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_partindex.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brick_icons.lab.partindex'`

- [ ] **Step 3: Write the implementation**

Create `brick_icons/lab/partindex.py`:

```python
"""Part id and description, for the title-bar search.

`printed` reads line 1, not the id: `^\\d{3,}p\\d+$` catches only 3254 of
13081 printed parts and 132 bare-numeric ids are patterned, so the id is a
fast path and never the authority.
"""
from __future__ import annotations

from pathlib import Path


def _description(path: Path) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            first = fh.readline().strip()
    except OSError:
        return ""
    return first[1:].strip() if first.startswith("0") else ""


def build(ldraw_dir: Path | str) -> dict[str, dict]:
    """Every file in `parts/`, as id -> {description, printed}."""
    out = {}
    for path in sorted(Path(ldraw_dir).joinpath("parts").glob("*.dat")):
        desc = _description(path)
        out[path.stem] = {
            "id": path.stem,
            "description": desc,
            "printed": "pattern" in desc.lower() or "sticker" in desc.lower(),
        }
    return out


def search(index: dict[str, dict], query: str, limit: int = 25) -> list[dict]:
    """Id and description matches, exact id first, then id prefix, then text."""
    q = query.strip().lower()
    if not q:
        return []
    words = q.split()
    exact, prefix, text = [], [], []
    for entry in index.values():
        pid = entry["id"].lower()
        haystack = f"{pid} {entry['description'].lower()}"
        if pid == q:
            exact.append(entry)
        elif pid.startswith(q):
            prefix.append(entry)
        elif all(w in haystack for w in words):
            text.append(entry)
    return [*exact, *prefix, *text][:limit]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_partindex.py -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/partindex.py tests/test_lab_partindex.py
git commit -m "index the LDraw library by id and description"
```

---

## Task 8: The defect store

**Files:**
- Create: `brick_icons/lab/defects.py`
- Test: `tests/test_lab_defects.py`

TOML has no stdlib writer, so the writer here is hand-rolled and deliberately
narrow — it emits exactly the fields the schema defines, in a fixed order, so a
diff of `defects.toml` reads as a change of meaning rather than of formatting.

- [ ] **Step 1: Write the failing test**

Create `tests/test_lab_defects.py`:

```python
import pytest

from brick_icons.lab import defects

ONE = {
    "id": "3941-occt-borehole",
    "part": "3941",
    "engines": ["occt"],
    "status": "open",
    "title": "borehole rim not drawn",
    "mark": {"x": 0.42, "y": 0.55, "w": 0.11, "h": 0.09},
    "seen": {"angle": "30,25", "shading": "outline", "shade_style": "flat3"},
    "filed": "2026-08-31",
    "notes": "the near lip is legitimately hidden; occt draws nothing at all",
}


def test_reading_a_missing_file_is_an_empty_list(tmp_path):
    assert defects.load(tmp_path / "defects.toml") == []


def test_a_defect_round_trips(tmp_path):
    path = tmp_path / "defects.toml"
    defects.save(path, [ONE])
    assert defects.load(path) == [ONE]


def test_multiline_notes_survive(tmp_path):
    path = tmp_path / "defects.toml"
    d = {**ONE, "notes": "first line\nsecond line"}
    defects.save(path, [d])
    assert defects.load(path)[0]["notes"] == "first line\nsecond line"


def test_a_quote_in_a_title_survives(tmp_path):
    path = tmp_path / "defects.toml"
    d = {**ONE, "title": 'the "near" lip'}
    defects.save(path, [d])
    assert defects.load(path)[0]["title"] == 'the "near" lip'


def test_adding_keeps_the_existing_defects(tmp_path):
    path = tmp_path / "defects.toml"
    defects.save(path, [ONE])
    second = {**ONE, "id": "4070-occt-ledge", "part": "4070"}
    defects.add(path, second)
    assert [d["id"] for d in defects.load(path)] == [ONE["id"], second["id"]]


def test_adding_a_duplicate_id_is_refused(tmp_path):
    path = tmp_path / "defects.toml"
    defects.save(path, [ONE])
    with pytest.raises(ValueError):
        defects.add(path, dict(ONE))


def test_update_changes_one_field(tmp_path):
    path = tmp_path / "defects.toml"
    defects.save(path, [ONE])
    defects.update(path, ONE["id"], {"status": "fixed"})
    assert defects.load(path)[0]["status"] == "fixed"
    assert defects.load(path)[0]["title"] == ONE["title"]


def test_update_rejects_an_unknown_status(tmp_path):
    path = tmp_path / "defects.toml"
    defects.save(path, [ONE])
    with pytest.raises(ValueError):
        defects.update(path, ONE["id"], {"status": "maybe"})


def test_update_of_a_missing_defect_is_an_error(tmp_path):
    path = tmp_path / "defects.toml"
    defects.save(path, [ONE])
    with pytest.raises(KeyError):
        defects.update(path, "no-such-id", {"status": "fixed"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_defects.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brick_icons.lab.defects'`

- [ ] **Step 3: Write the implementation**

Create `brick_icons/lab/defects.py`:

```python
"""The defect list, as git-tracked TOML.

Written in a fixed field order so a diff shows a change of meaning rather than
a reshuffle. Part ids live here and in the other corpus data files, never in
the library.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

DEFAULT_PATH = Path("tests/goldens/defects.toml")
STATUSES = ("open", "fixed", "wontfix", "notabug")
_ORDER = ("id", "part", "engines", "status", "title", "mark", "seen",
          "filed", "notes")

_HEADER = """\
# Defects found in corpus renders, filed from the lab.
#
# Written by brick_icons.lab; hand edits are kept but reformatted on the next
# write. `mark` is in fractions of the render box, so it survives a change of
# --render-px but not of --angle -- which is what `seen` records.

"""


def _dump_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_dump_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_dump_value(v)}"
                                for k, v in value.items()) + " }"
    text = str(value)
    if "\n" in text:
        return '"""\n' + text.replace("\\", "\\\\") + '"""'
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def load(path: Path | str = DEFAULT_PATH) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    return list(tomllib.loads(path.read_text()).get("defect", []))


def save(path: Path | str, records: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = [_HEADER]
    for record in records:
        lines = ["[[defect]]"]
        for field in _ORDER:
            if field in record:
                lines.append(f"{field} = {_dump_value(record[field])}")
        for field in sorted(set(record) - set(_ORDER)):
            lines.append(f"{field} = {_dump_value(record[field])}")
        chunks.append("\n".join(lines) + "\n")
    path.write_text("\n".join(chunks))


def add(path: Path | str, record: dict) -> dict:
    records = load(path)
    if any(r["id"] == record["id"] for r in records):
        raise ValueError(f"defect {record['id']!r} already exists")
    if record.get("status", "open") not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    records.append(record)
    save(path, records)
    return record


def update(path: Path | str, defect_id: str, changes: dict) -> dict:
    if "status" in changes and changes["status"] not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    records = load(path)
    for record in records:
        if record["id"] == defect_id:
            record.update(changes)
            save(path, records)
            return record
    raise KeyError(f"no defect {defect_id!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_defects.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/defects.py tests/test_lab_defects.py
git commit -m "store lab defects as git-tracked TOML"
```

---

## Task 9: Diff two renders by connected component

**Files:**
- Create: `brick_icons/lab/diff.py`
- Test: `tests/test_lab_diff.py`

A pixel count cannot separate antialias fringe from a real defect: the fringe
scatters into hundreds of one- and two-pixel components while a defect is a
handful of chunky ones. So the diff reports components, sized, and the pixel
total only as a footnote.

- [ ] **Step 1: Write the failing test**

Create `tests/test_lab_diff.py`:

```python
import numpy as np
from PIL import Image

from brick_icons.lab import diff


def _img(fill=255, boxes=()):
    a = np.full((64, 64), fill, np.uint8)
    for x0, y0, x1, y1 in boxes:
        a[y0:y1, x0:x1] = 0
    return Image.fromarray(a, "L")


def test_identical_images_have_no_components():
    r = diff.compare(_img(), _img())
    assert r["components"] == 0
    assert r["pixels"] == 0


def test_one_block_is_one_component():
    r = diff.compare(_img(), _img(boxes=[(10, 10, 20, 20)]))
    assert r["components"] == 1
    assert r["pixels"] == 100


def test_two_separated_blocks_are_two_components():
    r = diff.compare(_img(), _img(boxes=[(2, 2, 8, 8), (40, 40, 48, 48)]))
    assert r["components"] == 2


def test_component_sizes_are_reported_largest_first():
    r = diff.compare(_img(), _img(boxes=[(2, 2, 6, 6), (30, 30, 42, 42)]))
    assert r["sizes"] == [144, 16]


def test_speckle_below_the_floor_is_not_counted():
    """One stray pixel is antialias, not a defect."""
    r = diff.compare(_img(), _img(boxes=[(5, 5, 6, 6)]), min_size=4)
    assert r["components"] == 0


def test_sizes_are_capped_so_a_fringe_cannot_flood_the_response():
    boxes = [(2 * i, 2 * i, 2 * i + 1, 2 * i + 1) for i in range(30)]
    r = diff.compare(_img(), _img(boxes=boxes), min_size=1, max_listed=10)
    assert len(r["sizes"]) == 10
    assert r["components"] == 30


def test_mismatched_sizes_are_an_error():
    import pytest
    small = Image.fromarray(np.full((8, 8), 255, np.uint8), "L")
    with pytest.raises(ValueError):
        diff.compare(_img(), small)


def test_writes_a_visualisation(tmp_path):
    out = tmp_path / "d.png"
    diff.compare(_img(), _img(boxes=[(10, 10, 20, 20)]), out_png=out)
    assert out.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_diff.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brick_icons.lab.diff'`

- [ ] **Step 3: Write the implementation**

Create `brick_icons/lab/diff.py`:

```python
"""Compare two renders by connected component.

A small pixel diff is not agreement. Antialias fringe scatters into hundreds of
tiny components and a real defect is a handful of chunky ones, so the component
count and the component sizes are the answer; `pixels` is a footnote.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def _label(mask: np.ndarray) -> list[int]:
    """Sizes of 4-connected True regions, by iterative flood fill."""
    h, w = mask.shape
    seen = np.zeros((h, w), bool)
    sizes = []
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        stack, size = [(sy, sx)], 0
        seen[sy, sx] = True
        while stack:
            y, x = stack.pop()
            size += 1
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        sizes.append(size)
    return sizes


def compare(a: Image.Image, b: Image.Image, threshold: int = 16,
            min_size: int = 1, max_listed: int = 32,
            out_png: Path | str | None = None) -> dict:
    """Component count and sizes for the pixels where `a` and `b` differ."""
    ga = np.asarray(a.convert("L"), np.int16)
    gb = np.asarray(b.convert("L"), np.int16)
    if ga.shape != gb.shape:
        raise ValueError(f"size mismatch: {ga.shape} vs {gb.shape}")
    mask = np.abs(ga - gb) > threshold
    sizes = sorted((s for s in _label(mask) if s >= min_size), reverse=True)
    if out_png is not None:
        vis = np.where(mask, 0, 255).astype(np.uint8)
        Image.fromarray(vis, "L").save(out_png)
    return {"components": len(sizes), "sizes": sizes[:max_listed],
            "pixels": int(mask.sum())}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_diff.py -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/diff.py tests/test_lab_diff.py
git commit -m "diff two renders by connected component"
```

---

## Task 10: A job registry with progress

**Files:**
- Create: `brick_icons/lab/jobs.py`
- Test: `tests/test_lab_jobs.py`

Renders run for seconds and a batch for minutes, so the HTTP call starts a job
and returns; the client reads progress from an event stream. One event per
item, with position when the work list is known up front — a silent tool is
indistinguishable from a hung one.

- [ ] **Step 1: Write the failing test**

Create `tests/test_lab_jobs.py`:

```python
import time

from brick_icons.lab import jobs


def _wait(registry, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if registry.get(job_id)["state"] in ("done", "failed", "cancelled"):
            return registry.get(job_id)
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_a_job_runs_and_reports_done():
    r = jobs.Registry()
    job_id = r.start("test", ["a", "b"], lambda item, emit: emit(f"did {item}"))
    assert _wait(r, job_id)["state"] == "done"


def test_progress_carries_position_out_of_total():
    r = jobs.Registry()
    job_id = r.start("test", ["a", "b"], lambda item, emit: emit(item))
    _wait(r, job_id)
    events = r.get(job_id)["events"]
    assert [(e["index"], e["total"]) for e in events] == [(1, 2), (2, 2)]


def test_an_item_failure_is_an_event_not_a_stopped_job():
    def work(item, emit):
        if item == "a":
            raise RuntimeError("boom")
        emit(item)
    r = jobs.Registry()
    job_id = r.start("test", ["a", "b"], work)
    result = _wait(r, job_id)
    assert result["state"] == "done"
    assert result["failed"] == 1
    assert "boom" in result["events"][0]["message"]


def test_cancelling_stops_before_the_next_item():
    started = []

    def work(item, emit):
        started.append(item)
        time.sleep(0.05)
        emit(item)

    r = jobs.Registry()
    job_id = r.start("test", list("abcdefgh"), work)
    time.sleep(0.06)
    r.cancel(job_id)
    result = _wait(r, job_id)
    assert result["state"] == "cancelled"
    assert len(started) < 8


def test_what_work_returns_is_collected():
    r = jobs.Registry()
    job_id = r.start("test", ["a", "b"],
                     lambda item, emit: {"item": item})
    assert _wait(r, job_id)["results"] == [{"item": "a"}, {"item": "b"}]


def test_an_unknown_job_id_reads_as_none():
    assert jobs.Registry().get("nope") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brick_icons.lab.jobs'`

- [ ] **Step 3: Write the implementation**

Create `brick_icons/lab/jobs.py`:

```python
"""Background work, with progress the client can watch.

A per-item failure is an event rather than a raised error: a batch with two bad
parts is a partial success, and stopping the run would throw away the rest.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Callable


class Registry:
    """Jobs this process is running, by id."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, items: list, work: Callable) -> str:
        """Run `work(item, emit)` over `items` on a thread. Whatever `work`
        returns is collected into the job's `results`, which is how a caller
        gets an answer back without closing over the not-yet-assigned id."""
        job_id = uuid.uuid4().hex[:12]
        record = {"id": job_id, "kind": kind, "state": "running",
                  "total": len(items), "done": 0, "failed": 0,
                  "events": [], "results": [], "cancel": threading.Event(),
                  "started": time.time()}
        with self._lock:
            self._jobs[job_id] = record
        threading.Thread(target=self._run, args=(record, items, work),
                         daemon=True).start()
        return job_id

    def _run(self, record: dict, items: list, work: Callable) -> None:
        for index, item in enumerate(items, 1):
            if record["cancel"].is_set():
                record["state"] = "cancelled"
                return

            def emit(message, _i=index, _ok=True):
                record["events"].append({"index": _i, "total": record["total"],
                                         "message": str(message), "ok": _ok})

            try:
                result = work(item, emit)
                if result is not None:
                    record["results"].append(result)
                record["done"] += 1
            except Exception as e:                  # noqa: BLE001
                record["failed"] += 1
                emit(f"{type(e).__name__}: {e}", index, False)
        record["state"] = "done"

    def get(self, job_id: str) -> dict | None:
        record = self._jobs.get(job_id)
        if record is None:
            return None
        return {k: v for k, v in record.items() if k != "cancel"}

    def cancel(self, job_id: str) -> bool:
        record = self._jobs.get(job_id)
        if record is None:
            return False
        record["cancel"].set()
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_jobs.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/jobs.py tests/test_lab_jobs.py
git commit -m "add a job registry with per-item progress"
```

---

## Task 11: Golden status per part

**Files:**
- Create: `brick_icons/lab/goldens_status.py`
- Test: `tests/test_lab_goldens_status.py`

- [ ] **Step 1: Read the frozen hash format**

Run: `head -5 tests/goldens/hashes.txt`
Note the column layout — the next step's parser must match what you see. The
lines are `<combo>__<part>  <hash>` pairs written by
`scripts/freeze-goldens.py`.

- [ ] **Step 2: Write the failing test**

Create `tests/test_lab_goldens_status.py`:

```python
from brick_icons.lab import goldens_status


def test_parses_case_names_into_combo_and_part(tmp_path):
    path = tmp_path / "hashes.txt"
    path.write_text("outline-flat3__3941  abc123\noutline__3941  def456\n")
    rows = goldens_status.frozen(path)
    assert rows["3941"] == {"outline-flat3": "abc123", "outline": "def456"}


def test_ignores_comments_and_blank_lines(tmp_path):
    path = tmp_path / "hashes.txt"
    path.write_text("# a comment\n\noutline__3005  aaa\n")
    assert goldens_status.frozen(path) == {"3005": {"outline": "aaa"}}


def test_a_missing_file_is_empty(tmp_path):
    assert goldens_status.frozen(tmp_path / "nope.txt") == {}


def test_status_reports_a_part_with_no_goldens(tmp_path):
    path = tmp_path / "hashes.txt"
    path.write_text("outline__3005  aaa\n")
    assert goldens_status.status(path, "9999") == {"part": "9999",
                                                   "cases": {}, "known": False}


def test_status_lists_a_parts_cases(tmp_path):
    path = tmp_path / "hashes.txt"
    path.write_text("outline__3005  aaa\noutline-flat3__3005  bbb\n")
    got = goldens_status.status(path, "3005")
    assert got["known"] is True
    assert set(got["cases"]) == {"outline", "outline-flat3"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_goldens_status.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Write the implementation**

Create `brick_icons/lab/goldens_status.py`:

```python
"""What the golden harness has frozen for a part.

Reads only; re-freezing stays with `scripts/freeze-goldens.py`, which is where
a deliberate baseline move belongs.
"""
from __future__ import annotations

from pathlib import Path

DEFAULT_PATH = Path("tests/goldens/hashes.txt")


def frozen(path: Path | str = DEFAULT_PATH) -> dict[str, dict[str, str]]:
    """part -> {combo: hash}, from the frozen hash file."""
    path = Path(path)
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    for line in path.read_text().splitlines():
        text = line.split("#")[0].strip()
        if not text or "__" not in text:
            continue
        case, _, digest = text.partition(" ")
        combo, _, part = case.partition("__")
        out.setdefault(part, {})[combo] = digest.strip()
    return out


def status(path: Path | str, part: str) -> dict:
    """The frozen cases for one part, and whether it has any."""
    cases = frozen(path).get(part, {})
    return {"part": part, "cases": cases, "known": bool(cases)}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_goldens_status.py -v`
Expected: PASS, 5 tests. If a test fails on the column layout, fix the parser
to match the real file rather than editing `hashes.txt`.

- [ ] **Step 6: Commit**

```bash
git add brick_icons/lab/goldens_status.py tests/test_lab_goldens_status.py
git commit -m "read frozen golden hashes per part"
```

---

## Task 12: The FastAPI app — read routes

**Files:**
- Create: `brick_icons/lab/app.py`
- Modify: `pyproject.toml:11-12`
- Test: `tests/test_lab_app.py`

- [ ] **Step 1: Add the optional dependency and install it**

In `pyproject.toml`, under `[project.optional-dependencies]`, add below the
`occt` line:

```toml
lab = ["fastapi>=0.110", "uvicorn>=0.27", "httpx>=0.27"]
```

Run: `.venv/bin/pip install -e '.[lab]'`
Expected: fastapi, uvicorn and httpx install. `httpx` is what
`fastapi.testclient` needs.

- [ ] **Step 2: Write the failing test**

Create `tests/test_lab_app.py`:

```python
import pytest

from fastapi.testclient import TestClient

from brick_icons.lab import app as lab_app


@pytest.fixture
def client(tmp_path):
    return TestClient(lab_app.create_app(cache_root=tmp_path))


def test_schema_route_returns_the_fields(client):
    body = client.get("/api/schema").json()
    keys = {f["key"] for f in body["fields"]}
    assert {"engine", "shading", "shade_style", "angle"} <= keys


def test_lists_route_returns_the_corpus_lists(client):
    body = client.get("/api/lists").json()
    assert any(c["name"] == "specimens" for c in body["lists"])


def test_parts_route_searches(client):
    body = client.get("/api/parts", params={"q": "3941"}).json()
    assert body["results"][0]["id"] == "3941"


def test_parts_route_needs_a_query(client):
    assert client.get("/api/parts", params={"q": ""}).json()["results"] == []


def test_goldens_route_reports_a_part(client):
    body = client.get("/api/goldens", params={"part": "3941"}).json()
    assert body["part"] == "3941"


def test_unknown_route_is_404(client):
    assert client.get("/api/nope").status_code == 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brick_icons.lab.app'`

- [ ] **Step 4: Write the implementation**

Create `brick_icons/lab/app.py`:

```python
"""The lab's HTTP surface.

Routes only: every answer comes from a module that is testable without a
server, and nothing here decides anything about rendering.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from ..config import load_config
from . import cache, corpus, goldens_status, partindex, schema


def create_app(root: Path | str = ".",
               cache_root: Path | str = cache.DEFAULT_ROOT) -> FastAPI:
    root = Path(root)
    app = FastAPI(title="brick-icons lab")
    app.state.root = root
    app.state.cache_root = Path(cache_root)
    app.state.ldraw_dir = load_config(root=str(root)).ldraw_dir
    app.state.index = None

    def index() -> dict:
        if app.state.index is None:
            app.state.index = partindex.build(app.state.ldraw_dir)
        return app.state.index

    @app.get("/api/schema")
    def get_schema():
        return {"fields": schema.config_schema()}

    @app.get("/api/lists")
    def get_lists():
        return {"lists": corpus.lists(root=root)}

    @app.get("/api/parts")
    def get_parts(q: str = Query(""), limit: int = Query(25, le=200)):
        return {"results": partindex.search(index(), q, limit=limit)}

    @app.get("/api/goldens")
    def get_goldens(part: str):
        return goldens_status.status(root / goldens_status.DEFAULT_PATH, part)

    ldraw = app.state.ldraw_dir
    if Path(ldraw).is_dir():
        app.mount("/ldraw", StaticFiles(directory=str(ldraw)), name="ldraw")

    return app
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_app.py -v`
Expected: PASS, 6 tests. The `parts` tests take a few seconds on the first
call, which builds the index.

- [ ] **Step 6: Commit**

```bash
git add brick_icons/lab/app.py pyproject.toml tests/test_lab_app.py
git commit -m "serve the lab's schema, lists, part search and golden status"
```

---

## Task 13: Render, job and artifact routes

**Files:**
- Modify: `brick_icons/lab/app.py`
- Test: `tests/test_lab_app.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lab_app.py`:

```python
import time


def _finish(client, job_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "failed", "cancelled"):
            return body
        time.sleep(0.05)
    raise AssertionError("render did not finish")


def test_render_starts_a_job_and_echoes_the_command(client, ldraw_dir):
    body = client.post("/api/render", json={
        "part": "3005",
        "config": {"fmt": "svg", "shading": "outline"},
    }).json()
    assert body["command"] == "brick-icons 3005 --format svg --shading outline"
    assert body["job"]


def test_a_finished_render_lists_its_artifacts(client, ldraw_dir):
    started = client.post("/api/render", json={
        "part": "3005", "config": {"fmt": "svg", "shading": "outline"},
    }).json()
    done = _finish(client, started["job"])
    assert done["state"] == "done"
    assert "3005.svg" in {a["name"] for a in done["results"][0]["artifacts"]}


def test_an_artifact_is_served_back(client, ldraw_dir):
    started = client.post("/api/render", json={
        "part": "3005", "config": {"fmt": "svg", "shading": "outline"},
    }).json()
    done = _finish(client, started["job"])
    key = done["results"][0]["key"]
    r = client.get(f"/api/artifact/{key}/3005.svg")
    assert r.status_code == 200
    assert r.text.startswith("<svg")


def test_an_artifact_outside_the_cache_is_refused(client):
    r = client.get("/api/artifact/abc123/..%2F..%2Fpyproject.toml")
    assert r.status_code in (400, 404)


def test_an_unknown_config_key_is_a_400(client):
    r = client.post("/api/render", json={"part": "3005",
                                         "config": {"not_a_flag": 1}})
    assert r.status_code == 400


def test_a_job_can_be_cancelled(client, ldraw_dir):
    started = client.post("/api/render", json={
        "part": "3649", "config": {"fmt": "svg", "shading": "outline"},
    }).json()
    assert client.post(f"/api/jobs/{started['job']}/cancel").json()["cancelled"]


def test_an_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_diff_route_compares_two_cached_artifacts(client, tmp_path):
    import numpy as np
    from PIL import Image
    for key, box in (("aaaa1111", None), ("bbbb2222", (10, 10, 20, 20))):
        d = tmp_path / key
        d.mkdir(parents=True)
        a = np.full((64, 64), 255, np.uint8)
        if box:
            x0, y0, x1, y1 = box
            a[y0:y1, x0:x1] = 0
        Image.fromarray(a, "L").save(d / "r.png")
    body = client.get("/api/diff", params={
        "a_key": "aaaa1111", "a_name": "r.png",
        "b_key": "bbbb2222", "b_name": "r.png"}).json()
    assert body["components"] == 1
    assert body["sizes"] == [100]


def test_diff_of_a_missing_artifact_is_404(client):
    r = client.get("/api/diff", params={
        "a_key": "aaaa1111", "a_name": "gone.png",
        "b_key": "bbbb2222", "b_name": "gone.png"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_app.py -k render -v`
Expected: FAIL with 404 — the route does not exist

- [ ] **Step 3: Write the implementation**

In `brick_icons/lab/app.py`, extend the imports:

```python
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel

from . import cache, corpus, defects, diff, goldens_status, jobs, partindex, runner, schema
```

Add above `create_app`:

```python
class RenderRequest(BaseModel):
    part: str
    config: dict = {}
    force: bool = False
```

Inside `create_app`, after `app.state.index = None`, add:

```python
    app.state.jobs = jobs.Registry()
```

And add these routes before the `/ldraw` mount:

```python
    @app.post("/api/render")
    def post_render(req: RenderRequest):
        try:
            argv = schema.to_argv(req.part, req.config)
        except KeyError as e:
            raise HTTPException(400, str(e)) from None

        def work(item, emit):
            result = runner.render(item, root=app.state.cache_root,
                                   force=req.force)
            emit(f"{req.part}: {'cached' if result['cached'] else 'rendered'}")
            if not result["ok"]:
                raise RuntimeError(result["error"])
            return result

        return {"job": app.state.jobs.start("render", [argv], work),
                "argv": argv, "command": " ".join(["brick-icons", *argv])}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        record = app.state.jobs.get(job_id)
        if record is None:
            raise HTTPException(404, "no such job")
        return record

    @app.post("/api/jobs/{job_id}/cancel")
    def post_cancel(job_id: str):
        return {"cancelled": app.state.jobs.cancel(job_id)}

    def _artifact_path(key: str, name: str) -> Path:
        if not key.isalnum() or "/" in name or ".." in name:
            raise HTTPException(400, "bad artifact path")
        return app.state.cache_root / key / name

    @app.get("/api/artifact/{key}/{name}")
    def get_artifact(key: str, name: str):
        path = _artifact_path(key, name)
        if not path.is_file():
            raise HTTPException(404, "no such artifact")
        return FileResponse(path)

    @app.get("/api/diff")
    def get_diff(a_key: str, a_name: str, b_key: str, b_name: str,
                 min_size: int = 4):
        paths = [_artifact_path(a_key, a_name), _artifact_path(b_key, b_name)]
        if not all(p.is_file() for p in paths):
            raise HTTPException(404, "no such artifact")
        try:
            images = [Image.open(p) for p in paths]
            return diff.compare(*images, min_size=min_size)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_app.py -v`
Expected: PASS, 15 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/app.py tests/test_lab_app.py
git commit -m "add render, job and artifact routes"
```

---

## Task 14: Defect and batch routes

**Files:**
- Modify: `brick_icons/lab/app.py`
- Test: `tests/test_lab_app.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lab_app.py`:

```python
DEFECT = {
    "id": "3941-occt-borehole", "part": "3941", "engines": ["occt"],
    "status": "open", "title": "borehole rim not drawn",
    "mark": {"x": 0.42, "y": 0.55, "w": 0.11, "h": 0.09},
    "seen": {"angle": "30,25", "shading": "outline", "shade_style": "flat3"},
    "filed": "2026-08-31", "notes": "",
}


@pytest.fixture
def defect_client(tmp_path):
    return TestClient(lab_app.create_app(cache_root=tmp_path / "cache",
                                         defects_path=tmp_path / "defects.toml"))


def test_defects_start_empty(defect_client):
    assert defect_client.get("/api/defects").json()["defects"] == []


def test_a_posted_defect_comes_back(defect_client):
    assert defect_client.post("/api/defects", json=DEFECT).status_code == 200
    got = defect_client.get("/api/defects").json()["defects"]
    assert got[0]["id"] == DEFECT["id"]
    assert got[0]["mark"]["x"] == 0.42


def test_a_duplicate_defect_is_a_409(defect_client):
    defect_client.post("/api/defects", json=DEFECT)
    assert defect_client.post("/api/defects", json=DEFECT).status_code == 409


def test_a_defect_status_can_be_patched(defect_client):
    defect_client.post("/api/defects", json=DEFECT)
    r = defect_client.patch(f"/api/defects/{DEFECT['id']}",
                            json={"status": "fixed"})
    assert r.json()["status"] == "fixed"


def test_patching_an_unknown_defect_is_404(defect_client):
    assert defect_client.patch("/api/defects/nope",
                               json={"status": "fixed"}).status_code == 404


def test_a_bad_status_is_a_400(defect_client):
    defect_client.post("/api/defects", json=DEFECT)
    r = defect_client.patch(f"/api/defects/{DEFECT['id']}",
                            json={"status": "maybe"})
    assert r.status_code == 400


def test_batch_starts_one_job_for_the_list(client, ldraw_dir):
    body = client.post("/api/batch", json={
        "parts": ["3005", "3024"],
        "config": {"fmt": "svg", "shading": "outline"},
    }).json()
    done = _finish(client, body["job"], timeout=180)
    assert done["total"] == 2
    assert done["done"] == 2
    assert [e["index"] for e in done["events"]] == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_app.py -k defect -v`
Expected: FAIL — `create_app` has no `defects_path` argument

- [ ] **Step 3: Write the implementation**

Change `create_app`'s signature in `brick_icons/lab/app.py` to:

```python
def create_app(root: Path | str = ".",
               cache_root: Path | str = cache.DEFAULT_ROOT,
               defects_path: Path | str | None = None) -> FastAPI:
```

and inside it, beside the other `app.state` lines:

```python
    app.state.defects_path = Path(defects_path) if defects_path else (
        root / defects.DEFAULT_PATH)
```

Add above `create_app`:

```python
class BatchRequest(BaseModel):
    parts: list[str]
    config: dict = {}
    force: bool = False
```

And these routes:

```python
    @app.get("/api/defects")
    def get_defects(part: str | None = None, status: str | None = None):
        rows = defects.load(app.state.defects_path)
        if part:
            rows = [d for d in rows if d["part"] == part]
        if status:
            rows = [d for d in rows if d["status"] == status]
        return {"defects": rows}

    @app.post("/api/defects")
    def post_defect(record: dict):
        try:
            return defects.add(app.state.defects_path, record)
        except ValueError as e:
            code = 409 if "already exists" in str(e) else 400
            raise HTTPException(code, str(e)) from None

    @app.patch("/api/defects/{defect_id}")
    def patch_defect(defect_id: str, changes: dict):
        try:
            return defects.update(app.state.defects_path, defect_id, changes)
        except KeyError:
            raise HTTPException(404, f"no defect {defect_id!r}") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/api/batch")
    def post_batch(req: BatchRequest):
        try:
            argvs = [schema.to_argv(p, req.config) for p in req.parts]
        except KeyError as e:
            raise HTTPException(400, str(e)) from None

        def work(item, emit):
            result = runner.render(item, root=app.state.cache_root,
                                   force=req.force)
            emit(f"{item[0]}: {'cached' if result['cached'] else 'rendered'}")
            if not result["ok"]:
                raise RuntimeError(result["error"])
            return result

        return {"job": app.state.jobs.start("batch", argvs, work),
                "count": len(argvs)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_app.py -v`
Expected: PASS, 22 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/app.py tests/test_lab_app.py
git commit -m "add defect and batch routes"
```

---

## Task 15: The entry point

**Files:**
- Create: `brick_icons/lab/__main__.py`
- Test: manual

- [ ] **Step 1: Write the entry point**

Create `brick_icons/lab/__main__.py`:

```python
"""`python -m brick_icons.lab` — the lab server."""
from __future__ import annotations

import argparse

import uvicorn

from .app import create_app


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="brick-icons-lab")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--root", default=".")
    args = p.parse_args(argv)
    print(f"lab on http://{args.host}:{args.port}", flush=True)
    uvicorn.run(create_app(root=args.root), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Start it and check a route**

Run: `.venv/bin/python -m brick_icons.lab &` then
`curl -s localhost:8765/api/parts?q=3941 | head -c 200`
Expected: JSON whose first result has `"id": "3941"`. Stop the server
afterwards with `kill %1`.

- [ ] **Step 3: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: PASS. This is a plain `pytest`, which skips the drift tests — for the
full gate run `BRICK_GOLDENS=full .venv/bin/pytest`, which takes about 22
minutes and should be unaffected by anything in this plan.

- [ ] **Step 4: Commit**

```bash
git add brick_icons/lab/__main__.py
git commit -m "add the lab server entry point"
```

---

## Task 16: Document the server

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a README section**

Add to `README.md`, after the CLI usage section:

````markdown
## Lab server

A local server for inspecting renders and filing defects:

```sh
pip install -e '.[lab]'
python -m brick_icons.lab       # http://127.0.0.1:8765
```

Its config schema is read off `cli.build_parser()`, and a render runs the argv
it was handed through the CLI's own parse-config-render path — so a flag the
CLI grows appears in the lab with no other change, and the two cannot disagree
about what a parameter does.
````

- [ ] **Step 2: Add the rule to CLAUDE.md**

Add to `CLAUDE.md`:

```markdown
## The lab must not fork the CLI

`brick_icons/lab/` derives its config schema from `cli.build_parser()` and runs
renders through `_config_from_args` + `process_one`. Never add a lab-side
parameter table, and never re-implement a render path there: a parameter the
lab knows and the CLI does not is a bug by construction, and
`tests/test_lab_schema.py` fails on it.
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "document the lab server and its CLI-parity rule"
```

---

## Self-review notes

**Spec coverage.** `/api/schema` (Task 2), argv and parity tests (Tasks 1, 3),
`/api/lists` (Task 6), `/api/parts` (Task 7), `/api/render` and `/api/jobs`
(Tasks 5, 10, 13), `/api/artifact` (Tasks 4, 13), `/api/diff` (Tasks 9, 13),
`/api/defects` (Tasks 8, 14), `/api/goldens` (Tasks 11, 12), `/api/batch`
(Task 14), `/ldraw/*` mount (Task 12), entry point (Task 15).

**Not in this plan, by design.** `/api/reference` (LDView) belongs with the
frontend's reference source, where the lat/long that drives it is decided —
it is planned with the 3D and reference panes. `scripts/defects-to-handoff.py`
is planned with the defect UI, since the shape of a filed defect settles there.

**Known gap this plan leaves open.** `cli._config_from_args` still maps args to
overrides by hand, so a new flag needs a line there as well as its
`add_argument`. `tests/test_lab_schema.py` will not catch that, because the
schema is derived from the parser rather than from the override dict. Closing
it means driving the override dict from the parser too; that is a separate
change with its own risk to the CLI, and it is not required for the lab.
