"""Raincloud plot: half-violin, box plot and raw points per category, with counts.
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# Land cover, color, sample size, and log-normal median (mm/h) and spread.
GROUPS = [
    ("Forest", "C0", 64, 42, 0.45),
    ("Grassland", "C1", 118, 24, 0.55),
    ("Cropland", "C2", 205, 15, 0.6),
]
VIOLIN_WIDTH = 0.38  # widest point of every violin, in category units
BOX_WIDTH = 0.12
INNER_BOX_WIDTH = 0.06  # box drawn inside a full violin
JITTER = 0.07  # half-width of the point cloud
OFFSET = 0.22  # distance of the point cloud from the box center


def kernel_density(values, grid):
    """Gaussian kernel density with Silverman's bandwidth."""
    spread = min(values.std(ddof=1), np.subtract(*np.percentile(values, [75, 25])) / 1.34)
    bandwidth = 0.9 * spread * values.size ** (-1 / 5)
    z = (grid[:, None] - values[None, :]) / bandwidth
    return np.exp(-0.5 * z**2).sum(axis=1) / (values.size * bandwidth * np.sqrt(2 * np.pi))


def violin_outline(values):
    """Density on a grid limited to the observed range, scaled to VIOLIN_WIDTH.

    The density is estimated on log10 values to match the log y-axis.
    """
    logs = np.log10(values)
    grid = np.linspace(logs.min(), logs.max(), 200)
    density = kernel_density(logs, grid)
    return 10**grid, VIOLIN_WIDTH * density / density.max()


def draw_box(ax, values, x, color, width, face):
    ax.boxplot(values, positions=[x], widths=width, showfliers=False, patch_artist=True,
               boxprops={"facecolor": face, "edgecolor": color},
               medianprops={"color": color if face == "white" else "white"},
               whiskerprops={"color": color},
               capprops={"color": color}, zorder=3)


def raincloud(ax, samples, rng):
    for x, ((_, color, *_), values) in enumerate(zip(GROUPS, samples)):
        grid, half = violin_outline(values)
        ax.fill_betweenx(grid, x + BOX_WIDTH, x + BOX_WIDTH + half, color=color,
                         alpha=0.8, linewidth=0)
        draw_box(ax, values, x, color, BOX_WIDTH, "white")
        jitter = rng.uniform(-JITTER, JITTER, values.size)
        ax.scatter(x - OFFSET + jitter, values, s=2, color=color, alpha=0.6,
                   linewidths=0)


def violin_with_box(ax, samples):
    for x, ((_, color, *_), values) in enumerate(zip(GROUPS, samples)):
        grid, half = violin_outline(values)
        ax.fill_betweenx(grid, x - half, x + half, color=color, alpha=0.35, linewidth=0)
        draw_box(ax, values, x, color, INNER_BOX_WIDTH, color)


def format_axes(ax, samples):
    """Print each count on a second line under its category name."""
    labels = [f"{name}\n$n$ = {values.size}" for (name, *_), values in zip(GROUPS, samples)]
    ax.set_xticks(range(len(GROUPS)), labels=labels)
    ax.set_xlim(-0.5, len(GROUPS) - 0.5)
    ax.set_yscale("log")
    ticks = [2, 5, 10, 20, 50, 100, 200]
    ax.set_yticks(ticks, labels=[str(tick) for tick in ticks])
    ax.set_ylabel("Infiltration rate (mm/h)")


def main():
    rng = np.random.default_rng(11)
    samples = [rng.lognormal(np.log(median), spread, n)
               for _, _, n, median, spread in GROUPS]
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, sharey=True, figsize=(width_mm * MM, 62 * MM),
                                 gridspec_kw={"width_ratios": [1.5, 1]},
                                 layout="constrained")
        raincloud(axes[0], samples, rng)
        violin_with_box(axes[1], samples)
        for ax, letter in zip(axes, "ab"):
            format_axes(ax, samples)
            ax.annotate(letter, xy=(0, 1), xycoords="axes fraction", xytext=(0, 4),
                        textcoords="offset points", fontweight="bold", fontsize="large")
        axes[1].tick_params(labelleft=False)
        axes[1].set_ylabel("")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
