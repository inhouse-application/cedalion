"""Reference map: a country split into named regions, with cities, a river and neighboring land.

Synthetic outlines on a lon/lat grid; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path as MplPath
from matplotlib.ticker import FuncFormatter

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
EXTENT = (-128, -64, 22, 52)  # lon_min, lon_max, lat_min, lat_max
CONTINENT = ((-96.0, 39.0), (27.0, 22.0))  # center (lon, lat) and half-size in degrees
NATIONAL = (29.0, 47.5)  # the country lies between wiggly parallels near these latitudes
SPLITS = (-112.0, -101.0, -88.0)  # region borders run north–south near these longitudes
REGIONS = ("West", "Mountain", "Plains", "East")
# Name, lon, lat, label offset in points (dx, dy), horizontal alignment.
CITIES = [
    ("Harbor City", -118.5, 36.0, (3, -2), "left"),
    ("Red Rock", -107.5, 41.0, (3, 0), "left"),
    ("Millbrook", -97.0, 31.0, (3, -3), "left"),
    ("Lakeview", -85.0, 44.0, (3, 0), "left"),
    ("Eastport", -77.5, 41.5, (-3, -3), "right"),
]
CAPITAL = ("Centreville", -94.0, 38.5, (4, 1), "left")
SEA = "#e4edf2"
LAND = "white"
NEIGHBOR = "0.9"
BORDER = {"color": "0.55"}
COAST = {"facecolor": "none", "edgecolor": "0.15"}
NATIONAL_BORDER = {"color": "0.15", "linestyle": (0, (5, 1.5, 1, 1.5))}
RIVER = {"color": "#5b8fb0"}


def wiggle(rng, n, scale, terms=6):
    t = np.linspace(0, 1, n, endpoint=False)
    return sum(scale / k * np.sin(2 * np.pi * k * t + rng.uniform(0, 2 * np.pi))
               for k in range(1, terms + 1))


def blob(rng, center, half, scale=0.1):
    angle = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    radius = 1 + wiggle(rng, angle.size, scale, terms=14)
    ring = np.column_stack([center[0] + half[0] * radius * np.cos(angle),
                            center[1] + half[1] * radius * np.sin(angle)])
    return MplPath(np.vstack([ring, ring[:1]]), closed=True)


def country_band(rng):
    """The country: the land between two wiggly parallels. Returns the band and its two edges."""
    lon = np.linspace(EXTENT[0] - 5, EXTENT[1] + 5, 120)
    south, north = (np.column_stack([lon, lat + wiggle(rng, lon.size, 0.8)]) for lat in NATIONAL)
    return MplPath(np.vstack([south, north[::-1]])), (south, north)


def region_bands(rng):
    """Bands between wiggly meridians; the country outline clips them."""
    lat = np.linspace(EXTENT[2] - 5, EXTENT[3] + 5, 60)
    edges = [np.column_stack([np.full_like(lat, EXTENT[0] - 5), lat])]
    for lon in SPLITS:
        edges.append(np.column_stack([lon + wiggle(rng, lat.size, 0.8), lat]))
    edges.append(np.column_stack([np.full_like(lat, EXTENT[1] + 5), lat]))
    return [MplPath(np.vstack([west, east[::-1]])) for west, east in zip(edges[:-1], edges[1:])]


def river(rng):
    lat = np.linspace(56.0, 15.0, 120)
    lon = -90.5 + 1.2 * np.sin((lat - 30) / 3) + wiggle(rng, lat.size, 0.3)
    return lon, lat


def degrees(positive, negative):
    def label(value, _):
        return f"{abs(value):g}°{positive if value > 0 else negative}" if value else "0°"
    return FuncFormatter(label)


def place(ax, name, lon, lat, offset, ha, marker, size):
    ax.plot(lon, lat, linestyle="none", marker=marker, markersize=size, color="black",
            markeredgecolor="white", zorder=4)
    halo = [pe.withStroke(linewidth=plt.rcParams["lines.linewidth"], foreground="white")]
    ax.annotate(name, (lon, lat), xytext=offset, textcoords="offset points", ha=ha,
                va="center", path_effects=halo, zorder=5)


def reference_map(ax, continent, country, national_edges, bands, river_line):
    ax.set_facecolor(SEA)
    # Neighboring countries: the whole continent in gray; the country is painted over it.
    ax.add_patch(PathPatch(continent, facecolor=NEIGHBOR, edgecolor="none"))
    on_land = PathPatch(continent, transform=ax.transData, facecolor="none")
    ax.add_patch(PathPatch(country, facecolor=LAND, edgecolor="none")).set_clip_path(on_land)
    in_country = PathPatch(country, transform=ax.transData, facecolor="none")
    lon = np.linspace(EXTENT[0], EXTENT[1], 400)
    label_row = np.column_stack([lon, np.full_like(lon, 37.0)])
    for band, name in zip(bands, REGIONS):
        line, = ax.plot(*band.vertices[:60].T, lw=0.5 * plt.rcParams["lines.linewidth"], **BORDER)  # the band's western edge
        line.set_clip_path(in_country)
        # Label at the middle of the band's part inside the country.
        inside = band.contains_points(label_row) & continent.contains_points(label_row)
        ax.text(lon[inside].mean(), 37.0, name, ha="center", va="center", color="0.35",
                fontstyle="italic")
    river, = ax.plot(*river_line, **RIVER, zorder=2)
    river.set_clip_path(on_land)
    for edge in national_edges:
        line, = ax.plot(*edge.T, **NATIONAL_BORDER, zorder=3)
        line.set_clip_path(on_land)
    ax.add_patch(PathPatch(continent, **COAST, zorder=3))
    for city in CITIES:
        place(ax, *city, marker="o", size=3)
    place(ax, *CAPITAL, marker="*", size=6)
    ax.set(xlim=EXTENT[:2], ylim=EXTENT[2:], xticks=np.arange(-120, -64, 10),
           yticks=np.arange(25, 51, 5))
    ax.set_aspect(1 / np.cos(np.deg2rad(np.mean(EXTENT[2:]))))
    ax.xaxis.set_major_formatter(degrees("E", "W"))
    ax.yaxis.set_major_formatter(degrees("N", "S"))


def key(ax):
    handles = [
        Line2D([], [], linestyle="none", marker="*", markersize=6, color="black", label="Capital"),
        Line2D([], [], linestyle="none", marker="o", markersize=3, color="black", label="City"),
        Line2D([], [], **RIVER, label="River"),
        Line2D([], [], lw=0.5 * plt.rcParams["lines.linewidth"], **BORDER, label="Region border"),
        Line2D([], [], **NATIONAL_BORDER, label="National border"),
        Line2D([], [], color=COAST["edgecolor"], lw=plt.rcParams["patch.linewidth"], label="Coastline"),
        Patch(facecolor=NEIGHBOR, label="Neighboring country"),
        Patch(facecolor=SEA, label="Sea"),
    ]
    ax.legend(handles=handles, loc="center left", frameon=False)
    ax.set_axis_off()


def main():
    rng = np.random.default_rng(2)
    continent = blob(rng, *CONTINENT)
    country, national_edges = country_band(rng)
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
        fig, (ax_map, ax_key) = plt.subplots(1, 2, figsize=(width_mm * MM, 75 * MM),
                                             width_ratios=(5, 1), layout="constrained")
        reference_map(ax_map, continent, country, national_edges, region_bands(rng), river(rng))
        key(ax_key)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
