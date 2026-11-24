"""Split violin plot: two conditions as the left and right halves of one violin per category.

Synthetic stream samples in two seasons; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
COVERS = ["Peatland", "Forest", "Grassland", "Cropland", "Urban"]
# Condition, color, side (-1 left, +1 right), and log-normal median (mg/L) per cover.
CONDITIONS = [
    ("Spring", "C0", -1, [18.0, 7.5, 4.0, 3.2, 5.5]),
    ("Autumn", "C1", +1, [26.0, 10.0, 4.6, 4.4, 5.0]),
]
SPREAD = 0.35  # log-normal sigma
N = 80  # samples per cover and condition
HALF_WIDTH = 0.42  # widest half across the whole plot, in category units


def kernel_density(values, grid):
    """Gaussian kernel density with Silverman's bandwidth."""
    spread = min(values.std(ddof=1), np.subtract(*np.percentile(values, [75, 25])) / 1.34)
    bandwidth = 0.9 * spread * values.size ** (-1 / 5)
    z = (grid[:, None] - values[None, :]) / bandwidth
    return np.exp(-0.5 * z**2).sum(axis=1) / (values.size * bandwidth * np.sqrt(2 * np.pi))


def half_outlines(samples):
    """Grid and density for every half, cut at the observed range.

    The density is estimated on log10 values to match the log y-axis; the grid is
    returned in data units.
    """
    outlines = {}
    for key, values in samples.items():
        logs = np.log10(values)
        grid = np.linspace(logs.min(), logs.max(), 200)
        outlines[key] = (10**grid, kernel_density(logs, grid))
    return outlines


def split_violin(ax, samples):
    outlines = half_outlines(samples)
    # One scale for all halves: the highest density anywhere gets HALF_WIDTH.
    scale = HALF_WIDTH / max(density.max() for _, density in outlines.values())
    for condition, color, side, _ in CONDITIONS:
        for x, cover in enumerate(COVERS):
            grid, density = outlines[condition, cover]
            width = side * scale * density
            ax.fill_betweenx(grid, x, x + width, color=color, alpha=0.75, linewidth=0)
            values = samples[condition, cover]
            for q, style in ((25, (0, (2, 1))), (50, "-"), (75, (0, (2, 1)))):
                y = np.percentile(values, q)
                ax.plot([x, x + np.interp(y, grid, width)], [y, y], color="0.1",
                        linewidth=plt.rcParams["lines.linewidth"] * (1 if q == 50 else 0.5), linestyle=style)
    ax.set_xticks(range(len(COVERS)), labels=COVERS)
    ax.tick_params(axis="x", length=0)
    ax.set_xlim(-0.6, len(COVERS) - 0.4)
    ax.set_yscale("log")
    ticks = [1, 2, 5, 10, 20, 50]
    ax.set_yticks(ticks, labels=[str(t) for t in ticks])
    ax.set_ylim(1, 60)
    ax.set(xlabel="Land cover", ylabel="Dissolved organic carbon (mg/L)")
    handles = [Patch(color=color, alpha=0.75, label=f"{condition} ($n$ = {N} per cover)")
               for condition, color, _, _ in CONDITIONS]
    handles.append(plt.Line2D([], [], color="0.1", label="Median"))
    handles.append(plt.Line2D([], [], color="0.1", linestyle=(0, (2, 1)),
                              lw=0.5 * plt.rcParams["lines.linewidth"], label="Quartiles"))
    ax.legend(handles=handles, loc="upper right", frameon=False)


def main():
    rng = np.random.default_rng(17)
    samples = {(condition, cover): rng.lognormal(np.log(median), SPREAD, N)
               for condition, _, _, medians in CONDITIONS
               for cover, median in zip(COVERS, medians)}
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, ax = plt.subplots(figsize=(width_mm * MM, 70 * MM), layout="constrained")
        split_violin(ax, samples)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
