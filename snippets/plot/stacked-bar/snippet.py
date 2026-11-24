"""Stacked bar chart in absolute values (a) and as 100% of each bar (b), from the same table.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
CLASSES = ["<1", "1–10", "10–100", "100–1000", ">1000"]  # fire size (km²)
# Part, color, and burned area (thousand km²) in each class.
# The first part is stacked at the bottom.
PARTS = [
    ("Forest", "C0", [1.1, 4.0, 9.5, 21.0, 38.0]),
    ("Shrubland", "C1", [2.0, 6.5, 11.0, 15.5, 12.0]),
    ("Grassland", "C2", [4.5, 9.0, 12.5, 10.0, 6.0]),
    ("Cropland", "C3", [6.0, 5.0, 2.5, 1.0, 0.3]),
    ("Other", "#dddddd", [0.8, 1.2, 1.5, 1.8, 2.2]),
]
WIDTH = 0.65
EDGE = {"edgecolor": "white"}


def stacked_bars(ax, table):
    """table: one row per part, one column per class. Returns the bar containers."""
    bottom = np.zeros(table.shape[1])
    containers = []
    for (name, color, _), row in zip(PARTS, table):
        containers.append(ax.bar(range(len(CLASSES)), row, WIDTH, bottom=bottom,
                                 color=color, label=name, **EDGE))
        bottom += row
    ax.set_xticks(range(len(CLASSES)), labels=CLASSES)
    ax.tick_params(axis="x", length=0)
    ax.set_xlabel("Fire size (km$^2$)")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="0.9")
    return containers


def main():
    area = np.array([values for *_, values in PARTS])
    totals = area.sum(axis=0)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 66 * MM), layout="constrained")
        containers = stacked_bars(axes[0], area)
        axes[0].bar_label(containers[-1], labels=[f"{t:.0f}" for t in totals], padding=2)
        axes[0].set_ylim(0, 1.1 * totals.max())
        axes[0].set_ylabel("Burned area (thousand km$^2$)")
        stacked_bars(axes[1], 100 * area / totals)
        axes[1].set_ylim(0, 100)
        axes[1].set_yticks(range(0, 101, 20))
        axes[1].set_ylabel("Share of burned area (%)")
        for ax, letter in zip(axes, "ab"):
            ax.annotate(letter, xy=(0, 1), xycoords="axes fraction", xytext=(0, 4),
                        textcoords="offset points", fontweight="bold", fontsize="large")
        # Handles come in drawing order, bottom first.
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles[::-1], labels[::-1], loc="outside right center", frameon=False,
                   title="Vegetation", alignment="left")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
