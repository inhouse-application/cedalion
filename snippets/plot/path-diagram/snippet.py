"""Variables as boxes joined by arrows labeled with standardized path coefficients.

Synthetic data fitted by least squares; writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
N = 300
# name: (x, y) center in diagram units; the canvas is 10 wide and 6 high.
NODES = {
    "Rainfall": (1.6, 5.0),
    "Air temperature": (5.0, 5.0),
    "Household income": (8.4, 5.0),
    "Tree cover": (3.0, 2.8),
    "Water area": (7.0, 2.8),
    "Surface cooling": (5.0, 0.7),
}
BOX = (2.0, 0.75)  # width and height of a box in diagram units
# Each endogenous variable and the variables with a path into it.
MODEL = {
    "Tree cover": ("Rainfall", "Air temperature", "Household income"),
    "Water area": ("Rainfall", "Air temperature", "Household income"),
    "Surface cooling": ("Tree cover", "Water area", "Rainfall"),
}
COVARIANCE = (("Rainfall", "Air temperature"),)  # drawn double-headed
CURVED = {("Rainfall", "Surface cooling"): 0.6}  # arc3 radius for paths that pass a box
# Where each label sits along its path (0 = source, 1 = target); default LABEL_AT.
LABEL_AT = 0.4
LABEL_ALONG = {("Rainfall", "Water area"): 0.25, ("Household income", "Tree cover"): 0.25,
               ("Rainfall", "Air temperature"): 0.5}
POSITIVE, NEGATIVE, NOT_SIGNIFICANT = "#3b62c4", "#c8402f", "0.55"
WIDTH_PER_UNIT = 3  # stroke widths per unit of |coefficient|
T_CRIT = 1.96  # two-sided 5 % on the normal approximation


def standardize(values):
    return (values - values.mean()) / values.std()


def survey(rng):
    """Standardized synthetic data with fixed links between the variables."""
    rain = rng.normal(size=N)
    temperature = 0.4 * rain + 0.9 * rng.normal(size=N)
    income = rng.normal(size=N)
    trees = 0.5 * rain - 0.35 * temperature + 0.25 * income + 0.8 * rng.normal(size=N)
    water = 0.35 * rain + 0.05 * income + 0.9 * rng.normal(size=N)
    cooling = 0.55 * trees + 0.3 * water - 0.15 * rain + 0.6 * rng.normal(size=N)
    names = list(NODES)
    columns = (rain, temperature, income, trees, water, cooling)
    return {name: standardize(column) for name, column in zip(names, columns)}


def fit_paths(data):
    """Standardized coefficients, t values and R² from one least-squares fit per equation."""
    paths, r2 = {}, {}
    for target, sources in MODEL.items():
        x = np.column_stack([data[s] for s in sources])
        y = data[target]
        beta, *_ = np.linalg.lstsq(x, y, rcond=None)
        residual = y - x @ beta
        variance = residual @ residual / (N - len(sources) - 1)
        se = np.sqrt(np.diag(variance * np.linalg.inv(x.T @ x)))
        for source, b, s in zip(sources, beta, se):
            paths[source, target] = (b, b / s)
        r2[target] = 1 - residual.var() / y.var()
    for a, b in COVARIANCE:
        r = np.corrcoef(data[a], data[b])[0, 1]
        paths[a, b] = (r, r * np.sqrt((N - 2) / (1 - r ** 2)))
    return paths, r2


def boxes(ax, r2):
    patches = {}
    w, h = BOX
    for name, (x, y) in NODES.items():
        endogenous = name in r2
        patch = FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="square,pad=0",
                               facecolor="0.88" if endogenous else "white",
                               edgecolor="black", zorder=3)
        ax.add_patch(patch)
        label = f"{name}\n$R^2$ = {r2[name]:.2f}" if endogenous else name
        ax.text(x, y, label, ha="center", va="center", fontweight="bold", zorder=4)
        patches[name] = patch
    return patches


def label_point(start, end, rad, along=0.5):
    """A point on the arrow: the straight line, or the arc3 curve with radius rad."""
    start, end = np.asarray(start), np.asarray(end)
    chord = end - start
    control = (start + end) / 2 + rad * np.array([chord[1], -chord[0]])
    t = along
    return (1 - t) ** 2 * start + 2 * t * (1 - t) * control + t ** 2 * end


def coefficient_text(value):
    """Two decimals with a true minus sign, and no '−0.00'."""
    text = f"{value:.2f}"
    return "0.00" if float(text) == 0 else text.replace("-", "\u2212")


def path_diagram(ax, paths, r2):
    patches = boxes(ax, r2)
    for (source, target), (coef, t) in paths.items():
        significant = abs(t) > T_CRIT
        color = (POSITIVE if coef > 0 else NEGATIVE) if significant else NOT_SIGNIFICANT
        width = plt.rcParams["lines.linewidth"] * max(WIDTH_PER_UNIT * abs(coef), 0.4)
        rad = CURVED.get((source, target), 0.0)
        double = (source, target) in COVARIANCE
        arrow = FancyArrowPatch(
            NODES[source], NODES[target], patchA=patches[source], patchB=patches[target],
            shrinkA=1, shrinkB=1, connectionstyle=f"arc3,rad={rad}",
            arrowstyle="<|-|>" if double else "-|>", mutation_scale=5 + 1.5 * width,
            color=color, linewidth=width, linestyle="-" if significant else (0, (3, 2)),
            zorder=2)
        ax.add_patch(arrow)
        along = LABEL_ALONG.get((source, target), LABEL_AT)
        x, y = label_point(NODES[source], NODES[target], rad, along)
        ax.text(x, y, coefficient_text(coef), ha="center", va="center", fontweight="bold",
                bbox={"boxstyle": "square,pad=0.15", "facecolor": "white",
                      "edgecolor": "none"}, zorder=5)
    ax.set(xlim=(0, 10), ylim=(0, 5.6))
    ax.set_aspect("equal")
    ax.axis("off")


def key(ax):
    handles = [Line2D([], [], color=POSITIVE),
               Line2D([], [], color=NEGATIVE),
               Line2D([], [], color=NOT_SIGNIFICANT, ls=(0, (3, 2)))]
    ax.legend(handles, ["Positive, p < 0.05", "Negative, p < 0.05", "p ≥ 0.05"],
              loc="lower left", bbox_to_anchor=(0.0, 0.0), frameon=False,
              title="Standardized coefficient", alignment="left")


def main():
    rng = np.random.default_rng(4)
    paths, r2 = fit_paths(survey(rng))
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, ax = plt.subplots(figsize=(width_mm * MM, 105 * MM), layout="constrained")
        path_diagram(ax, paths, r2)
        key(ax)
        ax.text(10, 0.05, f"$n$ = {N}; width ∝ |coefficient|", ha="right", va="bottom")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
