"""Locator map with the study region filled, linked to a detail map by dashed connectors.

Synthetic regions on a lon/lat grid. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import ConnectionPatch, Patch, PathPatch
from matplotlib.path import Path as MplPath
from matplotlib.ticker import MultipleLocator

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
MID_LAT = 47.0
# Region boundaries run west–east near these latitudes (°N).
SPLITS = (44.0, 49.5)
STUDY = 1  # index of the highlighted region, counted from the south
STUDY_FILL = "#c9785d"
DETAIL_FILL = "#ecc9bc"
MUTED_FILL = "0.9"
BORDER = {"color": "0.55"}
CONNECTOR = {"color": STUDY_FILL, "linestyle": (0, (4, 2))}


def wiggle(rng, n, scale, terms=5):
    """Smooth random offsets: a few sine terms with random phases."""
    t = np.linspace(0, 1, n)
    return sum(scale / k * np.sin(2 * np.pi * k * t + rng.uniform(0, 2 * np.pi))
               for k in range(1, terms + 1))


def country_outline(rng):
    angle = np.linspace(0, 2 * np.pi, 240, endpoint=False)
    radius = 1 + wiggle(rng, angle.size, 0.08, terms=12)
    lon = 22 + 10 * radius * np.cos(angle)
    lat = MID_LAT + 7 * radius * np.sin(angle)
    ring = np.column_stack([lon, lat])
    return MplPath(np.vstack([ring, ring[:1]]), closed=True)  # with closed=True the last vertex only closes the path


def regions(rng):
    """Bands between wiggly parallels; the country outline clips them."""
    lon = np.linspace(5, 40, 80)
    edges = [np.column_stack([lon, np.full_like(lon, 30.0)])]
    for lat in SPLITS:
        edges.append(np.column_stack([lon, lat + wiggle(rng, lon.size, 0.6)]))
    edges.append(np.column_stack([lon, np.full_like(lon, 60.0)]))
    return [MplPath(np.vstack([south, north[::-1]]))
            for south, north in zip(edges[:-1], edges[1:])]


def visible_vertices(band, outline):
    """Vertices of the band clipped to the country."""
    inside_band = outline.vertices[band.contains_points(outline.vertices)]
    inside_country = band.vertices[outline.contains_points(band.vertices)]
    return np.vstack([inside_band, inside_country])


def draw_regions(ax, outline, bands, study_fill):
    clip = PathPatch(outline, transform=ax.transData, facecolor="none")
    for i, band in enumerate(bands):
        fill = study_fill if i == STUDY else MUTED_FILL
        ax.add_patch(PathPatch(band, facecolor=fill, edgecolor="none")).set_clip_path(clip)
    for band in bands[1:]:
        line, = ax.plot(*band.vertices[:80].T, **BORDER)  # the band's southern edge
        line.set_clip_path(clip)
    ax.add_patch(PathPatch(outline, facecolor="none", edgecolor="black"))


def locator(ax, outline, bands):
    draw_regions(ax, outline, bands, STUDY_FILL)
    lon, lat = outline.vertices.T
    ax.set(xlim=(lon.min() - 0.5, lon.max() + 0.5), ylim=(lat.min() - 0.5, lat.max() + 0.5))
    ax.set_aspect(1 / np.cos(np.radians(MID_LAT)))
    ax.set_axis_off()
    ax.set_anchor("W")  # push spare width into the gap the connectors cross


def detail(ax, outline, bands, rng):
    draw_regions(ax, outline, bands, DETAIL_FILL)
    corner = visible_vertices(bands[STUDY], outline)
    lon0, lat0 = corner.min(axis=0)
    lon1, lat1 = corner.max(axis=0)
    candidates = np.column_stack([rng.uniform(lon0, lon1, 400), rng.uniform(lat0, lat1, 400)])
    keep = outline.contains_points(candidates) & bands[STUDY].contains_points(candidates)
    ax.scatter(*candidates[keep][:30].T, s=6, color="black", linewidths=0, zorder=3,
               label="Station")
    ax.set(xlim=(lon0 - 0.5, lon1 + 0.5), ylim=(lat0 - 0.5, lat1 + 0.5))
    ax.set_aspect(1 / np.cos(np.radians(MID_LAT)))
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_locator(MultipleLocator(2))
    ax.grid(color="0.75")  # graticule at the tick positions
    ax.set_axisbelow(False)
    ax.xaxis.set_major_formatter("{x:g}°E")
    ax.yaxis.set_major_formatter("{x:g}°N")
    ax.yaxis.tick_right()
    ax.set_anchor("E")


def key(ax):
    handles = [Patch(facecolor=STUDY_FILL, label="Study region"),
               Patch(facecolor=MUTED_FILL, label="Other regions"),
               plt.Line2D([], [], marker="o", ms=2.5, color="black", lw=0, label="Station")]
    ax.legend(handles=handles, loc="upper left", frameon=False)
    ax.set_axis_off()


def connect(fig, ax_locator, ax_detail, outline, band):
    """Join the region's north-east and south-east tips to the detail map's left corners."""
    vertices = visible_vertices(band, outline)
    north_east = vertices[(vertices[:, 0] + vertices[:, 1]).argmax()]
    south_east = vertices[(vertices[:, 0] - vertices[:, 1]).argmax()]
    for point, y_frac in ((north_east, 1.0), (south_east, 0.0)):
        fig.add_artist(ConnectionPatch(
            xyA=point, coordsA="data", axesA=ax_locator,
            xyB=(0.0, y_frac), coordsB="axes fraction", axesB=ax_detail,
            **CONNECTOR,
        ))


def main():
    rng = np.random.default_rng(7)
    outline = country_outline(rng)
    bands = regions(rng)
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
        fig = plt.figure(figsize=(width_mm * MM, 70 * MM), layout="constrained")
        grid = fig.add_gridspec(2, 2, width_ratios=(1, 2.2), height_ratios=(1, 0.25))
        ax_locator = fig.add_subplot(grid[0, 0])
        ax_detail = fig.add_subplot(grid[:, 1])
        key(fig.add_subplot(grid[1, 0]))
        locator(ax_locator, outline, bands)
        detail(ax_detail, outline, bands, rng)
        connect(fig, ax_locator, ax_detail, outline, bands[STUDY])
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
