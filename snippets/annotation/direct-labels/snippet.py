"""Name each series at its data instead of in a legend: line ends and bar ends.
Synthetic built-up area by district and green-space share by city."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
YEARS = np.arange(2000, 2025)
DISTRICTS = {  # name: (color, start, yearly growth)
    "North": ("C0", 32, 0.9),
    "Harbor": ("C1", 41, 0.35),
    "East": ("C2", 30, 0.75),
    "Old Town": ("C3", 46, 0.05),
    "South": ("C4", 22, 0.95),
}
CITIES = ("Arden", "Belmont", "Corrin", "Dunmore", "Elsby", "Fenwick", "Galloway",
          "Hartley")
LABEL_GAP = 7  # minimum distance between label centers, points


def spread(values, gap):
    """Move sorted positions apart until neighbors are at least gap apart."""
    order = np.argsort(values)
    placed = np.array(values, float)[order]
    for _ in range(50):
        moved = False
        for i in range(1, placed.size):
            overlap = gap - (placed[i] - placed[i - 1])
            if overlap > 1e-9:
                placed[i - 1] -= overlap / 2
                placed[i] += overlap / 2
                moved = True
        if not moved:
            break
    result = np.empty_like(placed)
    result[order] = placed
    return result


def labeled_lines(ax, rng):
    ends = {}
    for name, (color, start, growth) in DISTRICTS.items():
        area = start + growth * (YEARS - YEARS[0]) + rng.normal(0, 0.5, YEARS.size)
        ax.plot(YEARS, area, color=color)
        ends[name] = area[-1]
    ax.set(xlim=(YEARS[0], YEARS[-1]), ylim=(15, 60), xlabel="Year",
           ylabel="Built-up area (%)")
    # Convert the gap from points to data units with the final axes height.
    ax.figure.canvas.draw()
    height_pt = ax.get_window_extent().height * 72 / ax.figure.dpi
    gap = LABEL_GAP * np.ptp(ax.get_ylim()) / height_pt
    label_y = spread(list(ends.values()), gap)
    for (name, end), y in zip(ends.items(), label_y):
        ax.annotate(name, xy=(YEARS[-1], end), xytext=(YEARS[-1] + 0.6, y),
                    color=DISTRICTS[name][0], va="center", ha="left",
                    annotation_clip=False,
                    arrowprops={"arrowstyle": "-", "color": DISTRICTS[name][0],
                                "shrinkA": 0, "shrinkB": 1})


def labeled_bars(ax, rng):
    share = np.sort(rng.uniform(8, 38, len(CITIES)))
    bars = ax.barh(np.arange(len(CITIES)), share, height=0.7, color="C0")
    ax.bar_label(bars, labels=CITIES, padding=2)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlim(0, 1.25 * share.max())
    ax.set_xlabel("Green-space share (%)")


def main():
    rng = np.random.default_rng(11)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 62 * MM),
                                 gridspec_kw={"width_ratios": [1.5, 1]})
        # Fixed margins: constrained layout would resize the axes after the labels are placed.
        fig.subplots_adjust(left=0.06, right=0.97, bottom=0.17, top=0.96, wspace=0.3)
        labeled_lines(axes[0], rng)
        labeled_bars(axes[1], rng)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
