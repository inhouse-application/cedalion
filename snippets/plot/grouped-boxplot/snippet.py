"""Grouped box plots: several series side by side at each category, one color per series.
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
SITES = ("North", "Central", "South")  # x categories
# Series: survey year, color and the change in mean leaf length (cm) from the first year.
YEARS = [("2021", "C0", 0.0), ("2022", "C1", 0.6),
         ("2023", "C2", 1.1), ("2024", "C3", 1.4)]
SITE_MEAN = (9.0, 11.0, 8.0)  # mean leaf length (cm) in 2021
N = 40  # leaves per site and year
GROUP_WIDTH = 0.8  # width taken by all boxes at one category, in category units
FILL = 0.8  # share of each slot filled by its box


def offsets(n_series, group_width):
    """Center of each series' slot relative to the category, and the box width."""
    slot = group_width / n_series
    centers = (np.arange(n_series) - (n_series - 1) / 2) * slot
    return centers, slot * FILL


def grouped_boxplot(ax, samples, years, group_width=GROUP_WIDTH):
    """samples[i][j]: values for series i at category j."""
    centers, width = offsets(len(years), group_width)
    for (_, color, _), offset, series in zip(years, centers, samples):
        ax.boxplot(series, positions=np.arange(len(SITES)) + offset, widths=width,
                   patch_artist=True,
                   boxprops={"facecolor": color, "edgecolor": "0.2"},
                   medianprops={"color": "0.1"},
                   whiskerprops={"color": "0.2"},
                   capprops={"color": "0.2"},
                   flierprops={"marker": "o", "markersize": 2, "markerfacecolor": color,
                               "markeredgecolor": "0.2"})
    ax.set_xticks(range(len(SITES)), labels=SITES)
    ax.set_xlim(-0.5, len(SITES) - 0.5)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="0.88")
    ax.set_xlabel("Site")


def main():
    rng = np.random.default_rng(8)
    samples = [[mean + shift + rng.gamma(2.0, 0.8, N) - 1.6 for mean in SITE_MEAN]
               for _, _, shift in YEARS]
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, sharey=True, figsize=(width_mm * MM, 66 * MM),
                                 layout="constrained")
        grouped_boxplot(axes[0], samples, YEARS)
        grouped_boxplot(axes[1], [samples[0], samples[-1]], [YEARS[0], YEARS[-1]],
                        group_width=GROUP_WIDTH * 2 / len(YEARS))
        axes[0].set_ylim(6, 18)
        axes[0].set_yticks(range(6, 19, 2))
        axes[0].set_ylabel("Leaf length (cm)")
        axes[1].tick_params(labelleft=False)
        for ax, letter in zip(axes, "ab"):
            ax.annotate(letter, xy=(0, 1), xycoords="axes fraction", xytext=(0, 4),
                        textcoords="offset points", fontweight="bold", fontsize="large")
        # boxplot returns no labeled artists.
        handles = [Patch(facecolor=color, edgecolor="0.2", label=year)
                   for year, color, _ in YEARS]
        fig.legend(handles=handles, loc="outside lower center", ncol=len(YEARS),
                   frameon=False, title="Survey year")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
