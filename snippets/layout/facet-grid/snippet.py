"""Facet grid: one panel per pair of levels of two categorical variables.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# (level, growth factor) of the column variable and the row variable
SOILS = [("Sand", 0.7), ("Loam", 1.0), ("Clay", 0.85)]
WATERING = [("Daily", 1.0), ("Weekly", 0.8), ("Fortnightly", 0.55)]
# (herb, color, marker, final height in cm at growth factors 1.0)
HERBS = [("Basil", "C0", "o", 34), ("Thyme", "C1", "s", 22)]
WEEKS = np.arange(1, 9)
STRIP_MM = 4
GAP_MM = 1.5


def draw_cell(ax, soil_factor, water_factor, rng):
    for herb, color, marker, final in HERBS:
        height = final * soil_factor * water_factor * (1 - np.exp(-WEEKS / 2.6))
        height = np.clip(height + rng.normal(0, 0.8, WEEKS.size), 0, None)
        ax.plot(WEEKS, height, color=color, marker=marker, markersize=2.5,
                label=herb)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="0.88")


def row_strip(ax, text):
    """Shaded strip beside the right edge of `ax`, as tall as the panel."""
    fig_width = ax.figure.get_figwidth() / MM
    panel_width = ax.get_position().width * fig_width
    strip = ax.inset_axes([1 + GAP_MM / panel_width, 0, STRIP_MM / panel_width, 1])
    strip.set_facecolor("0.85")
    strip.set_xticks([])
    strip.set_yticks([])
    for spine in strip.spines.values():
        spine.set_visible(False)
    strip.text(0.5, 0.5, text, rotation=-90, ha="center", va="center",
               fontweight="bold", transform=strip.transAxes)


def main():
    rng = np.random.default_rng(3)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(len(WATERING), len(SOILS), sharex=True, sharey=True,
                                 figsize=(width_mm * MM, 110 * MM))
        fig.subplots_adjust(left=0.08, right=0.92, top=0.89, bottom=0.15,
                            hspace=0.15, wspace=0.08)
        for row, (watering, water_factor) in enumerate(WATERING):
            for col, (soil, soil_factor) in enumerate(SOILS):
                draw_cell(axes[row, col], soil_factor, water_factor, rng)
            row_strip(axes[row, -1], watering)
        for ax, (soil, _) in zip(axes[0], SOILS):
            ax.set_title(soil, fontweight="bold", pad=4)

        # The axes are shared, so these limits and ticks apply to every panel.
        first = axes[0, 0]
        first.set_xlim(0.5, 8.5)
        first.set_xticks(WEEKS)
        first.set_ylim(0, 40)
        first.set_yticks([0, 10, 20, 30, 40])
        for ax in axes.flat:
            ax.label_outer()
        fig.supxlabel("Weeks after sowing", y=0.08, fontsize="medium")
        fig.supylabel("Plant height (cm)", x=0.025, fontsize="medium")
        fig.text(0.5, 0.94, "Soil texture", ha="center")
        fig.text(0.975, 0.515, "Watering interval", rotation=-90, ha="center",
                 va="center")

        handles, labels = first.get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=len(HERBS), frameon=False,
                   title="Herb", bbox_to_anchor=(0.5, 0))
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
