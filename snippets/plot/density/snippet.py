"""Density plot: Gaussian kernel density, cut at the observed range, with a rug of the values.
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# Climate group, color, number of catchments and beta-distribution parameters.
GROUPS = [
    ("Humid", "C0", 140, 6.0, 4.0),
    ("Temperate", "C1", 210, 3.5, 5.0),
    ("Arid", "C2", 90, 1.3, 9.0),
]
BANDWIDTH_SCALE = 1.0  # multiplies Silverman's bandwidth
RUG_HEIGHT = 0.04  # rug tick length as a fraction of the axes height
X_LABEL = "Runoff ratio"


def kernel_density(values, grid):
    """Gaussian kernel density with Silverman's bandwidth times BANDWIDTH_SCALE."""
    spread = min(values.std(ddof=1), np.subtract(*np.percentile(values, [75, 25])) / 1.34)
    bandwidth = BANDWIDTH_SCALE * 0.9 * spread * values.size ** (-1 / 5)
    z = (grid[:, None] - values[None, :]) / bandwidth
    return np.exp(-0.5 * z**2).sum(axis=1) / (values.size * bandwidth * np.sqrt(2 * np.pi))


def curve(values):
    """Density on a grid from the smallest to the largest value, not beyond."""
    grid = np.linspace(values.min(), values.max(), 300)
    return grid, kernel_density(values, grid)


def rug(ax, values, color):
    """Short ticks at the foot of the axes, one per value."""
    ax.vlines(values, 0, RUG_HEIGHT, transform=ax.get_xaxis_transform(), color=color,
              alpha=0.6)


def single_density(ax, values):
    grid, density = curve(values)
    ax.fill_between(grid, density, color="0.82", linewidth=0)
    ax.plot(grid, density, color="0.1")
    median = np.median(values)
    ax.vlines(median, 0, np.interp(median, grid, density), color="0.1",
              linestyle=(0, (3, 2)))
    ax.annotate(f"Median {median:.2f}", xy=(median, 0.5 * np.interp(median, grid, density)),
                xytext=(3, 0), textcoords="offset points", va="center")
    rug(ax, values, "0.1")
    ax.set_ylabel("Density")


def overlaid_densities(ax, samples):
    for (name, color, n, *_), values in zip(GROUPS, samples):
        grid, density = curve(values)
        ax.fill_between(grid, density, color=color, alpha=0.15, linewidth=0)
        ax.plot(grid, density, color=color, label=f"{name} ($n$ = {n})")
    ax.legend(loc="upper right", frameon=False, handlelength=1.2)


def main():
    rng = np.random.default_rng(9)
    samples = [rng.beta(a, b, n) for _, _, n, a, b in GROUPS]
    everything = np.concatenate(samples)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 60 * MM), layout="constrained")
        single_density(axes[0], everything)
        overlaid_densities(axes[1], samples)
        for ax, letter in zip(axes, "ab"):
            ax.set_xlim(0, 1)
            ax.set_ylim(bottom=0)
            ax.set_xlabel(X_LABEL)
            ax.annotate(letter, xy=(0, 1), xycoords="axes fraction", xytext=(0, 4),
                        textcoords="offset points", fontweight="bold", fontsize="large")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
