"""Back-to-back bars of the share of gauges with falling and rising flow, by land cover.

Synthetic shares for two flow indices and two regions; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgb
from matplotlib.ticker import FuncFormatter
from matplotlib.transforms import offset_copy

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
LIMIT = 60  # % on each side of zero
COVERS = ("Forest", "Cropland", "Urban")
COLORS = ("C0", "C1", "C2")
# Index -> region -> (% of gauges with falling flow, % with rising flow) per cover.
SHARES = {
    "Annual low flow": {
        "Upland": ((18, 7), (31, 5), (12, 9)),
        "Lowland": ((24, 4), (42, 3), (15, 16)),
    },
    "Annual peak flow": {
        "Upland": ((6, 15), (9, 22), (3, 37)),
        "Lowland": ((8, 11), (12, 19), (2, 48)),
    },
}


def lighter(color, amount=0.55):
    """Mix a color with white; amount=0 keeps it, amount=1 gives white."""
    return tuple(c + (1 - c) * amount for c in to_rgb(color))


def draw_region(ax, region, shares):
    falling, rising = np.array(shares).T
    rows = np.arange(len(COVERS))
    left = ax.barh(rows, -falling, height=0.7, color=[lighter(c) for c in COLORS])
    right = ax.barh(rows, rising, height=0.7, color=COLORS)
    for bars, values in ((left, falling), (right, rising)):
        ax.bar_label(bars, labels=[f"{v:d}" for v in values], padding=2)
    ax.axvline(0, color="black")
    ax.tick_params(axis="y", length=0)
    ax.set_yticks(rows, labels=COVERS)
    ax.invert_yaxis()
    ax.set_title(region, pad=3)


def direction_arrows(ax, fig, below=19):
    """Label each side of zero with an arrow a fixed distance below the axis."""
    line = offset_copy(ax.transAxes, fig=fig, y=-below, units="points")
    for start, end, text, align in ((0.48, 0.02, "Falling flow", "right"),
                                    (0.52, 0.98, "Rising flow", "left")):
        ax.annotate(text, xy=(end, 0), xycoords=line, xytext=(start, 0), textcoords=line,
                    ha=align, va="center", annotation_clip=False,
                    arrowprops={"arrowstyle": "->", "shrinkA": 2})


def draw_index(subfig, index, regions):
    axes = subfig.subplots(len(regions), 1, sharex=True)
    for ax, (region, shares) in zip(axes, regions.items()):
        draw_region(ax, region, shares)
    bottom = axes[-1]
    bottom.set_xlim(-LIMIT, LIMIT)
    bottom.set_xticks(np.arange(-LIMIT, LIMIT + 1, 20))
    bottom.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{abs(x):g}"))
    bottom.set_xlabel("Share of gauges (%)", labelpad=15)
    direction_arrows(bottom, subfig.figure)
    subfig.suptitle(index, fontweight="bold")


def main():
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig = plt.figure(figsize=(width_mm * MM, 70 * MM), layout="constrained")
        for subfig, (index, regions) in zip(fig.subfigures(1, 2, wspace=0.04), SHARES.items()):
            draw_index(subfig, index, regions)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
