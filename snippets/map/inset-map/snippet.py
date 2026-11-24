"""Station trends on a lon/lat map, with outlying islands in a framed inset map.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm
from matplotlib.lines import Line2D
from matplotlib.path import Path as Outline

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
CMAP = plt.get_cmap("RdBu_r")
LEVELS = np.linspace(-6, 6, 9)  # % per decade
CLASSES = {
    "Decrease": CMAP(0.1),
    "Not significant": "0.72",
    "Increase": CMAP(0.9),
}
MAIN_EXTENT = (4.0, 50.0, 36.0, 56.0)  # lon_min, lon_max, lat_min, lat_max
ISLAND_EXTENT = (46.0, 50.0, 30.0, 35.0)
LAND = {"facecolor": "0.93", "edgecolor": "0.45"}
FRAME = {"edgecolor": "black"}


def blob(lon, lat, radius, seed, n=200):
    """Closed outline with an irregular coast, as (n, 2) lon/lat vertices."""
    rng = np.random.default_rng(seed)
    angle = np.linspace(0, 2 * np.pi, n)
    wobble = sum(rng.uniform(0.02, 0.08) * np.cos(k * angle + rng.uniform(0, 2 * np.pi))
                 for k in range(2, 9))
    r = radius * (1 + wobble)
    return np.column_stack([lon + 1.4 * r * np.cos(angle), lat + r * np.sin(angle)])


def stations_in(outline, count, rng):
    """Random points inside an outline."""
    lo, hi = outline.min(axis=0), outline.max(axis=0)
    points = rng.uniform(lo, hi, size=(count * 3, 2))
    inside = Outline(outline).contains_points(points)
    return points[inside][:count]


def make_data():
    rng = np.random.default_rng(7)
    mainland = blob(30.5, 47.0, 7.2, seed=1)
    islands = [blob(47.0, 33.8, 0.45, seed=2), blob(48.3, 32.6, 0.6, seed=3),
               blob(49.1, 31.2, 0.35, seed=4)]
    points = np.vstack([stations_in(mainland, 420, rng)]
                       + [stations_in(island, 6, rng) for island in islands])
    lon, lat = points.T
    trend = 3 * np.sin((lat - 45) / 3) + 0.15 * (lon - 30) + rng.normal(0, 2.4, len(points))
    standard_error = rng.uniform(0.6, 1.8, len(points))
    significant = np.abs(trend / standard_error) > 2
    return mainland, islands, points, trend, significant


def draw_stations(ax, points, trend, significant, norm):
    lon, lat = points.T
    ax.scatter(lon[~significant], lat[~significant], s=5, marker="^",
               facecolor="none", edgecolor=CLASSES["Not significant"])
    return ax.scatter(lon[significant], lat[significant], c=trend[significant], s=6,
                      cmap=CMAP, norm=norm, edgecolor="none")


def island_inset(ax, islands, points, trend, significant, norm):
    """Separate framed map at the main map's scale; no connectors."""
    x0, x1, y0, y1 = MAIN_EXTENT
    i0, i1, j0, j1 = ISLAND_EXTENT
    # Fractions of the main axes that keep one degree the same length in both maps.
    w, h = (i1 - i0) / (x1 - x0), (j1 - j0) / (y1 - y0)
    axins = ax.inset_axes([0.99 - w, 0.02, w, h])
    for island in islands:
        axins.fill(*island.T, **LAND)
    draw_stations(axins, points, trend, significant, norm)
    axins.set(xlim=(i0, i1), ylim=(j0, j1), xticks=[], yticks=[],
              aspect=ax.get_aspect())
    for spine in axins.spines.values():
        spine.set(**FRAME)


def gaussian_kde(values, grid):
    """Kernel density with Silverman's bandwidth."""
    bandwidth = 1.06 * values.std() * len(values) ** (-1 / 5)
    z = (grid[:, None] - values[None, :]) / bandwidth
    return np.exp(-0.5 * z**2).sum(axis=1) / (len(values) * bandwidth * np.sqrt(2 * np.pi))


def trend_histogram(ax, trend, significant):
    axh = ax.inset_axes([0.08, 0.13, 0.24, 0.32])  # plotting area only; labels fall outside
    bins = np.arange(-10, 10.5, 1.0)
    width = bins[1] - bins[0]
    masks = {
        "Decrease": significant & (trend < 0),
        "Not significant": ~significant,
        "Increase": significant & (trend > 0),
    }
    bottom = np.zeros(len(bins) - 1)
    for name, mask in masks.items():
        share = np.histogram(trend[mask], bins)[0] / len(trend) * 100
        axh.bar(bins[:-1], share, width=width, bottom=bottom, align="edge",
                color=CLASSES[name], linewidth=0)
        bottom += share
    # Scale the density to percent per bin so it sits on the bars.
    grid = np.linspace(bins[0], bins[-1], 300)
    axh.plot(grid, gaussian_kde(trend, grid) * width * 100, color="black")
    places = {"Decrease": (0.02, 0.62, "left"), "Not significant": (0.5, 1.0, "center"),
              "Increase": (0.98, 0.62, "right")}
    for name, (x, y, ha) in places.items():
        share = masks[name].mean() * 100
        axh.text(x, y, f"{name}\n{share:.1f}%", transform=axh.transAxes, ha=ha,
                 va="bottom", color=CLASSES[name], linespacing=1.1)
    axh.set(xlim=(bins[0], bins[-1]), ylim=(0, None), xticks=[-10, 0, 10],
            xlabel="Trend (% per decade)", ylabel="Stations (%)")
    axh.patch.set_alpha(0)
    axh.spines[["top", "right"]].set_visible(False)


def main():
    mainland, islands, points, trend, significant = make_data()
    norm = BoundaryNorm(LEVELS, CMAP.N, extend="both")
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    map_frame = STYLE_DIR / "map.mplstyle"
    if map_frame.is_file():
        sheets.append(map_frame)
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, ax = plt.subplots(figsize=(width_mm * MM, 100 * MM), layout="constrained")
        ax.fill(*mainland.T, **LAND)
        dots = draw_stations(ax, points, trend, significant, norm)
        x0, x1, y0, y1 = MAIN_EXTENT
        ax.set(xlim=(x0, x1), ylim=(y0, y1), aspect=1 / np.cos(np.deg2rad((y0 + y1) / 2)),
               xticks=np.arange(10, 50, 10), yticks=np.arange(40, 56, 5),
               xlabel="Longitude (°E)", ylabel="Latitude (°N)")
        island_inset(ax, islands, points, trend, significant, norm)
        trend_histogram(ax, trend, significant)
        handles = [
            Line2D([], [], marker="o", linestyle="none", color="0.2", markersize=3,
                   label="p < 0.05"),
            Line2D([], [], marker="^", linestyle="none", markerfacecolor="none",
                   markeredgecolor=CLASSES["Not significant"], markersize=3, label="p ≥ 0.05"),
        ]
        ax.legend(handles=handles, loc="upper right", frameon=False)
        fig.colorbar(dots, ax=ax, shrink=0.6, label="Trend (% per decade)")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
