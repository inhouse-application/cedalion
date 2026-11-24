"""Choropleth map: districts filled by value, unclassed (a) and in classes (b), with hatched districts without data.
Synthetic districts on a lon/lat grid, clipped to a country outline."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib.colors import BoundaryNorm, ListedColormap, Normalize
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path as MplPath

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
CENTER = (20.0, 47.0)  # lon, lat of the country
HALF = (15.0, 6.5)  # half-width and half-height in degrees
GRID = (20, 9)  # district columns and rows before clipping
JITTER = 0.35  # vertex shift as a fraction of the grid spacing
NO_DATA_SHARE = 0.06  # share of districts without data
CMAP = ListedColormap(plt.get_cmap("Blues")(np.linspace(0.15, 1.0, 256)))
LIMITS = (0.0, 0.10)  # color scale of panel a
BREAKS = [0.0, 0.02, 0.04, 0.06, 0.08, 0.10]  # class edges of panel b
BORDER = {"edgecolor": "white"}
OUTLINE = {"facecolor": "none", "edgecolor": "0.3"}
NO_DATA = {"facecolor": "white", "edgecolor": "0.6", "hatch": "//////"}


def wiggle(rng, n, scale, terms=10):
    t = np.linspace(0, 1, n, endpoint=False)
    return sum(scale / k * np.sin(2 * np.pi * k * t + rng.uniform(0, 2 * np.pi))
               for k in range(1, terms + 1))


def country(rng):
    angle = np.linspace(0, 2 * np.pi, 300, endpoint=False)
    radius = 1 + wiggle(rng, angle.size, 0.06, terms=6)
    ring = np.column_stack([CENTER[0] + HALF[0] * radius * np.cos(angle),
                            CENTER[1] + HALF[1] * radius * np.sin(angle)])
    return MplPath(np.vstack([ring, ring[:1]]), closed=True)


def districts(rng, outline):
    """Quadrilaterals from a jittered grid; neighbors share their corners exactly."""
    nx, ny = GRID
    x = np.linspace(CENTER[0] - 1.25 * HALF[0], CENTER[0] + 1.25 * HALF[0], nx + 1)
    y = np.linspace(CENTER[1] - 1.25 * HALF[1], CENTER[1] + 1.25 * HALF[1], ny + 1)
    vx, vy = np.meshgrid(x, y)
    vx += rng.uniform(-JITTER, JITTER, vx.shape) * (x[1] - x[0])
    vy += rng.uniform(-JITTER, JITTER, vy.shape) * (y[1] - y[0])
    polygons = []
    for j in range(ny):
        for i in range(nx):
            corners = [(j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i)]
            polygon = np.array([(vx[c], vy[c]) for c in corners])
            if outline.contains_points(polygon).any():
                polygons.append(polygon)
    return polygons


def district_values(rng, polygons):
    center = np.array([p.mean(axis=0) for p in polygons])
    value = 0.05 + 0.035 * np.sin((center[:, 0] - 12) / 5) * np.cos((center[:, 1] - 44) / 4)
    value += rng.normal(0, 0.008, len(polygons))
    missing = rng.random(len(polygons)) < NO_DATA_SHARE
    return np.clip(value, *LIMITS), missing


def choropleth(ax, polygons, value, missing, outline, norm):
    """Fill each district by value; districts without data are hatched. Returns the mappable."""
    clip = PathPatch(outline, transform=ax.transData, facecolor="none")
    shown = [p for p, m in zip(polygons, missing) if not m]
    filled = PolyCollection(shown, array=value[~missing], cmap=CMAP, norm=norm, **BORDER)
    hatched = PolyCollection([p for p, m in zip(polygons, missing) if m], **NO_DATA)
    for collection in (filled, hatched):
        ax.add_collection(collection)
        collection.set_clip_path(clip)
    ax.add_patch(PathPatch(outline, **OUTLINE))
    lon, lat = outline.vertices.T
    ax.set(xlim=(lon.min() - 0.3, lon.max() + 0.3), ylim=(lat.min() - 0.3, lat.max() + 0.3))
    ax.set_aspect(1 / np.cos(np.deg2rad(CENTER[1])))
    ax.set_axis_off()
    return filled


def main():
    rng = np.random.default_rng(11)
    outline = country(rng)
    polygons = districts(rng, outline)
    value, missing = district_values(rng, polygons)
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
        no_data = Patch(label="No data", **NO_DATA)
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(width_mm * MM, 62 * MM), layout="constrained")

        filled = choropleth(ax_a, polygons, value, missing, outline, Normalize(*LIMITS))
        fig.colorbar(filled, ax=ax_a, location="bottom", shrink=0.55, aspect=25,
                     ticks=BREAKS, label="Value (unit)")

        classes = BoundaryNorm(BREAKS, CMAP.N)
        filled = choropleth(ax_b, polygons, value, missing, outline, classes)
        fig.colorbar(filled, ax=ax_b, location="bottom", shrink=0.55, aspect=25,
                     ticks=BREAKS, spacing="uniform", label="Value (unit)")

        for ax, letter in zip((ax_a, ax_b), "ab"):
            ax.legend(handles=[no_data], loc="lower left", frameon=False, handlelength=1.6,
                      handleheight=1.2)
            ax.text(0, 1, letter, transform=ax.transAxes, fontsize="large", fontweight="bold",
                    ha="left", va="top")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
