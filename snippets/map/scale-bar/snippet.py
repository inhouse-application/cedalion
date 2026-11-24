"""Alternating-segment scale bars on lon/lat maps at three latitudes.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from matplotlib.ticker import MultipleLocator
from matplotlib.transforms import blended_transform_factory

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
EARTH_RADIUS_KM = 6371.0
CENTER_LATS = (5.0, 45.0, 65.0)  # °N
LON_SPAN = 1.6  # degrees of longitude
BAR_KM = 40
SEGMENTS = 4
BAR_XY = (0.06, 0.07)  # lower-left corner of the bar, in axes fraction
BAR_HEIGHT = 0.025  # axes fraction


def km_per_degree_lon(lat):
    """Length of one degree of longitude on a sphere; it shrinks with cos(latitude)."""
    return np.pi / 180 * EARTH_RADIUS_KM * np.cos(np.radians(lat))


def km_per_degree_lat():
    return np.pi / 180 * EARTH_RADIUS_KM


def wiggle(rng, n, scale, terms=8):
    t = np.linspace(0, 1, n)
    return sum(scale / k * np.sin(2 * np.pi * k * t + rng.uniform(0, 2 * np.pi))
               for k in range(1, terms + 1))


def catchment(ax, rng, lon0, lat0, radius_km):
    """A jittered blob of the same size in kilometers at any latitude."""
    angle = np.linspace(0, 2 * np.pi, 200)
    radius = radius_km * (1 + wiggle(rng, angle.size, 0.12))
    lon = lon0 + radius * np.cos(angle) / km_per_degree_lon(lat0)
    lat = lat0 + radius * np.sin(angle) / km_per_degree_lat()
    ax.fill(lon, lat, facecolor="#cfdccf", edgecolor="#4f6b53")


def scale_bar(ax, length_km, segments, xy, height):
    """Draw alternating segments; x in data (degrees), y in axes fraction."""
    trans = blended_transform_factory(ax.transData, ax.transAxes)
    (lon_min, lon_max), (lat_min, lat_max) = ax.get_xlim(), ax.get_ylim()
    x0 = lon_min + xy[0] * (lon_max - lon_min)
    bar_lat = lat_min + xy[1] * (lat_max - lat_min)  # the bar is true at this latitude only
    step_deg = length_km / segments / km_per_degree_lon(bar_lat)
    for i in range(segments):
        ax.add_patch(Rectangle((x0 + i * step_deg, xy[1]), step_deg, height,
                               transform=trans, facecolor="black" if i % 2 == 0 else "white",
                               edgecolor="black", zorder=4))
    for i in (0, segments // 2, segments):
        ax.text(x0 + i * step_deg, xy[1] + height, f"{length_km * i / segments:g}",
                transform=trans, ha="center", va="bottom", zorder=4)
    ax.annotate("km", (x0 + segments * step_deg, xy[1] + height / 2), xycoords=trans,
                xytext=(2, 0), textcoords="offset points", ha="left", va="center")


def draw_map(ax, rng, center_lat):
    lon0 = 20.0
    # Same distance in kilometers north–south as east–west.
    lat_span = LON_SPAN * km_per_degree_lon(center_lat) / km_per_degree_lat()
    ax.set(xlim=(lon0 - LON_SPAN / 2, lon0 + LON_SPAN / 2),
           ylim=(center_lat - lat_span / 2, center_lat + lat_span / 2))
    ax.set_aspect(1 / np.cos(np.radians(center_lat)))
    catchment(ax, rng, lon0 + 0.1 * LON_SPAN, center_lat + 0.1 * lat_span, BAR_KM / 2)
    scale_bar(ax, BAR_KM, SEGMENTS, BAR_XY, BAR_HEIGHT)
    ax.xaxis.set_major_locator(MultipleLocator(0.5))
    ax.xaxis.set_major_formatter("{x:g}°E")
    ax.yaxis.set_major_formatter("{x:g}°N")
    ax.set_title(f"Center {center_lat:g}°N: 1° longitude = "
                 f"{km_per_degree_lon(center_lat):.0f} km", loc="left")


def main():
    rng = np.random.default_rng(11)
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
        fig, axes = plt.subplots(1, len(CENTER_LATS), figsize=(width_mm * MM, 66 * MM),
                                 layout="constrained")
        for ax, lat in zip(axes, CENTER_LATS):
            draw_map(ax, rng, lat)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
