"""Emphasize one series against muted others, and outline groups of cells in a matrix.
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
MUTED = {"color": "0.75", "zorder": 1}
FOCUS = {"color": "#c2412d", "zorder": 3}
FOCUS_STATION = 4
MONTHS = np.arange(1, 13)
SITES = ("A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2")
GROUP_SIZE = 2  # sites per outlined block on the diagonal


def focus_series(ax, rng):
    anomaly = rng.normal(0, 0.35, (12, MONTHS.size)).cumsum(axis=1) * 0.5
    anomaly[FOCUS_STATION] += np.linspace(0, 2.2, MONTHS.size)
    for station, series in enumerate(anomaly):
        if station != FOCUS_STATION:
            ax.plot(MONTHS, series, lw=0.5 * plt.rcParams["lines.linewidth"], **MUTED)
    # Draw the focus last and on top, so no muted line crosses it.
    ax.plot(MONTHS, anomaly[FOCUS_STATION], lw=2 * plt.rcParams["lines.linewidth"], **FOCUS)
    ax.annotate(f"Station {FOCUS_STATION + 1}", (MONTHS[-1], anomaly[FOCUS_STATION, -1]),
                xytext=(3, 0), textcoords="offset points", va="center",
                color=FOCUS["color"], fontweight="bold", annotation_clip=False)
    ax.annotate("Other 11 stations", (MONTHS[-1], np.median(anomaly[:, -1])),
                xytext=(3, -12), textcoords="offset points", va="center",
                color="0.5", annotation_clip=False)
    ax.axhline(0, color="0.4", zorder=0)
    ax.set(xlim=(1, 12), xticks=MONTHS, xlabel="Month",
           ylabel="Temperature anomaly (°C)")


def outlined_blocks(fig, ax, rng):
    n = len(SITES)
    group = np.arange(n) // GROUP_SIZE
    same = group[:, None] == group[None, :]
    similarity = np.where(same, 0.92, 0.62) + rng.normal(0, 0.05, (n, n))
    similarity = np.clip((similarity + similarity.T) / 2, 0, 1)
    np.fill_diagonal(similarity, 1)
    image = ax.imshow(similarity, cmap="YlGnBu", vmin=0.4, vmax=1.0)
    # Cell edges fall at half-integers in imshow coordinates.
    for start in range(0, n, GROUP_SIZE):
        ax.add_patch(Rectangle((start - 0.5, start - 0.5), GROUP_SIZE, GROUP_SIZE,
                               fill=False, edgecolor="black",
                               clip_on=False))  # the axes would clip the outer edges
    ax.set_xticks(range(n), SITES)
    ax.set_yticks(range(n), SITES)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.colorbar(image, ax=ax, shrink=0.8, aspect=20, label="Similarity")


def main():
    rng = np.random.default_rng(5)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 66 * MM),
                                 gridspec_kw={"width_ratios": [1.5, 1]},
                                 layout="constrained")
        focus_series(axes[0], rng)
        outlined_blocks(fig, axes[1], rng)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
