"""Logarithmic axes: one log axis with k/M tick labels, and a log-log scatter.

Synthetic data; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
DATA_COLOR = "C0"
GUIDE = {"color": "0.45", "linestyle": "--", "zorder": 1}


def short_number(value, _position=None):
    """10, 100, 1k, 10k, 100k, 1M, ... for decade ticks."""
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if value >= size:
            return f"{value / size:g}{suffix}"
    return f"{value:g}"


def log_x(ax, rng):
    size = np.logspace(3.6, 7.5, 60)
    growth = 0.04 + 0.03 * np.tanh(np.log10(size) - 5) + rng.normal(0, 0.002, size.size)
    ax.plot(size, growth, color=DATA_COLOR)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(short_number))
    ax.set(xlim=(10**3.5, 10**7.6), ylim=(0, 0.09),
           xlabel="Population (log scale)", ylabel="Annual growth rate")


def log_log(ax, rng):
    migration = 10 ** rng.uniform(1.5, 7.5, 300)
    scatter = np.clip(rng.normal(0, 0.35, migration.size), -0.7, 0.7)  # decades
    natural = migration * 10**scatter
    limits = (10**0.5, 10**8.5)
    # Give axline two points: its slope argument is meant for linear scales.
    ax.axline((1, 1), (10, 10), **GUIDE)
    ax.scatter(migration, natural, s=4, color=DATA_COLOR, alpha=0.6, linewidths=0)
    ax.set(xscale="log", yscale="log", xlim=limits, ylim=limits, aspect="equal",
           xlabel="Net migration (people)", ylabel="Natural increase (people)")
    for axis in (ax.xaxis, ax.yaxis):
        # numticks must exceed the decades shown, or matplotlib skips some.
        axis.set_major_locator(LogLocator(base=10, numticks=12))
        axis.set_minor_locator(LogLocator(base=10, subs=np.arange(2, 10), numticks=12))
        axis.set_major_formatter(FuncFormatter(short_number))
        axis.set_minor_formatter(NullFormatter())
    ax.grid(which="major", color="0.9")
    ax.set_axisbelow(True)


def main():
    rng = np.random.default_rng(12)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 70 * MM),
                                 gridspec_kw={"width_ratios": [1.5, 1]},
                                 layout="constrained")
        for ax, axis in ((axes[0], "x"), (axes[1], "x"), (axes[1], "y")):
            ax.tick_params(axis=axis, which="minor", length=0.6 * plt.rcParams[f"{axis}tick.major.size"],
                           width=0.8 * plt.rcParams[f"{axis}tick.major.width"])
        log_x(axes[0], rng)
        log_log(axes[1], rng)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
