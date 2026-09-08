#!/usr/bin/env python3
"""occt against naive on one machine, before and after the occt speedup.

    .venv/bin/python scripts/census-plot-engines.py --out out/engines.png

Only the backfill's rows are occt at HEAD. Job `62bb81bd` ran the pre-fix code
for its whole life, and its rows land in `out/census` beside the backfill's, so
the database cannot tell the two apart -- the HEAD timings are read from
`out/census/backfill/*.jsonl` directly. Both sets ran on studio; naive's rows
are studio's too, so the machine is held constant and only naive's code is
older, by a measured 1.16-1.35x.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

SURFACE, INK, MUTED = "#fcfcfb", "#0b0b0b", "#8d8b85"
NAIVE, OCCT, OCCT_OLD = "#2a78d6", "#eb6834", "#f0b9a0"


def head_timings(backfill: Path) -> dict[str, float]:
    out = {}
    for f in sorted(backfill.glob("*.jsonl")):
        for line in f.read_text(errors="ignore").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("error") is None and r.get("secs") is not None:
                out[r["part"]] = r["secs"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--backfill", default=str(ROOT / "out/census/backfill"))
    ap.add_argument("--out", default=str(ROOT / "out/engines.png"))
    args = ap.parse_args()

    head = head_timings(Path(args.backfill))
    conn = db.connect(args.db)
    pre = {r["part_id"]: r["secs"] for r in conn.execute(
        "SELECT part_id, secs FROM measurements "
        "WHERE run_id=3 AND engine='occt' AND error IS NULL")}
    nai = {r["part_id"]: r["secs"] for r in conn.execute(
        "SELECT part_id, secs FROM measurements "
        "WHERE run_id=1 AND engine='naive' AND error IS NULL")}
    conn.close()

    shared = sorted(p for p in head if p in nai and p in pre)
    print(f"{len(shared)} parts with all three timings", flush=True)

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(13, 5.2), facecolor=SURFACE)
    for a in (ax, bx):
        a.set_facecolor(SURFACE)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)

    for series, color, label in (
            ([pre[p] for p in shared], OCCT_OLD, "occt, pre-fix"),
            ([nai[p] for p in shared], NAIVE, "naive"),
            ([head[p] for p in shared], OCCT, "occt, HEAD")):
        ax.plot(range(len(series)), sorted(series), color=color, lw=2,
                label=f"{label} — {sum(series)/3600:.1f} core-h")
    ax.set_yscale("log")
    ax.set_xlabel("parts, cheapest first")
    ax.set_ylabel("seconds per part")
    ax.set_title(f"Same {len(shared)} parts, same machine", color=INK, loc="left")
    ax.legend(frameon=False)

    ratio = sorted(head[p] / nai[p] for p in shared)
    med = st.median(ratio)
    bx.hist(ratio, bins=60, range=(0, 3), color=OCCT, alpha=.85)
    bx.axvline(1, color=MUTED, lw=1.5, ls="--")
    bx.axvline(med, color=INK, lw=1.5)
    bx.text(med, bx.get_ylim()[1] * .95, f"  median {med:.2f}", color=INK, va="top")
    bx.set_xlabel("occt at HEAD ÷ naive, per part   (<1 = occt faster)")
    bx.set_ylabel("parts")
    bx.set_title("Where occt now wins, and where it does not", color=INK, loc="left")

    fig.tight_layout()
    fig.savefig(args.out, facecolor=SURFACE, dpi=130)
    print(f"wrote {args.out}")
    print(f"occt HEAD {sum(head[p] for p in shared)/3600:.1f} core-h vs "
          f"naive {sum(nai[p] for p in shared)/3600:.1f}; "
          f"{sum(1 for r in ratio if r < 1)} of {len(ratio)} parts faster under occt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
