"""Error bars on grouped bars and on a series of points, with their meaning printed.

Synthetic replicate measurements and monthly draws; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
WETLANDS = ("Riverine", "Depressional", "Constructed")
SEASONS = {"Spring": "C0", "Summer": "C1", "Autumn": "C2"}
REPLICATES = 8
ERROR = {"ecolor": "0.2", "capsize": 1.5}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def bars_with_ci(ax, rng):
    width = 0.8 / len(SEASONS)
    position = np.arange(len(WETLANDS))
    for i, (season, color) in enumerate(SEASONS.items()):
        samples = rng.normal(rng.uniform(20, 60, len(WETLANDS)), 8,
                             (REPLICATES, len(WETLANDS)))
        mean = samples.mean(axis=0)
        # 95% confidence interval of the mean; t(0.975, 7) = 2.365 for 8 replicates.
        half = 2.365 * samples.std(axis=0, ddof=1) / np.sqrt(REPLICATES)
        x = position + (i - (len(SEASONS) - 1) / 2) * width
        ax.bar(x, mean, width=width, color=color, label=season)
        ax.errorbar(x, mean, yerr=half, fmt="none", **ERROR)
    ax.set_xticks(position, WETLANDS)
    ax.set(ylim=(0, 80), ylabel="Nitrogen removal (%)")
    ax.legend(title="Mean ± 95% CI", alignment="left", loc="upper left", ncols=3,
              frameon=False, handlelength=1, columnspacing=1)


def points_with_quantiles(ax, rng):
    month = np.arange(12)
    draws = (0.6 * np.sin((month - 3) / 12 * 2 * np.pi)
             + rng.gamma(2, 0.25, (400, 12)))
    median = np.median(draws, axis=0)
    low, high = np.percentile(draws, [5, 95], axis=0)
    # yerr takes distances from the point, not the interval ends.
    ax.errorbar(month, median, yerr=[median - low, high - median], fmt="-o",
                color="C0", ms=3, **ERROR, label="Median, 5–95th percentile")
    ax.axhline(0, color="0.5", ls="--", zorder=0)
    ax.set_xticks(month, MONTHS)
    ax.set(ylabel="Drought index")
    ax.legend(loc="upper left", frameon=False)


def main():
    rng = np.random.default_rng(8)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 62 * MM),
                                 layout="constrained")
        bars_with_ci(axes[0], rng)
        points_with_quantiles(axes[1], rng)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
