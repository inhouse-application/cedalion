"""Beeswarm plot: every point shown, moved sideways just enough that no two markers overlap.

Synthetic fish lengths (a) and model effects (b); writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# a: stream, number of fish, and mean and spread of length (cm).
STREAMS = [
    ("Alder Brook", 45, 21, 3.0),
    ("Birch Creek", 80, 18, 2.6),
    ("Cedar Run", 60, 24, 3.6),
    ("Dove Burn", 30, 16, 2.2),
]
COLOR_A = "C0"
# b: predictor, and how strongly its value drives the effect (mm).
PREDICTORS = [("Precipitation", 9.0), ("Snow fraction", 5.0), ("Forest cover", -4.0),
              ("Mean slope", 3.0), ("Clay content", -1.5), ("Elevation", 0.8)]
N_EFFECT = 80  # catchments in b
SIZE = {"a": 6, "b": 3}  # marker area in points², per panel
GAP = 0.15  # extra space between markers, in points
LIMITS = {"length": (8, 36), "effect": (-5, 5)}


def swarm(values, diameter):
    """Sideways offsets (same units as values) so no two circles of `diameter` overlap.

    Points are placed from the smallest value up, each at the offset nearest the center line
    that clears every placed point within one diameter along the value axis.
    """
    order = np.argsort(values)
    offsets = np.zeros(values.size)
    placed = []
    for i in order:
        near = [j for j in placed if abs(values[i] - values[j]) < diameter]
        candidates = [0.0]
        for j in near:
            step = np.sqrt(diameter**2 - (values[i] - values[j]) ** 2)
            candidates += [offsets[j] - step, offsets[j] + step]
        for c in sorted(candidates, key=abs):
            if all((c - offsets[j]) ** 2 + (values[i] - values[j]) ** 2 >= diameter**2 - 1e-9
                   for j in near):
                offsets[i] = c
                break
        placed.append(i)
    return offsets


def points_per_unit(ax, axis):
    """Length in points of one data unit along x or y, from the drawn axes size."""
    box = ax.get_window_extent()
    lo, hi = ax.get_xlim() if axis == "x" else ax.get_ylim()
    pixels = box.width if axis == "x" else box.height
    return pixels * 72 / ax.figure.dpi / (hi - lo)


def vertical_swarms(ax, samples):
    """Called after the layout is fixed, so the scale in points is final."""
    diameter = np.sqrt(SIZE["a"]) + GAP
    y_scale, x_scale = points_per_unit(ax, "y"), points_per_unit(ax, "x")
    widest = 0
    for x, values in enumerate(samples):
        offsets = swarm(values * y_scale, diameter) / x_scale
        widest = max(widest, np.abs(offsets).max())
        ax.scatter(x + offsets, values, s=SIZE["a"], color=COLOR_A, linewidths=0)
        ax.plot([x - 0.3, x + 0.3], [np.median(values)] * 2, color="0.1")
    return widest


def effect_rows(ax, effects, feature):
    diameter = np.sqrt(SIZE["b"]) + GAP
    x_scale, y_scale = points_per_unit(ax, "x"), points_per_unit(ax, "y")
    widest = 0
    for row, (values, colors) in enumerate(zip(effects, feature)):
        offsets = swarm(values * x_scale, diameter) / y_scale
        widest = max(widest, np.abs(offsets).max())
        points = ax.scatter(values, row + offsets, s=SIZE["b"], c=colors, cmap="viridis",
                            vmin=0, vmax=1, linewidths=0)
    return points, widest


def main():
    rng = np.random.default_rng(6)
    lengths = [rng.normal(mean, spread, n) for _, n, mean, spread in STREAMS]
    feature = rng.random((len(PREDICTORS), N_EFFECT))  # predictor value as a 0–1 rank
    effects = [strength * (f - 0.5) + rng.normal(0, 0.4, N_EFFECT)
               for (_, strength), f in zip(PREDICTORS, feature)]
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 72 * MM),
                                 gridspec_kw={"width_ratios": [1, 1.3]},
                                 layout="constrained")
        a, b = axes
        # Everything that changes the axes size comes first: labels, limits, color bar.
        a.set_xticks(range(len(STREAMS)),
                     labels=[f"{name}\n$n$ = {n}" for name, n, *_ in STREAMS])
        a.tick_params(axis="x", length=0)
        a.set(xlim=(-0.6, len(STREAMS) - 0.4), ylim=LIMITS["length"],
              ylabel="Fork length (cm)")
        b.set_yticks(range(len(PREDICTORS)), labels=[name for name, _ in PREDICTORS])
        b.tick_params(axis="y", length=0)
        b.set(xlim=LIMITS["effect"], ylim=(len(PREDICTORS) - 0.5, -0.5),
              xlabel="Effect on predicted annual runoff (mm)")
        b.axvline(0, color="0.5", zorder=0)
        mappable = plt.cm.ScalarMappable(cmap="viridis")
        bar = fig.colorbar(mappable, ax=b, shrink=0.7, aspect=25, pad=0.02, ticks=[0, 1])
        bar.ax.set_yticklabels(["Low", "High"])
        bar.set_label("Predictor value")
        for ax, letter in zip(axes, "ab"):
            ax.annotate(letter, xy=(0, 1), xycoords="axes fraction", xytext=(0, 4),
                        textcoords="offset points", fontweight="bold", fontsize="large")
        fig.canvas.draw()  # run the layout, so the axes sizes in points are final
        widest_a = vertical_swarms(a, lengths)
        _, widest_b = effect_rows(b, effects, feature)
        # A swarm wider than half the category spacing runs into its neighbor.
        if max(widest_a, widest_b) > 0.5:
            raise ValueError(f"Swarm half-width {max(widest_a, widest_b):.2f} exceeds 0.5; "
                             "reduce SIZE or the number of points")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
