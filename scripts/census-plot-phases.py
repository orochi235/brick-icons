import json, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
PHASES = [("render", "#2a78d6", "render — hidden-line + SVG"),
          ("truth_mask", "#eb6834", "truth_mask — reference geometry"),
          ("compare", "#1baf7a", "compare — distance transform"),
          ("rasterize", "#eda100", "rasterize — resvg + load")]

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
rows.sort(key=lambda r: r["total"])
x = np.array([r["total"] for r in rows])
shares = np.array([[r[k] / r["total"] * 100 for r in rows] for k, _, _ in PHASES])

fig, ax = plt.subplots(figsize=(12.6, 6.4), dpi=170)
fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)
ax.stackplot(x, shares, colors=[c for _, c, _ in PHASES], zorder=3,
             edgecolor=SURFACE, linewidth=0.6)

# A legend rather than in-band labels: three of the four bands are too thin at
# the right of the plot to hold text, and stacking order is the reading order.
from matplotlib.patches import Patch
handles = [Patch(facecolor=c, label=lab) for _, c, lab in reversed(PHASES)]
leg = ax.legend(handles=handles, frameon=False, loc="center left",
                bbox_to_anchor=(1.01, 0.5), fontsize=10.5, handlelength=1.4,
                handleheight=1.1, labelspacing=0.8)
for t in leg.get_texts():
    t.set_color(INK)

ax.set_xscale("log")
ax.set_xlim(x.min(), x.max())
ax.set_ylim(0, 100)
ax.set_xticks([1, 2, 5, 10, 30, 60, 120, 200])
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}s"))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}%"))
ax.set_xlabel("Total wall-clock for the part (log)", color=INK2, fontsize=10)
ax.set_ylabel("Share of that part's time", color=INK2, fontsize=10)
ax.set_title("Where a part's time goes, by how long it takes — naive engine, 32 sampled parts",
             color=INK, fontsize=13.5, weight="bold", loc="left", pad=14)
tot = sum(r["total"] for r in rows)
ax.annotate("Across every part measured: render 96.1%, truth_mask 3.0%, compare 0.6%, rasterize 0.3%.\n"
            "A part under 2s is mostly fixed overhead; past 10s it is almost entirely the renderer.",
            xy=(0, 0), xytext=(0, -42), textcoords="offset points",
            xycoords="axes fraction", color=INK2, fontsize=9.5, va="top")
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
for side in ("left", "bottom"):
    ax.spines[side].set_color("#dedcd6")
ax.tick_params(colors=INK2, labelsize=9.5)
fig.tight_layout(rect=(0, 0.08, 1, 1))
fig.savefig(sys.argv[2], facecolor=SURFACE)
for k, _, _ in PHASES:
    print(f"{k}: {sum(r[k] for r in rows)/tot*100:.1f}%")
print("wrote", sys.argv[2])
