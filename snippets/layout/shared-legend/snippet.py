"""Shared legend: one legend below six panels that use the same four colors.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
MODELS = {"Model A": "C0", "Model B": "C1", "Model C": "C2", "Model D": "C3"}
SETTINGS = ["Low", "Mid", "High"]
CATCHMENTS = ["North Fork", "Stony Brook", "Mill River", "Black Creek", "Clearwater", "Red Hollow"]
MISSING = {("North Fork", "Model B")}
WIDTH = 0.2


def draw_catchment(ax, name, rng):
    x = np.arange(len(SETTINGS))
    for i, (model, color) in enumerate(MODELS.items()):
        if (name, model) in MISSING:
            for xi in x + (i - 1.5) * WIDTH:
                ax.text(xi, 0.02, "n/a", rotation=90, ha="center", va="bottom", color="0.4",
                        fontsize="small")
            continue
        score = np.clip(0.6 + 0.07 * i + rng.normal(0, 0.07, x.size), 0, 0.97)
        ax.bar(x + (i - 1.5) * WIDTH, score, width=WIDTH, color=color, label=model)
    ax.set_title(name, loc="left", pad=3)
    ax.set_xticks(x, SETTINGS)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="0.88")


def shared_legend(fig, axes):
    """One legend for all panels, from the labeled artists of every panel."""
    entries = {}
    for ax in axes.flat:
        for handle, label in zip(*ax.get_legend_handles_labels()):
            entries.setdefault(label, handle)
    labels = [m for m in MODELS if m in entries]
    fig.legend([entries[m] for m in labels], labels, loc="outside lower center",
               ncol=len(labels), frameon=False, handlelength=1.2, columnspacing=1.5)


def main():
    rng = np.random.default_rng(8)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(2, 3, sharex=True, sharey=True, figsize=(width_mm * MM, 85 * MM),
                                 layout="constrained")
        for ax, name in zip(axes.flat, CATCHMENTS):
            draw_catchment(ax, name, rng)
        axes[0, 0].set(ylim=(0, 1), yticks=np.linspace(0, 1, 6))
        fig.supylabel("Score (–)", fontsize="medium")
        shared_legend(fig, axes)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
