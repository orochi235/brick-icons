"""What counts as a part changing when the library is swapped.

A part is its own `.dat` plus every subfile it resolves to, so a hash that
reads only the file named by the id says nothing: the 2026-06 update moved
50950 by subfiling it. And the hash has to ignore what the renderer ignores --
an LDraw update rewrites headers across thousands of files, and a byte hash
turns that into a re-render of the whole library.
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
lh = importlib.import_module("ldraw-hash")

TRI = "3 16 0 0 0 1 0 0 0 1 0"
REF = "1 16 0 0 0 1 0 0 0 1 0 0 0 1 sub.dat"


def tree(tmp_path: Path, part: str, sub: str | None = None) -> Path:
    root = tmp_path / "ldraw"
    (root / "parts").mkdir(parents=True, exist_ok=True)
    (root / "p").mkdir(parents=True, exist_ok=True)
    (root / "parts" / "a.dat").write_text(part)
    if sub is not None:
        (root / "p" / "sub.dat").write_text(sub)
    return root


def hash_of(root: Path, part: str = "a") -> str:
    return lh.build(root)[part]["sha"]


def test_a_subfile_edit_moves_the_part_that_references_it(tmp_path):
    """The whole reason the id's own bytes are not the answer."""
    before = hash_of(tree(tmp_path / "b", f"0 A\n{REF}", f"0 Sub\n{TRI} 0 1"))
    after = hash_of(tree(tmp_path / "a", f"0 A\n{REF}", f"0 Sub\n{TRI} 0 2"))
    assert before != after


def test_a_header_rewrite_does_not(tmp_path):
    plain = hash_of(tree(tmp_path / "b", f"0 A\n{TRI} 0 1"))
    papered = hash_of(tree(
        tmp_path / "a",
        f"0 A\n0 !LDRAW_ORG Part UPDATE 2026-09\n0 !KEYWORDS boat\n{TRI} 0 1"))
    assert plain == papered


def test_a_winding_declaration_does(tmp_path):
    """`0 BFC` is the one type-0 line the renderer reads."""
    ccw = hash_of(tree(tmp_path / "b", f"0 A\n0 BFC CERTIFY CCW\n{TRI} 0 1"))
    cw = hash_of(tree(tmp_path / "a", f"0 A\n0 BFC CERTIFY CW\n{TRI} 0 1"))
    assert ccw != cw


def test_a_reference_that_resolves_nowhere_is_named(tmp_path):
    """2374b and 5241 shipped referencing files the release does not contain,
    and `flatten` drops what it cannot find without a word."""
    rows = lh.build(tree(tmp_path, f"0 A\n{REF}"))
    assert rows["a"]["unresolved"] == ["sub.dat"]


def test_a_reference_the_engine_substitutes_still_counts(tmp_path):
    """`primitives.from_ref` never reads `4-4cyli.dat`, but the naive path
    does -- so the reference is hashed whether or not a file backs it."""
    ref = "1 16 0 0 0 1 0 0 0 1 0 0 0 1 4-4cyli.dat"
    one = hash_of(tree(tmp_path / "b", f"0 A\n{ref}"))
    two = hash_of(tree(tmp_path / "a", f"0 A\n{TRI} 0 1"))
    assert one != two


def test_diff_splits_added_dropped_and_moved(tmp_path):
    old = {"a": {"sha": "1"}, "gone": {"sha": "2"}, "same": {"sha": "3"}}
    new = {"a": {"sha": "9"}, "new": {"sha": "4"}, "same": {"sha": "3"}}
    assert lh.diff(old, new) == {"added": ["new"], "dropped": ["gone"],
                                 "moved": ["a"]}
