"""Several lines, each with a translucent band in its own color.
Synthetic land-surface temperature for four regions; each band is the 10th-90th percentile of 200 draws."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# name: (color, base temperature, slope, highest cover observed)
REGIONS = {
    "Coastal": ("C0", 27, 0.06, 85),
    "Plains": ("C1", 29, 0.09, 95),
    "Highland": ("C2", 22, 0.05, 60),
    "Delta": ("C3", 25, 0.11, 75),
}
BAND_ALPHA = 0.2
EDGE_ALPHA = 0.5  # thin band outline in the line color; 0 removes it


def draw_series(rng, base, slope, top):
    cover = np.linspace(0, top, 60)
    spread = 0.4 + 2.0 * (cover / top) ** 3
    draws = (base + slope * cover + 0.6 * np.sin(cover / 12)
             + rng.normal(0, 1, (200, 1)) * spread)
    low, middle, high = np.percentile(draws, [10, 50, 90], axis=0)
    return cover, low, middle, high


def lines_with_bands(ax, rng):
    curves = {name: draw_series(rng, *spec[1:]) for name, spec in REGIONS.items()}
    # All bands first, then all lines: no band covers another region's line.
    for name, (cover, low, _, high) in curves.items():
        color = REGIONS[name][0]
        ax.fill_between(cover, low, high, color=color, alpha=BAND_ALPHA, linewidth=0)
        for edge in (low, high):
            ax.plot(cover, edge, color=color, alpha=EDGE_ALPHA,
                    lw=0.35 * plt.rcParams["lines.linewidth"])
    for name, (cover, _, middle, _) in curves.items():
        ax.plot(cover, middle, color=REGIONS[name][0], label=name)
    ax.set(xlim=(0, 100), xlabel="Impervious cover (%)",
           ylabel="Land-surface temperature (°C)")
    ax.legend(loc="upper left", frameon=False, ncols=2)


def main():
    rng = np.random.default_rng(14)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, ax = plt.subplots(figsize=(width_mm * MM, 70 * MM), layout="constrained")
        lines_with_bands(ax, rng)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
