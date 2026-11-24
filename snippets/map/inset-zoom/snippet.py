"""Overview map with a zoomed detail: inset (a), separate panel (b, c), circular inset (d).
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, ConnectionPatch, Rectangle

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"

LON = np.linspace(100.0, 140.0, 400)
LAT = np.linspace(20.0, 50.0, 300)
lon2d, lat2d = np.meshgrid(LON, LAT)
rng = np.random.default_rng(0)
FIELD = sum(
    a * np.exp(-((lon2d - x) ** 2 + (lat2d - y) ** 2) / (2 * s**2))
    for a, x, y, s in zip(rng.uniform(0.5, 1.5, 12), rng.uniform(102, 138, 12),
                          rng.uniform(22, 48, 12), rng.uniform(1.0, 4.0, 12))
)
EXTENT = (LON[0], LON[-1], LAT[0], LAT[-1])

# Region to zoom into: (lon_min, lon_max, lat_min, lat_max).
ZOOM = (122.0, 130.0, 34.0, 40.0)
# Region for the circular detail: (lon_center, lat_center, radius in degrees).
CIRCLE = (117.0, 32.0, 3.0)

OUTLINE = {"edgecolor": "black"}
IMSHOW = {"extent": EXTENT, "origin": "lower", "cmap": "viridis", "vmin": 0.0, "vmax": float(FIELD.max())}


def panel_label(ax, letter):
    ax.text(-0.02, 1.02, letter, transform=ax.transAxes, fontsize="large", fontweight="bold", ha="right", va="bottom")


def inset_in_axes(ax):
    """Detail drawn inside the overview axes."""
    im = ax.imshow(FIELD, **IMSHOW)
    axins = ax.inset_axes([0.60, 0.03, 0.38, 0.36])  # x, y, w, h in axes fraction
    axins.imshow(FIELD, **IMSHOW)
    axins.set_xlim(ZOOM[0], ZOOM[1])
    axins.set_ylim(ZOOM[2], ZOOM[3])
    axins.set_xticks([])
    axins.set_yticks([])
    for spine in axins.spines.values():
        spine.set(**OUTLINE)
    ax.indicate_inset_zoom(axins, alpha=1.0, **OUTLINE)
    return im


def detail_in_panel(fig, ax_over, ax_detail):
    """Detail drawn in its own panel, joined to an outline on the overview."""
    im = ax_over.imshow(FIELD, **IMSHOW)
    ax_detail.imshow(FIELD, **IMSHOW)
    ax_detail.set_xlim(ZOOM[0], ZOOM[1])
    ax_detail.set_ylim(ZOOM[2], ZOOM[3])
    ax_detail.yaxis.tick_right()
    ax_detail.yaxis.set_label_position("right")
    for spine in ax_detail.spines.values():
        spine.set(**OUTLINE)
    x0, x1, y0, y1 = ZOOM
    ax_over.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, **OUTLINE))
    # Right corners of the outline -> left corners of the detail panel.
    for y_data, y_frac in ((y1, 1.0), (y0, 0.0)):
        fig.add_artist(ConnectionPatch(
            xyA=(x1, y_data), coordsA="data", axesA=ax_over,
            xyB=(0.0, y_frac), coordsB="axes fraction", axesB=ax_detail,
            **OUTLINE,
        ))
    return im


def circular_inset(ax):
    """Circle on the overview and a larger circular inset; returns the inset axes."""
    im = ax.imshow(FIELD, **IMSHOW)
    x, y, r = CIRCLE
    ax.add_patch(Circle((x, y), r, fill=False, **OUTLINE))
    # A square data window keeps the inset axes square, so its circle stays round.
    axins = ax.inset_axes([0.60, 0.03, 0.38, 0.38])
    image = axins.imshow(FIELD, **IMSHOW)
    axins.set_xlim(x - r, x + r)
    axins.set_ylim(y - r, y + r)
    axins.axis("off")  # clipping the image leaves the axes background and frame
    image.set_clip_path(Circle((0.5, 0.5), 0.5, transform=axins.transAxes))
    axins.add_patch(Circle((0.5, 0.5), 0.5, transform=axins.transAxes, fill=False,
                           clip_on=False, **OUTLINE))
    return im, axins


def join_circles(fig, ax, axins):
    """One line from rim to rim, along the line between the centers on the page.

    Call after the layout is final: the direction is measured in display units.
    """
    x, y, r = CIRCLE
    fig.draw_without_rendering()
    start = ax.transData.transform((x, y))
    end = axins.transAxes.transform((0.5, 0.5))
    ux, uy = (end - start) / np.hypot(*(end - start))
    fig.add_artist(ConnectionPatch(
        xyA=(x + r * ux, y + r * uy), coordsA="data", axesA=ax,
        xyB=(0.5 - 0.5 * ux, 0.5 - 0.5 * uy), coordsB="axes fraction", axesB=axins,
        **OUTLINE,
    ))


def main():
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
        fig = plt.figure(figsize=(width_mm * MM, 118 * MM), layout="constrained")
        grid = fig.add_gridspec(2, 3, width_ratios=[1.33, 1.33, 1.0], height_ratios=[1, 1.2])
        axes = [fig.add_subplot(grid[0, i]) for i in range(3)]
        axes.append(fig.add_subplot(grid[1, :]))
        im = inset_in_axes(axes[0])
        detail_in_panel(fig, axes[1], axes[2])
        _, axins = circular_inset(axes[3])
        for ax, letter in zip(axes, "abcd"):
            panel_label(ax, letter)
        for ax in axes:
            ax.set_xlabel("Longitude (°E)")
        for ax in (axes[0], axes[3]):
            ax.set_ylabel("Latitude (°N)")
        # Attached to the top row only, but the bar serves all four panels.
        fig.colorbar(im, ax=axes[:3], shrink=0.9, label="Value (unit)")
        join_circles(fig, axes[3], axins)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
