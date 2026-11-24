"""Show a second category as lightness within each series' hue, with a two-part legend.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# Variety and its hue angle in CIE LCh (degrees).
VARIETIES = (("Variety A", 35), ("Variety B", 85), ("Variety C", 200), ("Variety D", 290))
LEVELS = ("25 %", "50 %", "75 %", "100 %")
# CIELAB L* per level, used for every hue
LIGHTNESS = (88, 72, 56, 40)
CHROMA = 45  # chroma of the darkest level; lighter levels get proportionally less
OPACITY = (0.25, 0.5, 0.75, 1.0)  # panel b only
TARGET = (17, 21)  # cm
WIDTH = 0.18  # box width in category units

# sRGB primaries and D65 white point.
RGB_TO_XYZ = np.array([[0.4124, 0.3576, 0.1805],
                       [0.2126, 0.7152, 0.0722],
                       [0.0193, 0.1192, 0.9505]])
WHITE = np.array([0.95047, 1.0, 1.08883])


def lch_to_linear_rgb(lightness, chroma, hue):
    """CIE L*C*h° to linear sRGB; components outside 0–1 are out of gamut."""
    a = chroma * np.cos(np.radians(hue))
    b = chroma * np.sin(np.radians(hue))
    fy = (lightness + 16) / 116
    f = np.array([fy + a / 500, fy, fy - b / 200])
    xyz = np.where(f**3 > 216 / 24389, f**3, (116 * f - 16) * 27 / 24389) * WHITE
    return np.linalg.solve(RGB_TO_XYZ, xyz)


def encode_srgb(linear):
    return np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * linear ** (1 / 2.4) - 0.055)


def level_chroma(lightness):
    """Chroma falling to zero at white, so light shades are pale tints in every hue."""
    return CHROMA * (100 - lightness) / (100 - min(LIGHTNESS))


def shade(hue, lightness, chroma=None):
    """Color at a fixed L*, keeping the hue and lowering chroma until it is in gamut."""
    chroma = level_chroma(lightness) if chroma is None else chroma
    for c in np.linspace(chroma, 0, 46):
        linear = lch_to_linear_rgb(lightness, c, hue)
        if np.all((linear >= 0) & (linear <= 1)):
            return tuple(encode_srgb(linear))
    return (0.5, 0.5, 0.5)  # not reached: chroma 0 is always in gamut


def seedling_heights(rng):
    """Thirty heights (cm) per variety and watering level."""
    base = np.array([14, 11, 16, 12])
    gain = np.array([3.0, 4.5, 2.0, 3.5])
    return [[rng.normal(b + g * j, 1.2 + 0.3 * j, 30) for j in range(len(LEVELS))]
            for b, g in zip(base, gain)]


def grouped_boxes(ax, heights, color_of):
    """Four boxes per variety; color_of(i, j) gives the fill of variety i, level j."""
    offsets = (np.arange(len(LEVELS)) - (len(LEVELS) - 1) / 2) * (WIDTH + 0.02)
    for i, samples in enumerate(heights):
        for j, values in enumerate(samples):
            face = color_of(i, j)
            median = "white" if LIGHTNESS[j] < 60 else "black"
            ax.boxplot(values, positions=[i + offsets[j]], widths=WIDTH, patch_artist=True,
                       boxprops={"facecolor": face, "edgecolor": "0.2"},
                       medianprops={"color": median},
                       whiskerprops={"color": "0.2"},
                       capprops={"linewidth": 0},
                       flierprops={"marker": "o", "markersize": 2, "markerfacecolor": face,
                                   "markeredgecolor": "0.2"},
                       zorder=2)
    ax.axhspan(*TARGET, color="0.88", linewidth=0, zorder=0)
    ax.text(1.01, np.mean(TARGET), "Target\nheight", transform=ax.get_yaxis_transform(),
            ha="left", va="center", color="0.4")
    ax.set_xticks(range(len(VARIETIES)), labels=[name for name, _ in VARIETIES])
    ax.set_xlim(-0.55, len(VARIETIES) - 0.45)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Seedling height (cm)")


def two_part_legend(ax):
    """Hue = variety at a middle lightness; gray ramp at the same L* = watering level."""
    hues = [Patch(facecolor=shade(h, LIGHTNESS[2]), edgecolor="0.2")
            for _, h in VARIETIES]
    grays = [Patch(facecolor=shade(0, L, chroma=0), edgecolor="0.2")
             for L in LIGHTNESS]
    first = ax.legend(hues, [name for name, _ in VARIETIES], title="Variety",
                      loc="center right", bbox_to_anchor=(0.52, 0.5), ncol=4,
                      frameon=False, handlelength=1.4, columnspacing=1.2)
    ax.add_artist(first)
    ax.legend(grays, LEVELS, title="Watering (% of field capacity)",
              loc="center left", bbox_to_anchor=(0.58, 0.5), ncol=4, frameon=False,
              handlelength=1.4, columnspacing=1.2)


def main():
    rng = np.random.default_rng(3)
    heights = seedling_heights(rng)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig = plt.figure(figsize=(width_mm * MM, 72 * MM), layout="constrained")
        grid = fig.add_gridspec(2, 2, height_ratios=[1, 0.13])
        lab = fig.add_subplot(grid[0, 0])
        alpha = fig.add_subplot(grid[0, 1], sharey=lab)
        grouped_boxes(lab, heights,
                      lambda i, j: shade(VARIETIES[i][1], LIGHTNESS[j]))
        grouped_boxes(alpha, heights,
                      lambda i, j: (*shade(VARIETIES[i][1], LIGHTNESS[3]), OPACITY[j]))
        lab.set_title("a  Lightness (fixed L* per level)", loc="left")
        alpha.set_title("b  Opacity (alpha per level)", loc="left")
        legend_ax = fig.add_subplot(grid[1, :])
        legend_ax.axis("off")
        two_part_legend(legend_ax)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
