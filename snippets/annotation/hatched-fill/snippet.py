"""Hatch the cells without data in a gridded field, and hatch bars of a separate class.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
NO_DATA_HATCH = "////"
HATCH_COLOR = "0.55"
CLASS_HATCH = "xxxx"
BAR_COLOR = "C0"
DISTRICTS = ("D1", "D2", "D3", "D4", "D5", "D6")


def synthetic_field(rng):
    x = np.linspace(0, 60, 61)
    y = np.linspace(0, 40, 41)
    xc, yc = np.meshgrid(x[:-1] + 0.5, y[:-1] + 0.5)
    moisture = 25 + 8 * np.sin(xc / 9) * np.cos(yc / 7) + rng.normal(0, 0.8, xc.shape)
    gap = ((xc - 38) ** 2 / 120 + (yc - 22) ** 2 / 50) < 1
    return x, y, np.ma.masked_where(gap, moisture)


def no_data_hatching(fig, ax, x, y, moisture):
    # Masked cells are not drawn, so the hatched patch behind the mesh shows
    # only where data are missing.
    ax.add_patch(plt.Rectangle((x[0], y[0]), x[-1] - x[0], y[-1] - y[0],
                               facecolor="white", hatch=NO_DATA_HATCH,
                               hatchcolor=HATCH_COLOR, edgecolor="none", zorder=0))
    mesh = ax.pcolormesh(x, y, moisture, cmap="YlGnBu", vmin=12, vmax=38, zorder=1)
    fig.colorbar(mesh, ax=ax, shrink=0.85, aspect=20, label="Soil moisture (%)")
    key = Patch(facecolor="white", hatch=NO_DATA_HATCH, hatchcolor=HATCH_COLOR,
                edgecolor="0.4", label="No data")
    ax.legend(handles=[key], loc="upper left", bbox_to_anchor=(0, -0.02),
              frameon=False, handleheight=1.4, handlelength=2.2)
    ax.set(aspect="equal", xticks=[], yticks=[])


def hatched_class(ax, rng):
    measured = rng.integers(20, 60, len(DISTRICTS))
    estimated = rng.integers(5, 25, len(DISTRICTS))
    position = np.arange(len(DISTRICTS))
    ax.bar(position, measured, width=0.65, color=BAR_COLOR, label="Measured")
    # The hatch takes the edge color unless hatchcolor is given.
    ax.bar(position, estimated, bottom=measured, width=0.65, color=BAR_COLOR,
           hatch=CLASS_HATCH, hatchcolor="white", edgecolor=BAR_COLOR,
           label="Estimated")
    ax.set_xticks(position, DISTRICTS)
    ax.set(xlabel="District", ylabel="Wells")
    ax.legend(loc="upper left", frameon=False, handleheight=1.4, handlelength=2.2)
    ax.set_ylim(0, 1.25 * (measured + estimated).max())


def main():
    rng = np.random.default_rng(4)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 70 * MM),
                                 gridspec_kw={"width_ratios": [1.6, 1]},
                                 layout="constrained")
        no_data_hatching(fig, axes[0], *synthetic_field(rng))
        hatched_class(axes[1], rng)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
