"""Monthly box plots on the left y-axis and a smooth curve on a right y-axis.
a: two unrelated scales. b: two signed scales with their zeros aligned."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgb

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
BOX_COLOR = "C0"
CURVE_COLOR = "C1"
MONTHS = np.arange(1, 13)


def monthly_samples(rng, center, spread):
    """Thirty daily values per month around a seasonal center."""
    return [rng.normal(c, s, 30) for c, s in zip(center, spread)]


def boxes(ax, samples):
    face = tuple(c + (1 - c) * 0.75 for c in to_rgb(BOX_COLOR))
    ax.boxplot(samples, positions=MONTHS, widths=0.6, showfliers=False,
               patch_artist=True,
               boxprops={"facecolor": face, "edgecolor": BOX_COLOR},
               whiskerprops={"color": BOX_COLOR},
               capprops={"color": BOX_COLOR},
               medianprops={"color": BOX_COLOR})
    medians = [np.median(s) for s in samples]
    ax.plot(MONTHS, medians, "-o", color=BOX_COLOR, ms=2)
    ax.set_xticks(MONTHS)
    ax.set_xlim(0.4, 12.6)
    ax.set_xlabel("Month")


def curve(ax, time, values, label):
    right = ax.twinx()
    # The style sheet hides the right spine.
    right.spines["right"].set_visible(True)
    right.plot(time, values, color=CURVE_COLOR)
    right.set_ylabel(label)
    # twinx() draws the new axes last; raise the box axes and clear their background.
    ax.set_zorder(right.get_zorder() + 1)
    ax.patch.set_visible(False)
    return right


def align_zero(left, right):
    """Extend the lower limits so zero sits at the same height on both axes."""
    limits = [axis.get_ylim() for axis in (left, right)]
    below = max(-low / (high - low) for low, high in limits)
    for axis, (low, high) in zip((left, right), limits):
        axis.set_ylim(-below * high / (1 - below), high)


def color_axis(ax, side, color):
    ax.spines[side].set_color(color)
    ax.tick_params(axis="y", colors=color)
    ax.yaxis.label.set_color(color)


def separate_scales(ax, rng):
    center = 30 - 9 * np.cos(2 * np.pi * (MONTHS - 1) / 12)
    boxes(ax, monthly_samples(rng, center, 2 + 0.1 * center))
    ax.set_ylabel("Soil moisture (%)")
    time = np.linspace(0.5, 12.5, 200)
    right = curve(ax, time, 14 - 11 * np.cos(2 * np.pi * (time - 1.5) / 12),
                  "Air temperature (°C)")
    color_axis(ax, "left", BOX_COLOR)
    color_axis(right, "right", CURVE_COLOR)


def shared_zero(ax, rng):
    center = 6 * np.sin(2 * np.pi * (MONTHS - 2) / 12) - 1
    boxes(ax, monthly_samples(rng, center, np.full(12, 2.0)))
    ax.set_ylabel("Soil moisture anomaly (%)")
    time = np.linspace(0.5, 12.5, 200)
    right = curve(ax, time, 2.5 * np.sin(2 * np.pi * (time - 4) / 12) + 0.8,
                  "Air temperature anomaly (°C)")
    align_zero(ax, right)
    ax.axhline(0, color="0.55", ls="--", zorder=0)
    color_axis(ax, "left", BOX_COLOR)
    color_axis(right, "right", CURVE_COLOR)


def main():
    rng = np.random.default_rng(7)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 62 * MM),
                                 layout="constrained")
        separate_scales(axes[0], rng)
        shared_zero(axes[1], rng)
        for ax, title in zip(axes, ("a  Unrelated scales", "b  Zeros aligned")):
            ax.set_title(title, loc="left")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
