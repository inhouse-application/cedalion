"""Strip plot: every observation as a point, spread sideways within its category.
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgba

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# name: (sample size, mean, standard deviation) of soil respiration (µmol CO₂ m⁻² s⁻¹)
GROUPS = {
    "Cropland": (60, 3.1, 0.9),
    "Grassland": (35, 4.0, 1.1),
    "Forest": (18, 5.2, 1.4),
    "Wetland": (5, 6.0, 1.0),
}
POINT_COLOR = "C0"
JITTER = 0.18  # half-width of the sideways spread, in category units
BOX_WIDTH = 0.6


def samples(rng):
    return {name: rng.normal(mean, sd, n) for name, (n, mean, sd) in GROUPS.items()}


def strip(ax, data, rng):
    """Points at their value, shifted sideways at random so equal values do not overlap."""
    for position, values in enumerate(data.values()):
        x = position + rng.uniform(-JITTER, JITTER, len(values))
        ax.scatter(x, values, s=6, color=POINT_COLOR, alpha=0.75, linewidths=0,
                   zorder=3)


def boxes(ax, data):
    ax.boxplot(list(data.values()), positions=range(len(data)), widths=BOX_WIDTH,
               showfliers=False,
               patch_artist=True,
               boxprops={"facecolor": to_rgba(POINT_COLOR, 0.25), "edgecolor": "0.3"},
               whiskerprops={"color": "0.3"},
               capprops={"color": "0.3"},
               medianprops={"color": "black"})


def t975(df, z=1.959964):
    """97.5 % quantile of Student's t (Cornish-Fisher series); within 0.1 % for df >= 4."""
    return (z + (z**3 + z) / (4 * df)
            + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * df**2)
            + (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / (384 * df**3)
            + (79 * z**9 + 776 * z**7 + 1482 * z**5 - 1920 * z**3 - 945 * z)
            / (92160 * df**4))


def mean_interval(ax, data):
    """Mean and t-based 95 % interval, drawn beside the points."""
    for position, values in enumerate(data.values()):
        mean = values.mean()
        half = t975(len(values) - 1) * values.std(ddof=1) / np.sqrt(len(values))
        x = position + JITTER + 0.12
        ax.errorbar(x, mean, yerr=half, fmt="o", color="black", ms=3,
                    capsize=1.5, zorder=4)


def format_axes(ax, data):
    labels = [f"{name}\n$n$ = {len(values)}" for name, values in data.items()]
    ax.set_xticks(range(len(data)), labels=labels)
    ax.set_xlim(-0.6, len(data) - 0.4)
    ax.set_ylabel("Soil respiration (µmol CO$_2$ m$^{-2}$ s$^{-1}$)")


def main():
    rng = np.random.default_rng(12)
    data = samples(rng)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 62 * MM), layout="constrained",
                                 sharey=True)
        boxes(axes[0], data)
        strip(axes[0], data, np.random.default_rng(1))
        strip(axes[1], data, np.random.default_rng(1))  # same jitter in both panels
        mean_interval(axes[1], data)
        for ax in axes:
            format_axes(ax, data)
        axes[1].set_ylabel("")
        axes[0].set_title("a  Points over box plots", loc="left")
        axes[1].set_title("b  Points with mean and 95% interval", loc="left")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
