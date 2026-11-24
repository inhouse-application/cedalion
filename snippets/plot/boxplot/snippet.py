"""Box plot with the whisker rule fixed in code and drawn in a key beside the plot.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgba

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# (band, stations, mean, spread); mean and spread in days per decade
BANDS = [
    ("<500 m", 48, 1.5, 3.0),
    ("500–1000 m", 62, -0.8, 3.4),
    ("1000–1500 m", 55, -3.1, 3.8),
    ("1500–2000 m", 37, -5.2, 4.4),
    (">2000 m", 21, -6.8, 5.0),
]
WHIS = (5, 95)  # whisker ends, as percentiles
COLOR = "C0"
BOX_WIDTH = 0.55


def box_props(color):
    """Style for one box: pale fill, colored outline and whiskers, dark median."""
    return {
        "patch_artist": True,
        "boxprops": {"facecolor": to_rgba(color, 0.25), "edgecolor": color},
        "medianprops": {"color": "0.1"},
        "whiskerprops": {"color": color},
        "capprops": {"color": color},
        "meanprops": {"marker": "o", "markersize": 2.5, "markerfacecolor": color,
                      "markeredgecolor": "white"},
        "flierprops": {"marker": "o", "markersize": 1.8, "markerfacecolor": "none",
                       "markeredgecolor": color},
    }


def boxplot(ax, samples):
    ax.axhline(0, color="0.4", linestyle=(0, (4, 2)), zorder=0)
    ax.boxplot(samples, positions=range(len(BANDS)), widths=BOX_WIDTH, whis=WHIS,
               showmeans=True, **box_props(COLOR))
    labels = [f"{name}\n$n$ = {values.size}" for (name, *_), values in zip(BANDS, samples)]
    ax.set_xticks(range(len(BANDS)), labels=labels)
    ax.set_xlim(-0.6, len(BANDS) - 0.4)
    ax.set(xlabel="Station elevation", ylabel="Change in snow-cover duration (days/decade)")


def box_key(ax):
    """One example box with each element named, in the same style as the plot."""
    stats = {"whislo": -2.2, "q1": -0.9, "med": -0.1, "mean": 0.45, "q3": 1.0,
             "whishi": 2.3, "fliers": [3.2]}
    ax.bxp([stats], positions=[0], widths=0.5, showmeans=True, **box_props("#7a7a7a"))
    names = [("fliers", "Beyond the whiskers"), ("whishi", f"{WHIS[1]}th percentile"),
             ("q3", "75th percentile"), ("mean", "Mean"), ("med", "Median"),
             ("q1", "25th percentile"), ("whislo", f"{WHIS[0]}th percentile")]
    for key, text in names:
        y = stats[key][0] if key == "fliers" else stats[key]
        ax.annotate(text, xy=(0.3, y), xytext=(0.45, y), va="center",
                    arrowprops={"arrowstyle": "-", "color": "0.5",
                                "shrinkA": 0, "shrinkB": 0})
    ax.set_xlim(-0.4, 1.9)
    ax.set_ylim(-3.0, 3.6)
    ax.axis("off")


def main():
    rng = np.random.default_rng(4)
    samples = [mean + spread * rng.standard_t(5, n) for _, n, mean, spread in BANDS]
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, (ax, key) = plt.subplots(1, 2, figsize=(width_mm * MM, 70 * MM),
                                      gridspec_kw={"width_ratios": [4, 1]},
                                      layout="constrained")
        boxplot(ax, samples)
        box_key(key)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
