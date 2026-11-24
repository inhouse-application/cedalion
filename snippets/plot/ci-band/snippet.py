"""Confidence bands: two group means with 95% intervals, and a latitude profile.
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.legend_handler import HandlerTuple
from matplotlib.patches import Patch

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
GROUPS = {"Street trees": "C0", "Lawn": "C1"}
BAND_ALPHA = 0.25
Z95 = 1.96  # normal quantile


def mean_and_ci(samples):
    """Mean over axis 0 and the half-width of its 95% confidence interval."""
    mean = samples.mean(axis=0)
    half = Z95 * samples.std(axis=0, ddof=1) / np.sqrt(samples.shape[0])
    return mean, half


def bands_by_group(ax, rng):
    distance = np.linspace(0, 200, 41)
    keys = []
    for (group, color), depth in zip(GROUPS.items(), (2.4, 1.1)):
        truth = depth * np.exp(-distance / 70)
        samples = truth + rng.normal(0, 0.6 + distance / 300, (80, distance.size))
        mean, half = mean_and_ci(samples)
        ax.fill_between(distance, mean - half, mean + half, color=color,
                        alpha=BAND_ALPHA, linewidth=0)
        line, = ax.plot(distance, mean, color=color)
        keys.append((Patch(facecolor=color, alpha=BAND_ALPHA), line))
    # ndivide=1 overlays the band patch and its line in one key.
    ax.legend(keys, list(GROUPS), title="Mean and 95% confidence interval",
              alignment="left", handler_map={tuple: HandlerTuple(ndivide=1)},
              loc="upper right", frameon=False)
    ax.axhline(0, color="0.5", ls="--", zorder=0)
    ax.set(xlim=(0, 200), xlabel="Distance from green space (m)",
           ylabel="Cooling (°C)")


def latitude_profile(ax, rng):
    latitude = np.arange(-50, 61, 2.5)
    truth = 2 + 1.5 * np.cos(np.radians(latitude - 40) * 2.2)
    count = np.where(np.abs(latitude) < 35, 160, 40)
    mean, half = np.empty(latitude.size), np.empty(latitude.size)
    for i, (center, n) in enumerate(zip(truth, count)):
        mean[i], half[i] = mean_and_ci(rng.normal(center, 1.2, n))
    # fill_betweenx fills between two x curves along y.
    ax.fill_betweenx(latitude, mean - half, mean + half, color="0.6",
                     alpha=0.4, linewidth=0, label="95% confidence interval")
    ax.plot(mean, latitude, color="C0", label="Mean")
    ax.axhline(0, color="0.5", ls="--", zorder=0)
    ax.set_yticks(np.arange(-40, 61, 20),
                  [f"{abs(v)}°{'N' if v > 0 else 'S' if v < 0 else ''}"
                   for v in np.arange(-40, 61, 20)])
    ax.set(ylim=(-50, 60), xlabel="Cooling (°C)")
    ax.legend(loc="lower right", frameon=False)


def main():
    rng = np.random.default_rng(9)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 66 * MM),
                                 gridspec_kw={"width_ratios": [1.6, 1]},
                                 layout="constrained")
        bands_by_group(axes[0], rng)
        latitude_profile(axes[1], rng)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
