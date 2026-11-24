"""Point map with marker area for one value and color for another, and a legend of round sizes.

Synthetic river gauges; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
EXTENT = (50.0, 100.0, 20.0, 40.0)  # lon_min, lon_max, lat_min, lat_max
SIZE_PER_UNIT = 0.03  # points² of marker area per km² of catchment
LEGEND_SIZES = [250, 1000, 4000]  # km²; legend_elements drops values outside the data range
LAND = {"color": "0.92", "linewidth": 0}


def coast(lon):
    """Latitude of a wavy southern coastline."""
    return 27 + 2.5 * np.sin((lon - 60) / 4) + 1.5 * np.sin((lon - 60) / 1.7)


def make_gauges(rng, count=240):
    lon = rng.uniform(EXTENT[0] + 1, EXTENT[1] - 1, count * 2)
    lat = rng.uniform(EXTENT[2], EXTENT[3] - 1, count * 2)
    on_land = lat > coast(lon) + 0.5
    lon, lat = lon[on_land][:count], lat[on_land][:count]
    catchment = np.clip(rng.lognormal(np.log(600), 0.9, count), 50, 5000)  # km²
    record = np.clip(rng.normal(35, 15, count), 5, 70).round()  # years
    return lon, lat, catchment, record


def draw_gauges(ax, lon, lat, catchment, record):
    order = np.argsort(catchment)[::-1]  # large first, so small markers stay visible
    return ax.scatter(lon[order], lat[order], s=catchment[order] * SIZE_PER_UNIT,
                      c=record[order], cmap="viridis", vmin=0, vmax=70,
                      edgecolor="white")


def size_legend(ax, points):
    """Legend entries at round catchment areas, drawn at the same scale as the map."""
    handles, labels = points.legend_elements(
        prop="sizes", num=LEGEND_SIZES, func=lambda s: s / SIZE_PER_UNIT,
        fmt="{x:,.0f}", color="0.45", markeredgecolor="white")
    ax.legend(handles, labels, title="Catchment area (km²)", loc="lower left",
              bbox_to_anchor=(0.26, 0.0), frameon=False, labelspacing=1.2,
              borderpad=0.8, handletextpad=1.0)


def main():
    rng = np.random.default_rng(11)
    lon, lat, catchment, record = make_gauges(rng)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, ax = plt.subplots(figsize=(width_mm * MM, 86 * MM), layout="constrained")
        shore = np.linspace(EXTENT[0], EXTENT[1], 400)
        ax.fill_between(shore, coast(shore), EXTENT[3], **LAND)
        points = draw_gauges(ax, lon, lat, catchment, record)
        size_legend(ax, points)
        x0, x1, y0, y1 = EXTENT
        ax.set(xlim=(x0, x1), ylim=(y0, y1), aspect=1 / np.cos(np.deg2rad((y0 + y1) / 2)),
               yticks=np.arange(20, 41, 5), xlabel="Longitude (°E)", ylabel="Latitude (°N)")
        fig.colorbar(points, ax=ax, shrink=0.6, label="Record length (years)")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
