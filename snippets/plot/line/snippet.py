"""Line chart: two metrics stacked on one shared x-axis, each series with its own color and marker.
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
YEARS = np.arange(2000, 2022, 2)
# Product, color, marker and first year with data.
PRODUCTS = [
    ("RainSat", "C0", "^", 2000),
    ("GaugeGrid", "C1", "v", 2000),
    ("Reanalysis", "C2", "o", 2000),
    ("MergedV2", "C3", "D", 2008),
    ("RadarMosaic", "C4", "P", 2014),
]
MEAN_STYLE = {"color": "black", "linestyle": (0, (4, 2)), "marker": "s",
              "markersize": 3, "label": "Mean of all"}
# Metric, axis label and limits.
METRICS = [("bias", "Bias (%)", (-40, 10)), ("r", "Correlation", (0.4, 1.0))]


def synthetic(rng):
    """values[metric][product]: one value per year, NaN before the product's first year."""
    values = {"bias": [], "r": []}
    for i, (*_, start) in enumerate(PRODUCTS):
        trend = (YEARS - YEARS[0]) / (YEARS[-1] - YEARS[0])
        bias = -32 + 6 * i + 12 * trend + rng.normal(0, 3, YEARS.size)
        r = 0.55 + 0.04 * i + 0.2 * trend + rng.normal(0, 0.025, YEARS.size)
        missing = YEARS < start
        values["bias"].append(np.where(missing, np.nan, bias))
        values["r"].append(np.where(missing, np.nan, np.clip(r, 0, 0.98)))
    return values


def line_chart(ax, series):
    """One line per product; NaN values leave the line out, so late series start mid-axis."""
    for (name, color, marker, _), values in zip(PRODUCTS, series):
        ax.plot(YEARS, values, color=color, marker=marker, label=name)
    # The mean of the products available in each year.
    ax.plot(YEARS, np.nanmean(series, axis=0), zorder=3, **MEAN_STYLE)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="0.9")


def main():
    rng = np.random.default_rng(3)
    values = synthetic(rng)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(2, 1, sharex=True, figsize=(width_mm * MM, 85 * MM),
                                 layout="constrained")
        for ax, (key, label, limits), letter in zip(axes, METRICS, "ab"):
            line_chart(ax, values[key])
            ax.set(ylabel=label, ylim=limits)
            ax.annotate(letter, xy=(0, 1), xycoords="axes fraction", xytext=(-24, 0),
                        textcoords="offset points", fontweight="bold", fontsize="large",
                        va="top")
        # sharex hides the upper panel's tick labels.
        axes[-1].set_xticks(YEARS)
        axes[-1].set_xlim(YEARS[0] - 0.6, YEARS[-1] + 0.6)
        axes[-1].set_xlabel("Year")
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside right center", frameon=False)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
