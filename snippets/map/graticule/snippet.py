"""Graticule: latitude and longitude lines on a lon/lat map (a) and on an Equal Earth world map (b).

Synthetic land on a lon/lat grid; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import PathPatch, Polygon
from matplotlib.path import Path as MplPath
from matplotlib.ticker import FuncFormatter, MultipleLocator

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
REGION = (95, 140, 20, 50)  # panel a: lon_min, lon_max, lat_min, lat_max
STEP_A = 10  # degrees between grid lines in panel a
PARALLELS = np.arange(-60, 61, 30)  # panel b
MERIDIANS = np.arange(-180, 181, 30)
LABELED_MERIDIANS = np.arange(-120, 121, 60)
GRATICULE = {"color": "0.6"}
FRAME = {"facecolor": "none", "edgecolor": "0.2"}
LAND = {"facecolor": "0.85", "edgecolor": "0.55"}
# Land masses: center lon, center lat, half-width and half-height in degrees.
LANDS = [(-100, 45, 30, 18), (-60, -15, 14, 22), (20, 5, 18, 28), (85, 45, 50, 18),
         (133, -25, 15, 10), (120, 30, 12, 12)]


def wiggle(rng, n, scale, terms=10):
    t = np.linspace(0, 1, n, endpoint=False)
    return sum(scale / k * np.sin(2 * np.pi * k * t + rng.uniform(0, 2 * np.pi))
               for k in range(1, terms + 1))


def land_rings(rng):
    rings = []
    for lon, lat, rx, ry in LANDS:
        angle = np.linspace(0, 2 * np.pi, 300, endpoint=False)
        radius = 1 + wiggle(rng, angle.size, 0.1)
        ring = np.column_stack([np.clip(lon + rx * radius * np.cos(angle), -180, 180),
                                np.clip(lat + ry * radius * np.sin(angle), -85, 85)])
        rings.append(np.vstack([ring, ring[:1]]))
    return rings


def equal_earth(lon, lat):
    """Equal Earth projection (Šavrič et al. 2018) for a unit sphere; degrees in."""
    a1, a2, a3, a4 = 1.340264, -0.081106, 0.000893, 0.003796
    lam, phi = np.radians(lon), np.radians(lat)
    theta = np.arcsin(np.sqrt(3) / 2 * np.sin(phi))
    x = (2 * np.sqrt(3) * lam * np.cos(theta)
         / (3 * (9 * a4 * theta**8 + 7 * a3 * theta**6 + 3 * a2 * theta**2 + a1)))
    y = a4 * theta**9 + a3 * theta**7 + a2 * theta**3 + a1 * theta
    return x, y


def degrees(positive, negative):
    def label(value, _=None):
        if value == 0 or abs(value) == 180:
            return f"{abs(value):g}°"
        return f"{abs(value):g}°{positive if value > 0 else negative}"
    return label


def graticule_lonlat(ax, rings):
    """Panel a: grid lines at the ticks, labels on all four sides."""
    for ring in rings:
        ax.add_patch(PathPatch(MplPath(ring), **LAND))
    ax.set(xlim=REGION[:2], ylim=REGION[2:])
    ax.set_aspect(1 / np.cos(np.radians(np.mean(REGION[2:]))))
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_locator(MultipleLocator(STEP_A))
    ax.xaxis.set_major_formatter(FuncFormatter(degrees("E", "W")))
    ax.yaxis.set_major_formatter(FuncFormatter(degrees("N", "S")))
    ax.tick_params(top=True, right=True, labeltop=True, labelright=True)
    ax.grid(True, **GRATICULE)
    ax.set_axisbelow(False)  # grid over the land


def graticule_projected(ax, rings):
    """Panel b: project parallels, meridians, land and frame; label outside the frame."""
    fine = np.linspace(-90, 90, 181)
    edge = np.concatenate([np.column_stack(equal_earth(np.full_like(fine, 180), fine)),
                           np.column_stack(equal_earth(np.full_like(fine, -180), fine[::-1]))])
    frame = Polygon(edge, closed=True, **FRAME)
    ax.add_patch(Polygon(edge, closed=True, facecolor="white", edgecolor="none"))
    for ring in rings:
        ax.add_patch(Polygon(np.column_stack(equal_earth(*ring.T)), **LAND))
    fine_lon = np.linspace(-180, 180, 361)
    for lat in PARALLELS:
        ax.plot(*equal_earth(fine_lon, np.full_like(fine_lon, lat)), **GRATICULE)
    for lon in MERIDIANS[1:-1]:  # ±180 are the frame
        ax.plot(*equal_earth(np.full_like(fine, lon), fine), **GRATICULE)
    ax.add_patch(frame)

    lat_label = degrees("N", "S")
    for lat in PARALLELS:
        x, y = equal_earth(-180, lat)
        ax.annotate(lat_label(lat), (x, y), xytext=(-4, 0), textcoords="offset points",
                    ha="right", va="center")
    lon_label = degrees("E", "W")
    for lon in LABELED_MERIDIANS:
        x, y = equal_earth(lon, -90)
        ax.annotate(lon_label(lon), (x, y), xytext=(0, -2), textcoords="offset points",
                    ha="center", va="top")
    x_max, y_max = equal_earth(180, 0)[0], equal_earth(0, 90)[1]
    # 1% margin so the frame line is not clipped.
    ax.set(xlim=(-1.01 * x_max, 1.01 * x_max), ylim=(-1.01 * y_max, 1.01 * y_max),
           aspect="equal")
    ax.set_axis_off()


def main():
    rng = np.random.default_rng(4)
    rings = land_rings(rng)
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
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(width_mm * MM, 66 * MM),
                                         width_ratios=(1, 1.7), layout="constrained")
        graticule_lonlat(ax_a, rings)
        graticule_projected(ax_b, rings)
        for ax, letter, x in ((ax_a, "a", -0.12), (ax_b, "b", -0.06)):
            ax.text(x, 1.08, letter, transform=ax.transAxes, fontsize="large", fontweight="bold",
                    ha="left", va="bottom")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
