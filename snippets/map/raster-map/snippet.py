"""Raster map: a gridded field drawn cell by cell under coastlines, with missing cells (a) and a land mask (b).
Synthetic data on a regular lon/lat grid."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path as MplPath
from matplotlib.ticker import FuncFormatter

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
EXTENT = (100, 150, 10, 50)  # lon_min, lon_max, lat_min, lat_max
CELL = 0.25  # grid spacing in degrees
LON_EDGES = np.arange(EXTENT[0], EXTENT[1] + CELL / 2, CELL)
LAT_EDGES = np.arange(EXTENT[2], EXTENT[3] + CELL / 2, CELL)
LON = (LON_EDGES[:-1] + LON_EDGES[1:]) / 2  # cell centers
LAT = (LAT_EDGES[:-1] + LAT_EDGES[1:]) / 2
# Land masses: center lon, center lat, half-width and half-height in degrees.
LANDS = [(112, 33, 15, 17), (138, 37, 4, 9), (122, 15, 3, 4)]
COAST = {"facecolor": "none", "edgecolor": "0.25"}
NO_DATA = "0.82"
SWATH_SPACING, SWATH_GAP = 16.0, 2.0  # degrees of longitude between gaps, and gap width
NORM = Normalize(0, 1.8)  # one scale for both panels
CMAP = "YlOrRd"
TICKS = {"xticks": np.arange(100, 151, 10), "yticks": np.arange(10, 51, 10)}


def wiggle(rng, n, scale, terms=10):
    t = np.linspace(0, 1, n, endpoint=False)
    return sum(scale / k * np.sin(2 * np.pi * k * t + rng.uniform(0, 2 * np.pi))
               for k in range(1, terms + 1))


def land_paths(rng):
    paths = []
    for lon, lat, rx, ry in LANDS:
        angle = np.linspace(0, 2 * np.pi, 300, endpoint=False)
        radius = 1 + wiggle(rng, angle.size, 0.12)
        ring = np.column_stack([lon + rx * radius * np.cos(angle),
                                lat + ry * radius * np.sin(angle)])
        paths.append(MplPath(np.vstack([ring, ring[:1]]), closed=True))
    return paths


def field(rng):
    """Smooth bumps plus cell noise, shape (lat, lon)."""
    lon2d, lat2d = np.meshgrid(LON, LAT)
    value = 0.3 + 0.01 * (50 - lat2d)
    for amp, x, y, s in zip(rng.uniform(0.4, 1.2, 10), rng.uniform(102, 130, 10),
                            rng.uniform(20, 45, 10), rng.uniform(1.5, 4.0, 10)):
        value += amp * np.exp(-((lon2d - x) ** 2 + (lat2d - y) ** 2) / (2 * s**2))
    return value + rng.normal(0, 0.05, value.shape)


def swath_gaps():
    """Slanted bands without data, as left between satellite overpasses."""
    lon2d, lat2d = np.meshgrid(LON, LAT)
    along = lon2d - 0.25 * lat2d  # constant along a slanted band
    return (along % SWATH_SPACING) < SWATH_GAP


def land_mask(lands):
    """True for cells whose center lies on land."""
    lon2d, lat2d = np.meshgrid(LON, LAT)
    centers = np.column_stack([lon2d.ravel(), lat2d.ravel()])
    inside = np.any([path.contains_points(centers) for path in lands], axis=0)
    return inside.reshape(lon2d.shape)


def degrees(positive, negative):
    def label(value, _):
        if value == 0:
            return "0°"
        return f"{abs(value):g}°{positive if value > 0 else negative}"
    return FuncFormatter(label)


def raster_map(ax, values, lands, bad_color="white"):
    """Draw a masked (lat, lon) array cell by cell, then the coastlines on top."""
    cmap = plt.get_cmap(CMAP).with_extremes(bad=bad_color)
    mesh = ax.pcolormesh(LON_EDGES, LAT_EDGES, values, cmap=cmap, norm=NORM,
                         shading="flat", rasterized=True)
    for path in lands:
        ax.add_patch(PathPatch(path, **COAST))
    ax.set(xlim=EXTENT[:2], ylim=EXTENT[2:], **TICKS)
    ax.set_aspect(1 / np.cos(np.deg2rad(np.mean(EXTENT[2:]))))
    ax.xaxis.set_major_formatter(degrees("E", "W"))
    ax.yaxis.set_major_formatter(degrees("N", "S"))
    return mesh


def main():
    rng = np.random.default_rng(5)
    lands = land_paths(rng)
    values = field(rng)
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
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(width_mm * MM, 78 * MM), layout="constrained")
        mesh = raster_map(ax_a, np.ma.masked_where(swath_gaps(), values), lands,
                          bad_color=NO_DATA)
        ax_a.legend(handles=[Patch(facecolor=NO_DATA, label="No data")], loc="lower right",
                    frameon=True, facecolor="white", edgecolor="none", framealpha=1,
                    handlelength=1.2, borderaxespad=0.6)
        raster_map(ax_b, np.ma.masked_where(~land_mask(lands), values), lands)
        ax_b.tick_params(labelleft=False)
        fig.colorbar(mesh, ax=[ax_a, ax_b], shrink=0.8, aspect=25, extend="max",
                     label="Value (unit)")
        for ax, letter in zip((ax_a, ax_b), "ab"):
            ax.text(-0.02, 1.02, letter, transform=ax.transAxes, fontsize="large",
                    fontweight="bold", ha="right", va="bottom")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
