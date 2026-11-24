"""Small multiples of radial bar glyphs: one ring per dataset, arc length = signed bias.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Patch, Wedge

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
DATASETS = {"Census grid": "C0", "Night lights": "C1", "Building model": "C2",
            "Mobile data": "C3"}  # outer ring first
REGIONS = (("Andes", 12), ("Sahel", 7), ("Delta", 31), ("Steppe", 4), ("Coast", 18),
           ("Alps", 9), ("Tundra", 2), ("Basin", 15))  # name, number of areas
MISSING = {("Tundra", "Mobile data"), ("Steppe", "Building model")}
LIMIT = 100.0  # |bias| in % that reaches 6 o'clock
HOLE = 0.38  # radius of the center circle; the outer edge is 1
GAP = 0.03  # radial gap between rings
LINE = "0.6"


def biases(rng):
    """Bias (%) per region and dataset, each dataset with its own typical sign."""
    center = np.array([-35, 20, -10, 45])
    values = np.clip(center + rng.normal(0, 30, (len(REGIONS), len(DATASETS))), -98, 98)
    for i, (region, _) in enumerate(REGIONS):
        for j, dataset in enumerate(DATASETS):
            if (region, dataset) in MISSING:
                values[i, j] = np.nan
    return values


def ring_radii():
    """Outer radius and width of each ring, outer ring first."""
    width = (1 - HOLE) / len(DATASETS)
    return [(1 - k * width, width - GAP) for k in range(len(DATASETS))]


def radial_bar(ax, values, name, count):
    ax.add_patch(Circle((0, 0), 1.04, fill=False, edgecolor=LINE))
    ax.plot([0, 0], [-HOLE, -1.04], color=LINE)  # where ±LIMIT meet
    for (outer, width), color, value in zip(ring_radii(), DATASETS.values(), values):
        if np.isnan(value):
            ax.text(0, outer - width / 2, "×", ha="center", va="center", fontsize="small",
                    fontweight="bold")
            continue
        sweep = 180 * min(abs(value), LIMIT) / LIMIT
        # Wedge angles are in degrees anticlockwise from 3 o'clock; 90 is the top.
        start, end = (90 - sweep, 90) if value > 0 else (90, 90 + sweep)
        ax.add_patch(Wedge((0, 0), outer, start, end, width=width, facecolor=color,
                           edgecolor="none"))
    ax.add_patch(Circle((0, 0), HOLE, facecolor="white", edgecolor=LINE))
    ax.text(0, 0.06, name, ha="center", va="center", fontweight="bold", fontsize="small")
    ax.text(0, -0.12, str(count), ha="center", va="center", fontsize="small")
    ax.set(xlim=(-1.1, 1.1), ylim=(-1.1, 1.1), aspect="equal")
    ax.axis("off")


def curved_arrow(ax, radius, start, end, text, text_angle):
    """An arc arrow outside the glyph, from angle start to end (degrees)."""
    angles = np.radians(np.linspace(start, end, 60))
    x, y = radius * np.cos(angles), radius * np.sin(angles)
    ax.plot(x[:-1], y[:-1], color="black")
    ax.annotate("", xy=(x[-1], y[-1]), xytext=(x[-3], y[-3]),
                arrowprops={"arrowstyle": "-|>", "color": "black",
                            "mutation_scale": 6})
    a = np.radians(text_angle)
    rotation = text_angle - 90 if np.cos(a) > 0 else text_angle + 90
    ax.text((radius + 0.1) * np.cos(a), (radius + 0.1) * np.sin(a), text, ha="center",
            va="center", rotation=rotation, rotation_mode="anchor")


def key(ax):
    """An enlarged glyph with every ring drawn as a short arc and labeled."""
    radial_bar(ax, np.full(len(DATASETS), -12.0), "Region", "Areas")
    curved_arrow(ax, 1.16, 80, -60, "Overestimation", 30)
    curved_arrow(ax, 1.16, 100, 240, "Underestimation", 150)
    ax.text(0, 1.2, "0%", ha="center", va="bottom")
    ax.text(-0.04, -1.08, f"−{LIMIT:.0f}%", ha="right", va="top")
    ax.text(0.04, -1.08, f"+{LIMIT:.0f}%", ha="left", va="top")
    ax.set(xlim=(-1.45, 1.45), ylim=(-1.35, 1.45))
    ax.set_title("Bias of population count", fontweight="bold")


def ring_legend(ax):
    """Ring names in their own column, one entry per row so they read in ring order."""
    handles = [Patch(facecolor=color) for color in DATASETS.values()]
    handles.append(Line2D([], [], linestyle="", marker="x", color="black", ms=3))
    ax.legend(handles, [*DATASETS, "No value"], title="Rings, outside to inside",
              loc="center left", frameon=False, handlelength=1.2, alignment="left")
    ax.axis("off")


def main():
    rng = np.random.default_rng(9)
    values = biases(rng)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig = plt.figure(figsize=(width_mm * MM, 82 * MM), layout="constrained")
        grid = fig.add_gridspec(2, 6, width_ratios=(1.9, 0.95, 1, 1, 1, 1))
        key(fig.add_subplot(grid[:, 0]))
        ring_legend(fig.add_subplot(grid[:, 1]))
        for k, ((name, count), row) in enumerate(zip(REGIONS, values)):
            radial_bar(fig.add_subplot(grid[k // 4, 2 + k % 4]), row, name, count)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
