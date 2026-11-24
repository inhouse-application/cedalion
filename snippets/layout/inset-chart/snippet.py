"""Inset chart: a small chart with its own axes inside another panel's plot area.
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
INSET_FONT = "small"
GROUPS = {"Small regions": "C0", "Large regions": "C1"}
INSET_COLOR = "C2"
NORM = Normalize(-0.05, 0.15)
CMAP = plt.get_cmap("viridis")


def wiggle(rng, n, scale, terms=8):
    t = np.linspace(0, 1, n, endpoint=False)
    return sum(scale / k * np.sin(2 * np.pi * k * t + rng.uniform(0, 2 * np.pi))
               for k in range(1, terms + 1))


def small_axes(axins):
    """Smaller text and ticks for an inset."""
    axins.tick_params(labelsize=INSET_FONT, pad=1)
    axins.xaxis.label.set_size(INSET_FONT)
    axins.yaxis.label.set_size(INSET_FONT)
    axins.patch.set_alpha(0)


def line_with_inset(ax, rng):
    size = np.logspace(4, 7.3, 60)
    x = np.log10(size)
    for i, (label, color) in enumerate(GROUPS.items()):
        mean = 0.05 + 0.02 * i + 0.025 * (x - 4) + 0.01 * np.sin(2 * x + i)
        half = 0.006 + 0.004 * (x - 4)
        ax.fill_between(size, mean - half, mean + half, color=color, alpha=0.2, linewidth=0)
        ax.plot(size, mean, color=color, label=label)
    ax.set(xscale="log", xlabel="Size", ylabel="Growth rate (unit)", ylim=(0, 0.2))
    ax.legend(loc="lower right", frameon=False)

    # Inset: x, y, width, height as fractions of the parent axes.
    axins = ax.inset_axes([0.1, 0.62, 0.32, 0.32])
    year = np.arange(1980, 2021, 5)
    slope = 0.02 + 0.0012 * (year - 1980) + rng.normal(0, 0.006, year.size)
    axins.fill_between(year, slope - 0.012, slope + 0.012, color=INSET_COLOR, alpha=0.2,
                       linewidth=0)
    axins.plot(year, slope, color=INSET_COLOR, marker="o", markersize=1.5)
    axins.axhline(0, color="black", linestyle="--")
    axins.set(xlabel="Year", ylabel="Slope", xticks=[1980, 2000, 2020], yticks=[0, 0.05])
    small_axes(axins)


def map_with_inset(ax, rng):
    angle = np.linspace(0, 2 * np.pi, 300, endpoint=False)
    radius = 1 + wiggle(rng, angle.size, 0.1)
    ring = np.column_stack([15 + 18 * radius * np.cos(angle), 48 + 9 * radius * np.sin(angle)])
    land = MplPath(np.vstack([ring, ring[:1]]), closed=True)
    ax.add_patch(PathPatch(land, facecolor="0.9", edgecolor="0.55"))
    candidates = np.column_stack([rng.uniform(-5, 35, 3000), rng.uniform(38, 58, 3000)])
    lon, lat = candidates[land.contains_points(candidates)][:300].T
    value = 0.03 + 0.004 * (lon - 5) + rng.normal(0, 0.02, lon.size)
    ax.scatter(lon, lat, c=value, cmap=CMAP, norm=NORM, s=5,
               edgecolors="white", zorder=3)
    ax.set(xlim=(-6, 52), ylim=(26, 60))
    ax.set_aspect(1 / np.cos(np.deg2rad(48)))
    ax.set_axis_off()

    axins = ax.inset_axes([0.66, 0.06, 0.3, 0.3])
    edges = np.linspace(NORM.vmin, NORM.vmax, 17)
    counts, _, bars = axins.hist(np.clip(value, NORM.vmin, NORM.vmax), bins=edges,
                                 edgecolor="white")
    for bar, low, high in zip(bars, edges[:-1], edges[1:]):
        bar.set_facecolor(CMAP(NORM((low + high) / 2)))
    axins.axvline(np.median(value), color="black", linestyle="--")
    axins.set(xlabel="Value (unit)", ylabel="Cities", xticks=[0, 0.1])
    small_axes(axins)


def main():
    rng = np.random.default_rng(9)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(width_mm * MM, 72 * MM), layout="constrained")
        line_with_inset(ax_a, rng)
        map_with_inset(ax_b, rng)
        for ax, letter in zip((ax_a, ax_b), "ab"):
            ax.text(-0.02, 1.02, letter, transform=ax.transAxes, fontsize="large",
                    fontweight="bold", ha="right", va="bottom")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
