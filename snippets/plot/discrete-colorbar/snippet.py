"""Color bars with class breaks: diverging with open ends, and twelve months.
Synthetic gridded changes in growing-season length and month of peak runoff."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap, from_levels_and_colors

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# Symmetric about zero; values beyond the outer breaks go to the end triangles.
BREAKS = np.array([-25, -15, -5, 5, 15, 25])
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def synthetic_grid():
    """Return grid edges and two fields on an 80 x 60 cell region."""
    x = np.linspace(0, 80, 81)
    y = np.linspace(0, 60, 61)
    xc, yc = np.meshgrid(x[:-1] + 0.5, y[:-1] + 0.5)
    change = (32 * np.sin(xc / 14) * np.cos(yc / 18)
              + 10 * np.cos((xc + yc) / 9))
    angle = np.arctan2(yc - 32, xc - 38) + 0.5 * np.sin(xc / 11)
    peak_month = 1 + np.floor(12 * (angle / (2 * np.pi) % 1)).astype(int)
    return x, y, change, peak_month


def diverging_classes(fig, ax, x, y, change):
    # One color per class plus one for each open end: len(BREAKS) + 1.
    colors = plt.get_cmap("RdBu_r")(np.linspace(0, 1, len(BREAKS) + 1))
    cmap, norm = from_levels_and_colors(BREAKS, colors, extend="both")
    mesh = ax.pcolormesh(x, y, change, cmap=cmap, norm=norm)
    colorbar = fig.colorbar(mesh, ax=ax, location="bottom", shrink=0.8,
                            aspect=30, pad=0.04)
    colorbar.set_ticks(BREAKS)
    colorbar.minorticks_off()
    colorbar.set_label("Change in growing-season length (days)")
    ax.set_title("Diverging classes", loc="left")


def month_classes(fig, ax, x, y, peak_month):
    cmap = ListedColormap(plt.get_cmap("twilight")(np.arange(12) / 12))
    norm = BoundaryNorm(np.arange(0.5, 13), cmap.N)  # class edges at half-months
    mesh = ax.pcolormesh(x, y, peak_month, cmap=cmap, norm=norm)
    colorbar = fig.colorbar(mesh, ax=ax, location="bottom", shrink=0.8,
                            aspect=30, pad=0.04)
    colorbar.set_ticks(np.arange(1, 13), labels=MONTHS)  # class centers
    colorbar.ax.tick_params(which="both", length=0)
    colorbar.set_label("Month of peak runoff")
    ax.set_title("Month classes", loc="left")


def main():
    x, y, change, peak_month = synthetic_grid()
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 80 * MM),
                                 layout="constrained")
        diverging_classes(fig, axes[0], x, y, change)
        month_classes(fig, axes[1], x, y, peak_month)
        for ax in axes:
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
