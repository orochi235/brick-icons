import json, glob, sys
import numpy as np
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

# Log-spaced bins: the data spans 0.3s to 1038s, so equal-width bins would put
# 90% of parts in the first one.
edges = np.logspace(np.log10(0.3), np.log10(1200), 25)
centers = np.sqrt(edges[:-1] * edges[1:])
width = (edges[1] / edges[0]) ** 0.5

top = max(np.histogram(np.array(v), bins=edges)[0].max() for v in ok.values())

fig, ax = plt.subplots(figsize=(11.5, 6.4), dpi=170)
fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)

for i, engine in enumerate(("naive", "occt")):
    v = np.array(ok.get(engine, []))
    counts, _ = np.histogram(v, bins=edges)
    # Grouped, not overlaid: each bar sits in its own half of the bin with a
    # visible gap, so neither series hides the other.
    lo = centers * width ** (-1 + i * 0.98)
    hi = centers * width ** (-0.02 + i * 0.98)
    ax.bar(lo, counts, width=(hi - lo), align="edge", color=SERIES[engine],
           label=engine, zorder=3, linewidth=0)
    med = float(np.median(v))
    ax.annotate(f"{engine} median {med:.0f}s", xy=(med, top * (1.06 - i * 0.07)),
                xytext=(7, 0), textcoords="offset points",
                color=INK, fontsize=10, va="center")
    ax.plot([med, med], [0, top * (1.05 - i * 0.07)], color=SERIES[engine],
            lw=2, ls=(0, (2, 2)), zorder=4)
    print(f"{engine}: n={len(v)} median={med:.1f}s peak bin={counts.max()}")

ax.axvline(120, color=MUTED, lw=1, ls=(0, (4, 3)), zorder=2)
ax.annotate("120s guard — best-effort: SIGALRM cannot\ninterrupt a long C call, so parts run past it", xy=(120, top * 1.13),
            xytext=(7, 0), textcoords="offset points", color=INK2, fontsize=9.5, va="top")
ax.set_ylim(0, top * 1.22)

ax.set_xscale("log")
ax.set_xlim(0.3, 1200)
ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}s" if x >= 1 else f"{x:g}s"))
ax.set_xticks([0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600, 1200])
ax.set_xlabel("Wall-clock per part (log)", color=INK2, fontsize=10)
ax.set_ylabel("Parts", color=INK2, fontsize=10)
ax.set_title("How long a part takes to render — census run 1",
             color=INK, fontsize=13.5, weight="bold", loc="left", pad=14)
ax.grid(True, which="major", axis="y", color="#e6e5e0", lw=0.8, zorder=0)
ax.set_axisbelow(True)
leg = ax.legend(frameon=False, loc="upper left", fontsize=10.5)
for t in leg.get_texts():
    t.set_color(INK)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
for side in ("left", "bottom"):
    ax.spines[side].set_color("#dedcd6")
ax.tick_params(colors=INK2, labelsize=9.5)
ax.annotate(f"Excludes {len(failed.get('naive', [])):,} naive and {len(failed.get('occt', [])):,} occt parts "
            f"that hit the guard or crashed — they consumed time but produced no render.",
            xy=(0, 0), xytext=(0, -44), textcoords="offset points",
            xycoords="axes fraction", color=INK2, fontsize=9.5)
fig.tight_layout(rect=(0, 0.05, 1, 1))
fig.savefig(sys.argv[1], facecolor=SURFACE)
print("wrote", sys.argv[1])
