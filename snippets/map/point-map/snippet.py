"""Point map: cities on gray land, value by color (a) or by color and size together (b).
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
EXTENT = (-40, 80, -40, 60)  # lon_min, lon_max, lat_min, lat_max
# Land masses: center lon, center lat, half-width and half-height in degrees.
LANDS = [(-14, 30, 18, 22), (42, 38, 30, 16), (25, -12, 16, 22), (66, -5, 9, 8)]
LAND = {"facecolor": "0.88", "edgecolor": "0.55"}
N_CITIES = 600
VMIN, VMAX = 10, 30  # color scale of panel a
CLASSES = [10, 14, 18, 22, 26, 30]  # class edges of panel b
SIZES = [1.5, 3, 5, 8, 12]  # marker area (points²) per class in panel b


def wiggle(rng, n, scale, terms=8):
    t = np.linspace(0, 1, n, endpoint=False)
    return sum(scale / k * np.sin(2 * np.pi * k * t + rng.uniform(0, 2 * np.pi))
               for k in range(1, terms + 1))


def land_paths(rng):
    paths = []
    for lon, lat, rx, ry in LANDS:
        angle = np.linspace(0, 2 * np.pi, 200, endpoint=False)
        radius = 1 + wiggle(rng, angle.size, 0.12)
        ring = np.column_stack([lon + rx * radius * np.cos(angle),
                                lat + ry * radius * np.sin(angle)])
        paths.append(MplPath(np.vstack([ring, ring[:1]]), closed=True))
    return paths


def cities(rng, lands):
    """Cities inside the land masses; value falls with distance from the equator."""
    lon = rng.uniform(*EXTENT[:2], 20 * N_CITIES)
    lat = rng.uniform(*EXTENT[2:], 20 * N_CITIES)
    points = np.column_stack([lon, lat])
    keep = np.any([path.contains_points(points) for path in lands], axis=0)
    lon, lat = points[keep][:N_CITIES].T
    value = 28 - 0.3 * np.abs(lat) + rng.normal(0, 1.5, lon.size)
    return lon, lat, value


def base_map(ax, lands):
    for path in lands:
        ax.add_patch(PathPatch(path, **LAND))
    ax.set(xlim=EXTENT[:2], ylim=EXTENT[2:], aspect="equal")
    ax.set_axis_off()


def point_map(ax, lon, lat, value, norm, cmap, sizes=None):
    """Draw cities as filled circles. Without `sizes` every point has one size."""
    order = np.argsort(value)  # draw high values last so they are not hidden
    s = 4 if sizes is None else sizes[order]
    return ax.scatter(lon[order], lat[order], c=value[order], s=s, cmap=cmap, norm=norm,
                      edgecolors="white", zorder=3)


def class_legend(ax, norm, cmap):
    handles = []
    for i, (low, high) in enumerate(zip(CLASSES[:-1], CLASSES[1:])):
        color = cmap(norm((low + high) / 2))
        # The end classes also hold values beyond the outer edges.
        label = f"< {high}" if i == 0 else f"≥ {low}" if high == CLASSES[-1] else f"{low}–{high}"
        handles.append(Line2D([], [], linestyle="none", marker="o", markersize=np.sqrt(SIZES[i]),
                              markerfacecolor=color, markeredgecolor="white",
                              label=label))
    ax.legend(handles=handles, title="Value (unit)", loc="lower left", frameon=False,
              handletextpad=0.2, borderaxespad=0.2)


def main():
    rng = np.random.default_rng(3)
    lands = land_paths(rng)
    lon, lat, value = cities(rng, lands)
    cmap = plt.get_cmap("viridis")
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
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(width_mm * MM, 80 * MM), layout="constrained")

        base_map(ax_a, lands)
        points = point_map(ax_a, lon, lat, value, Normalize(VMIN, VMAX), cmap)
        bar = ax_a.inset_axes([0.03, 0.12, 0.3, 0.035])
        fig.colorbar(points, cax=bar, orientation="horizontal", extend="both",
                     ticks=range(VMIN, VMAX + 1, 5), label="Value (unit)")

        base_map(ax_b, lands)
        classes = BoundaryNorm(CLASSES, cmap.N, extend="neither")
        index = np.clip(np.digitize(value, CLASSES) - 1, 0, len(SIZES) - 1)
        clipped = np.clip(value, CLASSES[0], CLASSES[-1] - 1e-9)
        point_map(ax_b, lon, lat, clipped, classes, cmap, sizes=np.array(SIZES)[index])
        class_legend(ax_b, classes, cmap)

        for ax, letter in zip((ax_a, ax_b), "ab"):
            ax.text(0, 1, letter, transform=ax.transAxes, fontsize="large", fontweight="bold",
                    ha="left", va="top")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
