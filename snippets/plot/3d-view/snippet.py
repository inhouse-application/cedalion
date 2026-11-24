"""Point cloud of a street scene, ground colored by slope class: oblique view (a), view from above (b).
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
EXTENT = (60.0, 40.0)  # scene size in x and y (m)
GROUND_POINTS = 14000
SLOPE_BREAKS = (0, 5, 10, 15)  # class edges (degrees); steeper goes to the open end
SLOPE_COLORS = ("#fbe9b7", "#f6c445", "#ec8a2b", "#c8352b")
SLOPE_CMAP = ListedColormap(SLOPE_COLORS)
SLOPE_NORM = BoundaryNorm(SLOPE_BREAKS, SLOPE_CMAP.N, extend="max")
BUILDING = (38.0, 54.0, 6.0, 20.0, 9.0)  # x0, x1, y0, y1 (m), height above ground (m)
BUILDING_COLOR = "0.55"
POINT_SIZE = 0.6  # marker area (pt²)
ZOOM = 1.5  # scale of the 3-D box inside its axes


def ground(x, y):
    """Height (m) of a street that climbs a ramp across x, with a mound at one corner."""
    ramp = 3.0 / (1 + np.exp(-(x - 24) / 3.0))
    mound = 2.2 * np.exp(-((x - 10) ** 2 + (y - 30) ** 2) / 40)
    return ramp + mound


def slope_degrees(x, y, step=0.05):
    """Steepest slope of the ground surface, from central differences."""
    dz_dx = (ground(x + step, y) - ground(x - step, y)) / (2 * step)
    dz_dy = (ground(x, y + step) - ground(x, y - step)) / (2 * step)
    return np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))


def scene(rng):
    """Ground points outside the building footprint, and points on the building walls and roof."""
    x0, x1, y0, y1, height = BUILDING
    x = rng.uniform(0, EXTENT[0], GROUND_POINTS)
    y = rng.uniform(0, EXTENT[1], GROUND_POINTS)
    outside = ~((x > x0) & (x < x1) & (y > y0) & (y < y1))
    x, y = x[outside], y[outside]
    floor = ground((x0 + x1) / 2, (y0 + y1) / 2)
    walls = []
    for _ in range(2500):
        side = rng.integers(4)
        t, z = rng.uniform(0, 1), rng.uniform(0, height)
        walls.append(((x0 + t * (x1 - x0), y0 + (side % 2) * (y1 - y0), z) if side < 2
                      else (x0 + (side % 2) * (x1 - x0), y0 + t * (y1 - y0), z)))
    roof = np.column_stack([rng.uniform(x0, x1, 1500), rng.uniform(y0, y1, 1500),
                            np.full(1500, height)])
    building = np.vstack([walls, roof]) + [0, 0, floor]
    return np.column_stack([x, y, ground(x, y)]), building


def three_d_view(ax, points, building, elev, azim, zoom=ZOOM):
    xyz = points.T
    # clip_on=False: with zoom > 1 the corners of the scene reach past the axes box.
    cloud = ax.scatter(*xyz, c=slope_degrees(xyz[0], xyz[1]), cmap=SLOPE_CMAP,
                       norm=SLOPE_NORM, s=POINT_SIZE, linewidths=0, depthshade=False,
                       rasterized=True, clip_on=False)
    ax.scatter(*building.T, color=BUILDING_COLOR, s=POINT_SIZE, linewidths=0,
               depthshade=False, rasterized=True, clip_on=False)
    ax.view_init(elev=elev, azim=azim)
    # Equal meters on all three axes: no vertical exaggeration.
    top = building[:, 2].max()
    ax.set_box_aspect((EXTENT[0], EXTENT[1], top), zoom=zoom)
    ax.set(xlim=(0, EXTENT[0]), ylim=(0, EXTENT[1]), zlim=(0, top))
    ax.set_axis_off()
    return cloud


def main():
    rng = np.random.default_rng(11)
    points, building = scene(rng)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig = plt.figure(figsize=(width_mm * MM, 64 * MM), layout="constrained")
        grid = fig.add_gridspec(1, 2, width_ratios=(1.35, 1))
        oblique = fig.add_subplot(grid[0], projection="3d")
        above = fig.add_subplot(grid[1], projection="3d", proj_type="ortho")
        cloud = three_d_view(oblique, points, building, elev=28, azim=-62)
        three_d_view(above, points, building, elev=90, azim=-90, zoom=1.2)
        oblique.set_title("a  Oblique view", loc="left")
        above.set_title("b  View from above", loc="left")
        colorbar = fig.colorbar(cloud, ax=[oblique, above], location="bottom",
                                shrink=0.5, aspect=40, pad=0.02, extend="max",
                                extendfrac=0.2)
        colorbar.set_ticks(SLOPE_BREAKS)
        colorbar.set_label("Ground slope (°); building points in gray")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
