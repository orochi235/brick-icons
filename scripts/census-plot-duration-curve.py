import json, glob, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#8d8b85"
SERIES = {"naive": "#2a78d6", "occt": "#eb6834"}

ok, failed = {}, {}
for f in glob.glob("out/census-run1/*.jsonl"):
    for line in open(f, errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        s = d.get("secs")
        if s is None:
            continue
        (failed if "error" in d else ok).setdefault(d["engine"], []).append(s)

fig, ax = plt.subplots(figsize=(11, 6.2), dpi=170)
fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)

for engine in ("naive", "occt"):
    v = sorted(ok.get(engine, []))
    if not v:
        continue
    xs = [i / len(v) * 100 for i in range(len(v))]
    ax.plot(xs, v, color=SERIES[engine], lw=2, solid_capstyle="round", zorder=3)
    # Direct label at the curve's end, in ink -- the colored line carries identity.
    ax.annotate(f"{engine}  ({len(v):,} parts)", xy=(100, v[-1]), xytext=(-4, 8),
                textcoords="offset points", ha="right", color=INK, fontsize=10.5, weight="medium")
    p50, p90 = v[len(v) // 2], v[int(len(v) * .9)]
    print(f"{engine}: n={len(v)} p50={p50:.1f}s p90={p90:.1f}s max={v[-1]:.0f}s")

ax.axhline(120, color=MUTED, lw=1, ls=(0, (4, 3)), zorder=2)
ax.annotate("120s guard — arms the geometry phase only,\nso a part can finish well past it",
            xy=(1.5, 120), xytext=(0, 10), textcoords="offset points",
            color=INK2, fontsize=9.5, va="bottom")

nb = sum(len(x) for x in failed.values())
ax.annotate(f"Not shown: {len(failed.get('naive', [])):,} naive and {len(failed.get('occt', [])):,} occt parts "
            f"({nb:,}) hit the guard or crashed and produced nothing.",
            xy=(0, 0), xytext=(0, -46), textcoords="offset points",
            xycoords="axes fraction", color=INK2, fontsize=9.5)

ax.set_yscale("log")
ax.set_ylim(0.25, 1400)
ax.set_xlim(0, 100)
ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:g}s"))
ax.set_xlabel("Parts, slowest last (percentile)", color=INK2, fontsize=10)
ax.set_ylabel("Wall-clock per part", color=INK2, fontsize=10)
ax.set_title("Render time per part — census run 1, parts that produced a measurement",
             color=INK, fontsize=13.5, weight="semibold", loc="left", pad=14)
ax.grid(True, which="major", axis="y", color="#e6e5e0", lw=0.8, zorder=0)
ax.set_axisbelow(True)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
for side in ("left", "bottom"):
    ax.spines[side].set_color("#dedcd6")
ax.tick_params(colors=INK2, labelsize=9.5)
fig.tight_layout(rect=(0, 0.05, 1, 1))
out = sys.argv[1]
fig.savefig(out, facecolor=SURFACE)
print("wrote", out)
