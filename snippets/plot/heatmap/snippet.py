"""Matrices of cells colored by value: values printed in the cells (a), a symmetric matrix with groups outlined (b).
Synthetic land-cover shares and station correlations."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgb
from matplotlib.patches import Rectangle

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
DISTRICTS = ("North", "Harbor", "Old town", "Riverside", "Airport", "Hills")
COVER = ("Tree", "Grass", "Water", "Built", "Bare")
# Station names grouped by region; the groups are outlined in panel b.
GROUPS = (("Coast", ("C1", "C2", "C3")), ("Valley", ("V1", "V2")),
          ("Upland", ("U1", "U2", "U3")))
SHARE_CMAP = "YlOrBr"
CORR_CMAP = "YlGnBu"
LIGHT_TEXT_ABOVE = 0.55  # luminance of the cell below which its text turns white


def luminance(rgba):
    r, g, b = to_rgb(rgba)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def heatmap(ax, values, rows, cols, cmap, vmin, vmax, fmt=None):
    image = ax.imshow(values, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(cols)), labels=cols)
    ax.set_yticks(range(len(rows)), labels=rows)
    # White gaps between cells; minor ticks sit on the cell edges.
    ax.set_xticks(np.arange(len(cols) + 1) - 0.5, minor=True)
    ax.set_yticks(np.arange(len(rows) + 1) - 0.5, minor=True)
    ax.grid(which="minor", color="white")
    ax.tick_params(which="both", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    if fmt:
        for (i, j), value in np.ndenumerate(values):
            dark = luminance(image.to_rgba(value)) < LIGHT_TEXT_ABOVE
            ax.text(j, i, format(value, fmt), ha="center", va="center",
                    color="white" if dark else "black")
    return image


def outline_blocks(ax, sizes):
    """One rectangle per group on the diagonal of a square matrix."""
    start = 0
    for size in sizes:
        ax.add_patch(Rectangle((start - 0.5, start - 0.5), size, size, fill=False,
                               edgecolor="black", zorder=3,
                               clip_on=False))
        start += size


def land_cover(rng):
    """Whole-number shares (%) of each cover class per district; each row sums to 100."""
    exact = 100 * rng.dirichlet(np.full(len(COVER), 0.7), size=len(DISTRICTS))
    shares = np.floor(exact).astype(int)
    # Largest remainder: give the missing points to the largest fractional parts.
    for row, short in enumerate(100 - shares.sum(1)):
        shares[row, np.argsort(shares[row] - exact[row])[:short]] += 1
    return shares


def station_correlation(rng):
    """Correlation of daily series that share a regional signal within each group."""
    days = 365
    series = []
    for _, names in GROUPS:
        regional = rng.normal(size=days)
        series += [regional + rng.normal(0, 0.6, days) for _ in names]
    common = rng.normal(size=days)
    return np.corrcoef(np.array(series) + common)


def main():
    rng = np.random.default_rng(3)
    names = [name for _, group in GROUPS for name in group]
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 66 * MM), layout="constrained",
                                 width_ratios=(1.1, 1))
        share = heatmap(axes[0], land_cover(rng), DISTRICTS, COVER, SHARE_CMAP, 0, 100,
                        fmt="d")
        axes[0].set_xlabel("Land cover")
        fig.colorbar(share, ax=axes[0], label="Share of district area (%)",
                     aspect=25, pad=0.02)
        corr = heatmap(axes[1], station_correlation(rng), names, names, CORR_CMAP, 0, 1)
        axes[1].set_aspect("equal")
        outline_blocks(axes[1], [len(group) for _, group in GROUPS])
        fig.colorbar(corr, ax=axes[1], label="Pearson correlation of daily rainfall",
                     aspect=25, pad=0.02)
        axes[0].set_title("a  Land-cover share by district", loc="left")
        axes[1].set_title("b  Station correlation, regions outlined", loc="left")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
