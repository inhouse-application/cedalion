"""Label runs of months as seasons, with shaded bands (a) or brackets below the axis (b).

Synthetic monthly rainfall; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.transforms import offset_copy

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
MONTHS = np.arange(1, 13)
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# Group label, first month, last month.
GROUPS = [("Dry season", 1, 4), ("Wet season", 5, 9), ("Transition", 10, 12)]
HALF = 0.45  # months a group reaches past its first and last month
BAR_COLOR = "C0"


def rainfall(ax, values):
    ax.bar(MONTHS, values, width=0.6, color=BAR_COLOR, zorder=2)
    ax.set_xticks(MONTHS, labels=MONTH_NAMES)
    ax.set_xlim(0.4, 12.6)


def bands(ax):
    """Shade each group; x in months, y as a fraction of the axes height."""
    blend = ax.get_xaxis_transform()
    for label, first, last in GROUPS:
        ax.axvspan(first - HALF, last + HALF, color="0.92", lw=0, zorder=0)
        ax.text((first + last) / 2, 0.97, label, transform=blend,
                ha="center", va="top", color="0.3")


def brackets(ax, drop=17, tip=2.5):
    """Draw a bracket under each group, `drop` points below the x-axis."""
    below = offset_copy(ax.get_xaxis_transform(), fig=ax.figure,
                        y=-drop, units="points")
    line = {"color": "0.3"}
    for label, first, last in GROUPS:
        left, right = first - HALF, last + HALF
        ax.plot([left, right], [0, 0], transform=below, clip_on=False, **line)
        for end in (left, right):
            ax.annotate("", (end, 0), xycoords=below, xytext=(0, tip),
                        textcoords="offset points",
                        arrowprops={"arrowstyle": "-", "shrinkA": 0,
                                    "shrinkB": 0, **line})
        ax.annotate(label, ((left + right) / 2, 0), xycoords=below,
                    xytext=(0, -2), textcoords="offset points",
                    ha="center", va="top", color="0.3")


def main():
    rng = np.random.default_rng(11)
    values = 40 + 150 * np.exp(-((MONTHS - 7) / 2) ** 2) + rng.normal(0, 8, 12)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, sharey=True, figsize=(width_mm * MM, 62 * MM),
                                 layout="constrained")
        for ax in axes:
            rainfall(ax, values)
        axes[0].set_ylabel("Rainfall (mm)")
        bands(axes[0])
        brackets(axes[1])
        axes[0].set_ylim(0, 220)
        for ax, title in zip(axes, ("a  Bands", "b  Brackets")):
            ax.set_title(title, loc="left")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
