"""Scatter plot of many points in one call and shuffled order, colored by group (a) and by a third variable (b).
Synthetic half-hourly sap flux against vapour pressure deficit for three tree species."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgba

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# Species, color, number of half-hours, and maximum sap flux (g m⁻² s⁻¹).
SPECIES = [
    ("Beech", "C0", 1100, 52),
    ("Oak", "C1", 700, 38),
    ("Pine", "C2", 900, 30),
]
SIZE = 3  # marker area in points²
ALPHA = 0.5
LIMITS = {"x": (0, 4), "y": (0, 80)}  # same in both panels; checked in scatter()


def synthetic(rng):
    """x: VPD (kPa), y: sap flux, moisture: soil moisture (m³/m³), group: species index."""
    parts = []
    for i, (_, _, n, top) in enumerate(SPECIES):
        vpd = rng.gamma(2.2, 0.4, n)
        moisture = rng.uniform(0.08, 0.38, n)
        flux = top * (1 - np.exp(-vpd / 0.7)) * np.clip((moisture - 0.05) / 0.2, 0.2, 1)
        parts.append((vpd, flux * rng.lognormal(0, 0.15, n), moisture, np.full(n, i)))
    x, y, moisture, group = (np.concatenate(p) for p in zip(*parts))
    # One random order for all points, so neither panel draws one group last.
    order = rng.permutation(x.size)
    return x[order], y[order], moisture[order], group[order]


def scatter(ax, x, y, colors, **kwargs):
    """All points in a single call; rasterized only affects vector (PDF/SVG) output."""
    # Fixed limits drop points without warning; fail instead.
    inside = ((x >= LIMITS["x"][0]) & (x <= LIMITS["x"][1])
              & (y >= LIMITS["y"][0]) & (y <= LIMITS["y"][1]))
    if not inside.all():
        raise ValueError(f"{(~inside).sum()} points fall outside LIMITS")
    points = ax.scatter(x, y, c=colors, s=SIZE, linewidths=0, rasterized=True, **kwargs)
    ax.set(xlim=LIMITS["x"], ylim=LIMITS["y"], xlabel="Vapour pressure deficit (kPa)",
           ylabel="Sap flux density (g m$^{-2}$ s$^{-1}$)")
    return points


def main():
    rng = np.random.default_rng(5)
    x, y, moisture, group = synthetic(rng)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, sharey=True, figsize=(width_mm * MM, 70 * MM),
                                 layout="constrained")
        # a: color per point from its group, alpha baked into the color.
        colors = [to_rgba(SPECIES[g][1], ALPHA) for g in group]
        scatter(axes[0], x, y, colors)
        # scatter in one call returns no per-group artists; draw empty ones for the legend.
        for name, color, n, _ in SPECIES:
            axes[0].scatter([], [], s=12, color=color, linewidths=0,
                            label=f"{name} ($n$ = {n})")
        axes[0].legend(loc="upper left", frameon=False, handletextpad=0.2)
        points = scatter(axes[1], x, y, moisture, cmap="viridis_r", vmin=0.05, vmax=0.4,
                         alpha=0.7)
        bar = fig.colorbar(points, ax=axes[1], shrink=0.8, aspect=25, pad=0.02)
        bar.set_label("Soil moisture (m$^3$ m$^{-3}$)")
        bar.solids.set_alpha(1)
        axes[1].set_ylabel("")
        for ax, letter in zip(axes, "ab"):
            ax.annotate(letter, xy=(0, 1), xycoords="axes fraction", xytext=(0, 4),
                        textcoords="offset points", fontweight="bold", fontsize="large")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
