"""Which parts occt.TANGENT_PLANE_GROUPS changes: for each part, how many
coplanar faces follow a tangent plane into its wall's fill. Renders each part
once in the occt slot; prints one line per part as it finishes.

    .venv/bin/python scripts/tangent-plane-affected.py 4079 3001 ...
    .venv/bin/python scripts/tangent-plane-affected.py --from parts.txt
"""
import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from brick_icons import cli, db, occt  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--from", dest="src", help="file of part ids, one per line")
    a = ap.parse_args()
    parts = list(a.parts)
    if a.src:
        parts += [ln.split()[0] for ln in Path(a.src).read_text().splitlines()
                  if ln.strip() and not ln.startswith("#")]
    orig = occt._absorb_tangent_planes
    moved = [0]

    def count(tangent, faces=()):
        before = {id(f): f.get("group") for f in faces}
        planes = {id(p) for p, _ in tangent}
        orig(tangent, faces)
        moved[0] += sum(1 for f in faces if id(f) not in planes
                        and f.get("kind") == "occt-plane"
                        and f.get("group") != before.get(id(f)))

    occt._absorb_tangent_planes = count
    for i, part in enumerate(parts, 1):
        moved[0] = 0
        try:
            with tempfile.TemporaryDirectory() as d:
                args = cli._parse_args(db.canonical_argv(part, "occt"))
                cli.process_one(cli._config_from_args(args), part, Path(d))
            print(f"[{i}/{len(parts)}] {part} {moved[0]}", flush=True)
        except Exception as e:      # one bad part must not sink the survey
            print(f"[{i}/{len(parts)}] {part} ERROR {e}", flush=True)


if __name__ == "__main__":
    main()
