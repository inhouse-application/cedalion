"""Label gains and losses inside diverging bars and net changes at their tips.

Synthetic changes in tree canopy area; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"

DISTRICTS = ("North", "East", "South", "West")
LOSS = np.array([-14, -7, -23, -10])
GAIN = np.array([9, 19, 6, 14])


def signed_labels(values):
    """Use a typographic minus and an explicit plus for positive changes."""
    return [f"{value:+d}".replace("-", "−") for value in values]


def gross_changes(ax):
    for values, fill, ink in ((LOSS, "#dec09b", "black"), (GAIN, "#27637a", "white")):
        bars = ax.barh(DISTRICTS, values, color=fill, height=0.58)
        ax.bar_label(bars, labels=signed_labels(values), label_type="center",
                     color=ink)
    ax.set_title("Canopy loss and gain", loc="left")


def net_changes(ax):
    net = LOSS + GAIN
    bars = ax.barh(DISTRICTS, net, color="#68747b", height=0.58)
    ax.bar_label(bars, labels=signed_labels(net), padding=3)
    ax.set_title("Net canopy change", loc="left")


def main():
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, sharex=True, sharey=True,
                                 figsize=(width_mm * MM, 54 * MM), layout="constrained")
        gross_changes(axes[0])
        net_changes(axes[1])
        axes[0].invert_yaxis()
        limit = 1.18 * max(abs(LOSS.min()), GAIN.max())
        axes[0].set_xlim(-limit, limit)
        fig.get_layout_engine().set(wspace=0.08)
        for ax in axes:
            ax.tick_params(axis="y", length=0)
            ax.spines["left"].set_visible(False)
            ax.axvline(0, color="0.55", zorder=0)
        fig.supxlabel("Area change (ha)", fontsize="medium")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
