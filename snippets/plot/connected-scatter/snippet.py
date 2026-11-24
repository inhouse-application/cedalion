"""Join twelve monthly points in order, close the loop and mark its direction.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTH_CMAP = ListedColormap(plt.get_cmap("twilight")(np.arange(12) / 12))
MONTH_NORM = BoundaryNorm(np.arange(0.5, 13), MONTH_CMAP.N)
# Lake name and response time to air temperature (months).
LAKES = (("Deep lake", 1.6), ("Shallow lake", 0.6))
ARROW_EVERY = 1  # draw a direction arrow on every n-th segment


def seasonal_cycle(time, response):
    """Air temperature and lake-minus-air difference for a lagged lake."""
    omega = 2 * np.pi / 12
    air = 10 - 11 * np.cos(omega * (time - 0.6))
    gain = 1 / np.hypot(1, omega * response)
    lag = np.arctan(omega * response) / omega
    lake = 11 - 11 * gain * np.cos(omega * (time - 0.6 - lag))
    return air, lake - air


def closed(values):
    """Repeat the first value so the path returns from December to January."""
    return np.r_[values, values[:1]]


def direction_arrows(ax, x, y):
    """Place an arrowhead at the middle of each segment, pointing forward."""
    for i in range(0, len(x) - 1, ARROW_EVERY):
        start = np.array([x[i], y[i]])
        step = np.array([x[i + 1], y[i + 1]]) - start
        ax.annotate("", xy=start + 0.56 * step, xytext=start + 0.44 * step,
                    arrowprops={"arrowstyle": "-|>", "color": "black",
                                "mutation_scale": 6,
                                "shrinkA": 0, "shrinkB": 0},
                    zorder=2)


def draw_lake(ax, name, response):
    month = np.arange(1, 13)
    air, difference = seasonal_cycle(month - 0.5, response)
    ax.plot(closed(air), closed(difference), color="black",
            zorder=1)
    direction_arrows(ax, closed(air), closed(difference))
    points = ax.scatter(air, difference, c=month, cmap=MONTH_CMAP,
                        norm=MONTH_NORM, s=22, edgecolor="black",
                        zorder=3)

    time = np.linspace(0, 12, 241)
    air, difference = seasonal_cycle(time, 2 * response)
    ax.plot(air, difference, color="0.4", linestyle="--",
            zorder=1)

    ax.axhline(0, color="0.75", zorder=0)
    ax.set_title(name, loc="left")
    ax.set_xlabel("Air temperature (°C)")
    return points


def main():
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, sharex=True, sharey=True,
                                 figsize=(width_mm * MM, 72 * MM),
                                 layout="constrained")
        for ax, (name, response) in zip(axes, LAKES):
            points = draw_lake(ax, name, response)
        axes[0].set_ylabel("Lake minus air temperature (°C)")
        # Build the handles by hand: a scatter handle would take January's fill.
        handles = [
            Line2D([], [], color="black", marker="o",
                   markersize=4, markerfacecolor="0.7",
                   markeredgecolor="black"),
            Line2D([], [], color="0.4", linestyle="--"),
        ]
        axes[0].legend(handles, ["Monthly mean", "Response time doubled"],
                       loc="lower left", frameon=False)
        colorbar = fig.colorbar(points, ax=axes, aspect=30, pad=0.02)
        colorbar.set_ticks(np.arange(1, 13), labels=MONTHS)
        colorbar.ax.tick_params(which="both", length=0)
        colorbar.ax.invert_yaxis()
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
