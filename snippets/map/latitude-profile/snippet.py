"""Station map with a latitude profile that shares its latitude axis.
Synthetic spring-onset anomalies; the profile shows the mean and one standard deviation per latitude bin."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize
from matplotlib.patches import ConnectionPatch
from matplotlib.ticker import FuncFormatter

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
EXTENT = (-10, 50, 36, 64)  # lon_min, lon_max, lat_min, lat_max
REFERENCE_LAT = 52  # °N, drawn across both panels
BIN_WIDTH = 2  # degrees of latitude per profile bin
MIN_STATIONS = 8  # bins with fewer stations are left out of the profile
LIMIT = 12  # days; color scale and profile run from -LIMIT to +LIMIT
GUIDE = {"color": "0.35", "linestyle": "--", "snap": False}
LINE_COLOR = "C0"
WIDTHS = (4, 1)  # map and profile column widths


def stations(rng, n=420):
    """Return lon, lat and an anomaly that changes sign north of REFERENCE_LAT."""
    lon = rng.uniform(EXTENT[0] + 1, EXTENT[1] - 1, n)
    lat = 36.5 + 26 * rng.beta(1.6, 1.4, n)
    anomaly = 4 - 9 / (1 + np.exp(-(lat - REFERENCE_LAT) / 2.5))
    anomaly += 0.08 * (lon - 20) + rng.normal(0, 3, n)
    return lon, lat, anomaly


def latitude_profile(lat, value):
    """Mean and standard deviation of value in BIN_WIDTH latitude bins."""
    edges = np.arange(EXTENT[2], EXTENT[3] + BIN_WIDTH, BIN_WIDTH)
    centers, mean, sd = [], [], []
    for low, high in zip(edges[:-1], edges[1:]):
        inside = value[(lat >= low) & (lat < high)]
        if inside.size >= MIN_STATIONS:
            centers.append((low + high) / 2)
            mean.append(inside.mean())
            sd.append(inside.std(ddof=1))
    return np.array(centers), np.array(mean), np.array(sd)


def degrees(east_or_north, west_or_south):
    def label(value, _):
        if value == 0:
            return "0°"
        return f"{abs(value):g}°{east_or_north if value > 0 else west_or_south}"
    return FuncFormatter(label)


def draw_map(ax, lon, lat, anomaly):
    norm = Normalize(-LIMIT, LIMIT)
    points = ax.scatter(lon, lat, c=anomaly, cmap="RdBu_r", norm=norm, s=5,
                        edgecolors="0.2")
    ax.axhline(REFERENCE_LAT, **GUIDE)
    ax.annotate(f"Reference latitude ({REFERENCE_LAT}°N)", (0.01, REFERENCE_LAT),
                xycoords=ax.get_yaxis_transform(), xytext=(0, 2),
                textcoords="offset points", ha="left", va="bottom", zorder=3,
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6})
    # One degree of longitude is cos(latitude) as long as one degree of latitude.
    ax.set_aspect(1 / np.cos(np.deg2rad(np.mean(EXTENT[2:]))))
    ax.set(xlim=EXTENT[:2], ylim=EXTENT[2:], xticks=np.arange(-10, 51, 10),
           yticks=np.arange(40, 61, 5))
    ax.xaxis.set_major_formatter(degrees("E", "W"))
    ax.yaxis.set_major_formatter(degrees("N", "S"))
    return points


def match_height(ax_map, ax_profile):
    """Give the profile the map's height: box aspect is height / width."""
    # The map's aspect is the drawn length of a degree of latitude over one of longitude.
    map_box = (EXTENT[3] - EXTENT[2]) * ax_map.get_aspect() / (EXTENT[1] - EXTENT[0])
    ax_profile.set_box_aspect(map_box * WIDTHS[0] / WIDTHS[1])


def draw_profile(ax, lat, anomaly):
    centers, mean, sd = latitude_profile(lat, anomaly)
    ax.fill_betweenx(centers, mean - sd, mean + sd, color=LINE_COLOR, alpha=0.2,
                     linewidth=0)
    ax.plot(mean, centers, color=LINE_COLOR)
    ax.axvline(0, color="0.6")
    ax.axhline(REFERENCE_LAT, **GUIDE)
    ax.set_xlim(-LIMIT, LIMIT)
    ax.set_xticks([-10, 0, 10])
    ax.set_xlabel("Anomaly (days)")
    ax.set_title("Mean ± 1 s.d.", pad=3)
    ax.yaxis.tick_right()
    ax.tick_params(axis="y", labelleft=False, labelright=True)


def bridge(fig, ax_map, ax_profile):
    """Continue the reference line through the gap between the two panels."""
    fig.add_artist(ConnectionPatch(
        xyA=(1, REFERENCE_LAT), coordsA=ax_map.get_yaxis_transform(),
        xyB=(0, REFERENCE_LAT), coordsB=ax_profile.get_yaxis_transform(), **GUIDE))


def main():
    lon, lat, anomaly = stations(np.random.default_rng(7))
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
        fig, (ax_map, ax_profile) = plt.subplots(
            1, 2, sharey=True, figsize=(width_mm * MM, 122 * MM), layout="constrained",
            gridspec_kw={"width_ratios": WIDTHS})
        points = draw_map(ax_map, lon, lat, anomaly)
        draw_profile(ax_profile, lat, anomaly)
        match_height(ax_map, ax_profile)
        bridge(fig, ax_map, ax_profile)
        # Attached to the map alone, the color bar shortens the map column and breaks the alignment.
        colorbar = fig.colorbar(points, ax=[ax_map, ax_profile], location="bottom",
                                 extend="both", shrink=0.5, aspect=40)
        colorbar.set_label("Spring onset anomaly (days)")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
