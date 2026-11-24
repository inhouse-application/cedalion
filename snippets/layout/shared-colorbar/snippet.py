"""Shared color bar: one color bar per column of map panels, each over one fixed scale.

Synthetic gridded fields; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize
from matplotlib.ticker import FuncFormatter

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
EXTENT = (-10, 70, 35, 60)  # lon_min, lon_max, lat_min, lat_max
LON = np.linspace(EXTENT[0], EXTENT[1], 320)
LAT = np.linspace(EXTENT[2], EXTENT[3], 100)
# One norm per column, passed to every panel of that column.
VALUE = {"cmap": "viridis", "norm": Normalize(0.2, 1.2)}
CHANGE = {"cmap": "RdBu_r", "norm": Normalize(-0.3, 0.3)}
YEARS = (2000, 2020)
PERIODS = ("1980–2000", "2000–2020")


def field(rng, base, spread):
    lon2d, lat2d = np.meshgrid(LON, LAT)
    value = np.full(lon2d.shape, base)
    for amp, x, y, s in zip(rng.normal(0, spread, 8), rng.uniform(-5, 65, 8),
                            rng.uniform(38, 57, 8), rng.uniform(3, 8, 8)):
        value += amp * np.exp(-((lon2d - x) ** 2 + (lat2d - y) ** 2) / (2 * s**2))
    return value


def degrees(positive, negative):
    def label(value, _):
        return f"{abs(value):g}°{positive if value > 0 else negative}" if value else "0°"
    return FuncFormatter(label)


def map_panel(ax, values, scale, letter, title):
    image = ax.imshow(values, extent=EXTENT, origin="lower", interpolation="nearest", **scale)
    ax.text(0, 1.03, letter, transform=ax.transAxes, fontsize="large", fontweight="bold",
            ha="left", va="bottom")
    ax.annotate(title, (0, 1.03), xycoords="axes fraction", xytext=(9, 0),
                textcoords="offset points", ha="left", va="bottom")
    ax.set_aspect(1 / np.cos(np.deg2rad(np.mean(EXTENT[2:]))))
    ax.set(xticks=np.arange(0, 61, 20), yticks=np.arange(40, 61, 10))
    ax.xaxis.set_major_formatter(degrees("E", "W"))
    ax.yaxis.set_major_formatter(degrees("N", "S"))
    return image


def shared_colorbar(fig, image, column, label, extend):
    """One horizontal color bar under all panels of a column."""
    return fig.colorbar(image, ax=column, location="bottom", shrink=0.8, aspect=25,
                        pad=0.02, extend=extend, label=label)


def main():
    rng = np.random.default_rng(6)
    value_2000 = field(rng, 0.65, 0.25)
    value_2020 = value_2000 + field(rng, 0.03, 0.15)
    change_early = field(rng, 0.0, 0.15)
    change_late = value_2020 - value_2000
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(2, 2, sharex=True, sharey=True, figsize=(width_mm * MM, 100 * MM),
                                 layout="constrained")
        left = [map_panel(axes[0, 0], value_2000, VALUE, "a", str(YEARS[0])),
                map_panel(axes[1, 0], value_2020, VALUE, "c", str(YEARS[1]))]
        right = [map_panel(axes[0, 1], change_early, CHANGE, "b", PERIODS[0]),
                 map_panel(axes[1, 1], change_late, CHANGE, "d", PERIODS[1])]
        for ax in axes.flat:
            ax.label_outer()
        # Any image of the column will do: they all hold the same norm.
        shared_colorbar(fig, left[0], axes[:, 0], "Value (unit)", "both")
        shared_colorbar(fig, right[0], axes[:, 1], "Change in value (unit)", "both")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
