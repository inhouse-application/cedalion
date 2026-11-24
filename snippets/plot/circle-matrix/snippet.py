"""Matrices of circles colored by a correlation, with a thick outline where it is significant.
Synthetic bird counts and habitat attributes; Spearman correlation and a Fisher z test."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
ATTRIBUTES = ("Canopy cover", "Shrub density", "Distance to water", "Elevation",
              "Patch area", "Road density", "Noise level", "Soil moisture")
SPECIES = ("Wren", "Finch", "Thrush", "Swift")
SEASONS = (("Spring", 60), ("Summer", 25), ("Winter", 40))  # name, number of sites
# Four classes on each side of zero; |rho| > 0.8 goes to the end triangles.
BREAKS = np.linspace(-0.8, 0.8, 9)
# One color per class plus one for each open end.
CMAP = ListedColormap(plt.get_cmap("PuOr_r")(np.linspace(0, 1, len(BREAKS) + 1)))
NORM = BoundaryNorm(BREAKS, CMAP.N, extend="both")
CIRCLE = 85  # marker area (pt²)


def outline(significant):
    """Edge width per circle: heavy where significant, thin elsewhere."""
    return plt.rcParams["lines.linewidth"] * np.where(significant, 1, 0.3)


def spearman(x, y):
    """Spearman's rho between every column of x and every column of y."""
    rx = np.argsort(np.argsort(x, axis=0), axis=0)
    ry = np.argsort(np.argsort(y, axis=0), axis=0)
    rx = (rx - rx.mean(0)) / rx.std(0)
    ry = (ry - ry.mean(0)) / ry.std(0)
    return rx.T @ ry / len(x)


def significant(rho, n, z_crit=1.96):
    """Two-sided test at 5 % with Fisher's z; depends on n, not only on rho."""
    return np.abs(np.arctanh(rho)) * np.sqrt(n - 3) > z_crit


def survey(rng, n):
    """Habitat attributes and species counts at n sites, linked by fixed weights."""
    weights = np.array([[0.8, 0.2, 0.6, -0.3], [0.5, 0.6, 0.1, -0.2],
                        [-0.4, -0.1, -0.5, 0.3], [0.1, -0.5, 0.2, 0.4],
                        [0.6, 0.0, 0.4, 0.1], [-0.6, -0.3, -0.4, 0.2],
                        [-0.5, -0.4, -0.2, 0.0], [0.3, 0.1, 0.5, -0.4]])
    habitat = rng.normal(size=(n, len(ATTRIBUTES)))
    counts = rng.poisson(np.exp(1.5 + 0.7 * habitat @ weights
                                + rng.normal(0, 0.4, (n, len(SPECIES)))))
    return habitat, counts


def circle_matrix(ax, rho, mask):
    rows, cols = np.indices(rho.shape)
    points = ax.scatter(cols.ravel(), rows.ravel(), c=rho.ravel(), cmap=CMAP, norm=NORM,
                        s=CIRCLE, edgecolors="black",
                        linewidths=outline(mask.ravel()))
    ax.tick_params(length=0)
    ax.set_xticks(range(len(SPECIES)), labels=SPECIES)
    ax.set_yticks(range(len(ATTRIBUTES)), labels=ATTRIBUTES)
    ax.set_xlim(-0.6, len(SPECIES) - 0.4)
    ax.set_ylim(len(ATTRIBUTES) - 0.5, -0.5)  # first attribute at the top
    return points


def outline_legend(ax):
    """Legend for the two outline widths."""
    handles = [Line2D([], [], linestyle="", marker="o", markersize=7,
                      markerfacecolor="0.85", markeredgecolor="black",
                      markeredgewidth=outline(flag)) for flag in (True, False)]
    ax.legend(handles, ["p < 0.05", "p ≥ 0.05"], title="Correlation (Fisher z test)",
              loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=2,
              frameon=False, columnspacing=2)


def main():
    rng = np.random.default_rng(5)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, len(SEASONS), sharey=True,
                                 figsize=(width_mm * MM, 76 * MM), layout="constrained")
        for ax, (season, n), letter in zip(axes, SEASONS, "abc"):
            rho = spearman(*survey(rng, n))
            points = circle_matrix(ax, rho, significant(rho, n))
            ax.set_title(f"{letter}  {season} ($n$ = {n} sites)", loc="left")
        outline_legend(axes[1])
        colorbar = fig.colorbar(points, ax=axes, extend="both", aspect=30, pad=0.02)
        colorbar.set_ticks(BREAKS)
        colorbar.set_label("Spearman's rank correlation, count vs attribute")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
