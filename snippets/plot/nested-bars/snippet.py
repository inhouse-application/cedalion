"""Draw the stations in a subset as narrow bars inside the bars for all stations.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
YEARS = np.arange(2012, 2024)
ALL = np.array([41, 44, 52, 57, 55, 61, 68, 66, 49, 58, 72, 75])
AUTOMATIC = np.array([6, 9, 14, 20, 24, 31, 39, 43, 37, 46, 60, 66])
WIDE, NARROW = 0.75, 0.4


def nested_bars(ax):
    whole = ax.bar(YEARS, ALL, width=WIDE, color="C0", label="All stations", zorder=1)
    ax.bar(YEARS, AUTOMATIC, width=NARROW, color="C1", label="Automatic stations",
           zorder=2)
    ax.bar_label(whole, padding=1.5, color="C0", fontweight="bold")
    ax.set_xticks(YEARS)
    ax.set_xlim(YEARS[0] - 0.6, YEARS[-1] + 0.6)
    # Autoscaling stops at the tallest bar; leave room for its label.
    ax.set_ylim(0, 1.12 * ALL.max())
    ax.set(xlabel="Year", ylabel="Stations reporting")
    ax.legend(loc="upper left", frameon=False)


def main():
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, ax = plt.subplots(figsize=(width_mm * MM, 62 * MM), layout="constrained")
        nested_bars(ax)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
