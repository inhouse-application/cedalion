"""Histogram in percent of all values, with one bin edge at zero.

Synthetic trends in growing-season length at weather stations; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# Class, fill color, text color, and where its share is printed (data units).
CLASSES = [
    ("Decrease ($p$ < 0.05)", "#2166ac", "#2166ac", (-6.0, 4.0)),
    ("Increase ($p$ < 0.05)", "#b2182b", "#b2182b", (7.5, 7.0)),
    ("Not significant", "#bdbdbd", "0.45", (4.5, 15.0)),
]
# Region, color and number of stations, for b.
REGIONS = [("Lowland", "C0", 420), ("Upland", "C1", 95)]
BIN_WIDTH = 1.0  # days per decade
EDGES = np.arange(-10, 10 + BIN_WIDTH, BIN_WIDTH)  # includes 0, so no bin straddles zero
X_LABEL = "Trend in growing-season length (days/decade)"


def stations(rng, n, mean):
    """Trend per station and its class index (0 decrease, 1 increase, 2 not significant)."""
    trend = rng.normal(mean, 3.0, n)
    # The larger the trend, the more likely it is significant.
    significant = rng.random(n) < 1 / (1 + np.exp(-(np.abs(trend) - 2.5) / 0.6))
    return trend, np.where(significant, np.where(trend < 0, 0, 1), 2)


def check_range(values):
    """hist drops values outside the bins without warning, and the percentages fall short."""
    outside = (values < EDGES[0]) | (values > EDGES[-1])
    if outside.any():
        raise ValueError(f"{outside.sum()} values fall outside EDGES")


def format_axes(ax):
    ax.axvline(0, color="0.2")
    ax.set_xlim(EDGES[0], EDGES[-1])
    ax.set_xticks(np.arange(EDGES[0], EDGES[-1] + 1, 2))
    ax.set_xlabel(X_LABEL)


def histogram_by_class(ax, trend, label):
    """Stacked bars; weights of 100/n make every bar a percentage of all stations."""
    check_range(trend)
    groups = [trend[label == i] for i in range(len(CLASSES))]
    weights = [np.full(g.size, 100 / trend.size) for g in groups]
    ax.hist(groups, bins=EDGES, weights=weights, stacked=True, rwidth=1,
            color=[c[1] for c in CLASSES], label=[c[0] for c in CLASSES],
            edgecolor="white")
    for (_, _, text_color, (x, y)), g in zip(CLASSES, groups):
        ax.text(x, y, f"{100 * g.size / trend.size:.1f}%", color=text_color,
                fontweight="bold", ha="center", va="bottom")
    format_axes(ax)
    ax.legend(loc="upper left", frameon=False, handlelength=1)
    ax.set_ylabel("Stations (%)")


def histogram_by_group(ax, samples):
    """Step outlines on shared bins; each group in percent of its own count."""
    for (name, color, n), values in zip(REGIONS, samples):
        check_range(values)
        ax.hist(values, bins=EDGES, weights=np.full(n, 100 / n), histtype="step",
                color=color, label=f"{name} ($n$ = {n})")
    format_axes(ax)
    ax.legend(loc="upper left", frameon=False, handlelength=1)


def main():
    rng = np.random.default_rng(21)
    trend, label = stations(rng, 515, 1.2)
    samples = [rng.normal(mean, spread, n)
               for (_, _, n), mean, spread in zip(REGIONS, (2.0, -0.5), (2.5, 3.5))]
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, sharey=True, figsize=(width_mm * MM, 62 * MM),
                                 layout="constrained")
        histogram_by_class(axes[0], trend, label)
        histogram_by_group(axes[1], samples)
        axes[1].tick_params(labelleft=True)
        axes[0].set_yticks(range(0, 21, 5))
        for ax, letter in zip(axes, "ab"):
            ax.annotate(letter, xy=(0, 1), xycoords="axes fraction", xytext=(0, 4),
                        textcoords="offset points", fontweight="bold", fontsize="large")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
