"""Continuous color bars with triangular ends for values beyond the color range.

Synthetic gridded fields; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
REFERENCE = 1.0
HALF_RANGE = 0.5
RAIN_TOP = 1200  # mm; values above it get the over color
OVER_COLOR = "#e8a33d"
COLORBAR = {"location": "bottom", "shrink": 0.8, "aspect": 30, "pad": 0.04,
            "extendfrac": 0.05}


def synthetic_grid(rng):
    x = np.linspace(0, 80, 81)
    y = np.linspace(0, 50, 51)
    xc, yc = np.meshgrid(x[:-1] + 0.5, y[:-1] + 0.5)
    ratio = (REFERENCE + 0.58 * np.sin(xc / 12) * np.cos(yc / 10)
             + rng.normal(0, 0.05, xc.shape))
    rain = 300 + 900 * np.exp(-((xc - 58) ** 2 + (yc - 30) ** 2) / 200) + 8 * yc
    return x, y, ratio, rain


def both_ends(fig, ax, x, y, ratio):
    cmap = plt.get_cmap("RdBu_r")
    norm = Normalize(REFERENCE - HALF_RANGE, REFERENCE + HALF_RANGE)
    mesh = ax.pcolormesh(x, y, ratio, cmap=cmap, norm=norm)
    colorbar = fig.colorbar(mesh, ax=ax, extend="both", **COLORBAR)
    colorbar.set_ticks(np.linspace(norm.vmin, norm.vmax, 5))
    colorbar.set_label("Ratio to baseline")
    # x = 0 and 1 are the ends of the bar body, not the triangle tips.
    for side, text, ha in ((0, "Below baseline", "left"), (1, "Above baseline", "right")):
        colorbar.ax.text(side, 1.25, text, transform=colorbar.ax.transAxes,
                         ha=ha, va="bottom")
    ax.set_title("Both ends", loc="left")


def upper_end(fig, ax, x, y, rain):
    cmap = plt.get_cmap("YlGnBu").with_extremes(over=OVER_COLOR)
    mesh = ax.pcolormesh(x, y, rain, cmap=cmap, vmin=0, vmax=RAIN_TOP)
    colorbar = fig.colorbar(mesh, ax=ax, extend="max", **COLORBAR)
    colorbar.set_label("Annual rainfall (mm)")
    ax.set_title("Upper end only", loc="left")


def main():
    x, y, ratio, rain = synthetic_grid(np.random.default_rng(2))
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 76 * MM),
                                 layout="compressed")
        both_ends(fig, axes[0], x, y, ratio)
        upper_end(fig, axes[1], x, y, rain)
        for ax in axes:
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
