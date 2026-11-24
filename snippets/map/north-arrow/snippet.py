"""North arrow placed in axes fraction and sized in millimeters.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, Polygon
from matplotlib.ticker import MultipleLocator
from matplotlib.transforms import Affine2D, ScaledTranslation

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
CORNER = (1.0, 1.0)  # anchor, in axes fraction
OFFSET_MM = (-5.0, -13.0)  # arrow base center relative to the anchor, in millimeters
ARROW_MM = (4.0, 6.0)  # width and height of the arrow, in millimeters
SEA = "#dce8ee"
LAND = "#ece8dc"


def north_arrow(ax, xy=CORNER, offset=OFFSET_MM, size=ARROW_MM):
    """Two half-triangles and an "N" on a pale backing."""
    fig = ax.figure
    # Millimeters -> inches -> pixels, then shift to the anchor in axes fraction.
    trans = (Affine2D().translate(*offset).scale(MM)
             + fig.dpi_scale_trans + ScaledTranslation(*xy, ax.transAxes))
    width, height = size
    ax.add_patch(FancyBboxPatch((-width / 2 - 1, -1), width + 2, height + 5.5,
                                boxstyle="round,pad=0,rounding_size=1", transform=trans,
                                facecolor="white", alpha=0.8, edgecolor="none", zorder=4))
    tip, notch = (0, height), (0, 0.25 * height)
    left, right = (-width / 2, 0), (width / 2, 0)
    for corners, fill in (((tip, left, notch), "0.2"), ((tip, notch, right), "white")):
        ax.add_patch(Polygon(corners, closed=True, transform=trans, facecolor=fill,
                             edgecolor="0.2", zorder=5))
    ax.text(0, height + 0.8, "N", transform=trans, ha="center", va="bottom",
            fontweight="bold", zorder=5)


def coastline(ax, rng, lon_range, lat_range, step):
    """A jittered land blob that fills most of the map, over a sea background."""
    lon_mid, lat_mid = np.mean(lon_range), np.mean(lat_range)
    angle = np.linspace(0, 2 * np.pi, 300)
    t = np.linspace(0, 1, angle.size)
    radius = 1 + sum(0.1 / k * np.sin(2 * np.pi * k * t + rng.uniform(0, 2 * np.pi))
                     for k in range(1, 12))
    lon = lon_mid + 0.42 * np.ptp(lon_range) * radius * np.cos(angle)
    lat = lat_mid + 0.42 * np.ptp(lat_range) * radius * np.sin(angle)
    ax.set_facecolor(SEA)
    ax.fill(lon, lat, facecolor=LAND, edgecolor="0.35")
    ax.set(xlim=lon_range, ylim=lat_range)
    ax.set_aspect(1 / np.cos(np.radians(lat_mid)))
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_locator(MultipleLocator(step))
    ax.xaxis.set_major_formatter("{x:g}°E")
    ax.yaxis.set_major_formatter("{x:g}°N")


def main():
    rng = np.random.default_rng(5)
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
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 70 * MM), layout="constrained",
                                 gridspec_kw={"width_ratios": [6, 1]})
        coastline(axes[0], rng, (4, 26), (50, 56), step=2)
        coastline(axes[1], rng, (8, 14), (38, 50), step=2)
        for ax in axes:
            north_arrow(ax)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
