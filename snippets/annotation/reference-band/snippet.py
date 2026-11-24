"""Shade the range above a class threshold behind nitrate distributions by land use.

Synthetic well samples for two seasons; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
LOWER, UPPER = 3, 10  # mg/L; class thresholds
BAND_COLOR = "#f2dfd8"
GUIDE = {"color": "0.4", "linestyle": "--"}
USES = ("Forest", "Pasture", "Cropland", "Orchard")
COLORS = ("C0", "C1", "C2", "C3")
# Season -> median nitrate (mg/L) per land use; spread is lognormal.
MEDIANS = {"Spring": (1.5, 3.5, 6.5, 5.0), "Autumn": (1.2, 2.8, 4.5, 4.2)}


def samples(rng, median, n=300):
    return rng.lognormal(np.log(median), 0.6, n)


def draw_season(ax, season, groups, top):
    positions = np.arange(1, len(groups) + 1)
    # axhspan does not follow later limit changes, so set the limit first.
    ax.set_ylim(0, top)
    ax.axhspan(UPPER, top, color=BAND_COLOR, linewidth=0, zorder=0)
    for level, label in ((LOWER, f"{LOWER} mg/L"), (UPPER, f"{UPPER} mg/L")):
        ax.axhline(level, zorder=1, **GUIDE)
        ax.annotate(label, (1, level), xycoords=ax.get_yaxis_transform(),
                    xytext=(-2, 2), textcoords="offset points", ha="right", va="bottom",
                    color="0.3")
    parts = ax.violinplot(groups, positions, widths=0.75, showextrema=False,
                          showmedians=True)
    for body, color in zip(parts["bodies"], COLORS):
        body.set(facecolor=color, edgecolor="none", alpha=1, zorder=2)
    parts["cmedians"].set(color="white", zorder=3)
    for x, values in zip(positions, groups):
        share = 100 * np.mean(values > UPPER)
        ax.annotate(f"{share:.1f}%", (x, values.max()),
                    xytext=(0, 2), textcoords="offset points", ha="center", va="bottom")
    ax.tick_params(axis="x", length=0)
    ax.set_xticks(positions, labels=USES)
    ax.set_xlim(0.45, len(groups) + 0.95)
    ax.set_title(season, loc="left", pad=3)


def main():
    rng = np.random.default_rng(7)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, sharey=True, figsize=(width_mm * MM, 62 * MM),
                                 layout="constrained")
        seasons = {season: [samples(rng, m) for m in medians]
                   for season, medians in MEDIANS.items()}
        top = 5 * np.ceil(max(g.max() for gs in seasons.values() for g in gs) / 5) + 3
        for ax, (season, groups) in zip(axes, seasons.items()):
            draw_season(ax, season, groups, top)
        axes[0].set_ylabel("Nitrate (mg/L)")
        axes[0].text(0.02, 0.97,
                     f"Share of samples above {UPPER} mg/L printed above each group",
                     transform=axes[0].transAxes, ha="left", va="top", color="0.3")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
