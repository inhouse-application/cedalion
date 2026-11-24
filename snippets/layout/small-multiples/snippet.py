"""Small multiples: daily temperatures at six sites on shared axes with one legend.
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# Site name, daily mean temperature (°C), and daily amplitude (°C).
SITES = [
    ("Lakeshore", 18, 3), ("Floodplain", 20, 6), ("Meadow", 19, 8),
    ("Orchard", 17, 5), ("Foothills", 15, 6), ("Plateau", 13, 9),
]


def draw_site(ax, name, mean, amplitude):
    hours = np.arange(25)
    cycle = np.cos(2 * np.pi * (hours - 15) / 24)
    clear = mean + amplitude * cycle
    overcast = mean - 1 + 0.45 * amplitude * cycle
    ax.plot(hours, clear, color="C0", label="Clear sky")
    ax.plot(hours, overcast, color="C1",
            linestyle="--", label="Overcast")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="0.88")
    ax.set_title(name, loc="left", pad=3)


def main():
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(2, 3, sharex=True, sharey=True,
                                 figsize=(width_mm * MM, 88 * MM))
        for ax, (name, mean, amplitude) in zip(axes.flat, SITES):
            draw_site(ax, name, mean, amplitude)
            ax.set_xlabel("Local hour")
            ax.set_ylabel("Air temperature (°C)")
            ax.label_outer()

        first = axes[0, 0]
        first.set_xlim(0, 24)
        first.set_xticks([0, 6, 12, 18, 24])
        first.set_ylim(0, 30)
        first.set_yticks([0, 10, 20, 30])
        handles, labels = first.get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", ncol=2, frameon=False)
        fig.subplots_adjust(left=0.07, right=0.985, top=0.89, bottom=0.12,
                            hspace=0.26, wspace=0.12)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
