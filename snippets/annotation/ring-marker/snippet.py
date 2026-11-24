"""Ring the points that meet a stated condition and key the ring in a legend.
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.legend_handler import HandlerTuple
from matplotlib.lines import Line2D

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
LIMIT = 50  # mg/L
CMAP = "BuPu"
VMIN, VMAX = 0, 60
RING_COLOR = "#f2a900"
DOT_AREA = 14  # points²
RING_AREA = 60  # points²


def synthetic_sites(rng):
    xy = rng.uniform((2, 2), (198, 88), (420, 2))
    hotspot = (np.exp(-((xy[:, 0] - 140) ** 2 + (xy[:, 1] - 45) ** 2) / 300)
               + 0.8 * np.exp(-((xy[:, 0] - 45) ** 2 + (xy[:, 1] - 25) ** 2) / 150))
    nitrate = 12 + 44 * hotspot + rng.gamma(2, 4, len(xy))
    return xy, nitrate


def ringed_points(fig, ax, xy, nitrate):
    ring_width = plt.rcParams["lines.linewidth"]
    dot_edge = 0.5 * plt.rcParams["axes.linewidth"]
    points = ax.scatter(*xy.T, c=nitrate, s=DOT_AREA, cmap=CMAP, vmin=VMIN, vmax=VMAX,
                        edgecolors="0.4", linewidths=dot_edge, zorder=2)
    above = nitrate > LIMIT
    # Draw order: dots, then rings, then the ringed dots again on top.
    ax.scatter(*xy[above].T, s=RING_AREA, facecolors="none", edgecolors=RING_COLOR,
               linewidths=ring_width, zorder=3)
    ax.scatter(*xy[above].T, c=nitrate[above], s=DOT_AREA, cmap=CMAP, vmin=VMIN,
               vmax=VMAX, edgecolors="0.4", linewidths=dot_edge, zorder=4)
    # ndivide=1 overlays ring and dot in one key. markersize is a diameter in points,
    # scatter s an area in points², hence the square roots.
    ring = Line2D([], [], ls="none", marker="o", markersize=np.sqrt(RING_AREA),
                  markerfacecolor="none", markeredgecolor=RING_COLOR,
                  markeredgewidth=ring_width)
    dot = Line2D([], [], ls="none", marker="o", markersize=np.sqrt(DOT_AREA),
                 markerfacecolor=points.cmap(points.norm(LIMIT + 5)),
                 markeredgecolor="0.4", markeredgewidth=dot_edge)
    ax.legend([(ring, dot)], [f"Sites with nitrate > {LIMIT} mg/L"],
              handler_map={tuple: HandlerTuple(ndivide=1)}, loc="upper left",
              bbox_to_anchor=(0, -0.01), frameon=False)
    colorbar = fig.colorbar(points, ax=ax, shrink=0.8, aspect=25, pad=0.02)
    colorbar.set_label("Nitrate (mg/L)")
    ax.set(xlim=(0, 200), ylim=(0, 90), aspect="equal", xticks=[], yticks=[])


def main():
    xy, nitrate = synthetic_sites(np.random.default_rng(21))
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, ax = plt.subplots(figsize=(width_mm * MM, 86 * MM), layout="constrained")
        ringed_points(fig, ax, xy, nitrate)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
