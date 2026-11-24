"""Fitted lines over scatter: a straight line and a quadratic, each with its 95% band.

Synthetic data. Writes snippet.png next to this file.
"""

from math import lgamma
import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
GROUPS = {"Group A": "C0", "Group B": "C1"}
FIT = {"color": "black"}
BAND = {"color": "0.55", "alpha": 0.35, "linewidth": 0}


def t_quantile(p, df):
    """Student-t quantile by integrating the density."""
    x = np.linspace(0, 12, 24001)
    log_c = lgamma((df + 1) / 2) - lgamma(df / 2) - 0.5 * np.log(df * np.pi)
    density = np.exp(log_c - (df + 1) / 2 * np.log1p(x**2 / df))
    cdf = 0.5 + np.concatenate([[0], np.cumsum((density[1:] + density[:-1]) / 2
                                               * np.diff(x))])
    return np.interp(p, cdf, x)


def polynomial_fit(x, y, degree, grid):
    """Least-squares polynomial, its R² and the 95% confidence band of the mean."""
    design = np.vander(x, degree + 1)
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ coef
    df = x.size - (degree + 1)
    variance = residual @ residual / df
    covariance = variance * np.linalg.inv(design.T @ design)
    grid_design = np.vander(grid, degree + 1)
    fitted = grid_design @ coef
    se = np.sqrt(np.einsum("ij,jk,ik->i", grid_design, covariance, grid_design))
    half = t_quantile(0.975, df) * se
    r2 = 1 - residual @ residual / np.sum((y - y.mean()) ** 2)
    return coef, fitted, half, r2


def term(value, digits, suffix=""):
    """' + 1.23 x' or ' − 1.23 x' with a true minus sign, for printed equations."""
    return f" {'−' if value < 0 else '+'} {abs(value):.{digits}f}{suffix}"


def scatter_by_group(ax, x, y, group):
    for i, (name, color) in enumerate(GROUPS.items()):
        ax.scatter(x[group == i], y[group == i], s=5, color=color, alpha=0.7,
                   linewidths=0, label=name, zorder=1)


def straight_fit(ax, x, y, group):
    scatter_by_group(ax, x, y, group)
    grid = np.linspace(x.min(), x.max(), 100)
    (slope, intercept), fitted, half, r2 = polynomial_fit(x, y, 1, grid)
    ax.fill_between(grid, fitted - half, fitted + half, zorder=2, **BAND)
    ax.plot(grid, fitted, zorder=3, **FIT)
    ax.text(0.03, 0.97, f"y = {intercept:.2f}{term(slope, 2, ' x')}\n"
            f"n = {x.size}\nR² = {r2:.2f}", transform=ax.transAxes, va="top")
    ax.set(xlabel="Green-space share", ylabel="Cooling (°C)")
    ax.legend(loc="lower right", frameon=False, handletextpad=0.2)


def curved_fit(ax, x, y, group):
    scatter_by_group(ax, x, y, group)
    grid = np.linspace(x.min(), x.max(), 100)
    (a, b, c), fitted, half, r2 = polynomial_fit(x, y, 2, grid)
    ax.fill_between(grid, fitted - half, fitted + half, zorder=2, **BAND)
    ax.plot(grid, fitted, zorder=3, **FIT)
    ax.text(0.03, 0.97, f"y = {c:.2f}{term(b, 3, ' x')}{term(a, 4, ' x²')}\n"
            f"n = {x.size}\nR² = {r2:.2f}", transform=ax.transAxes, va="top")
    ax.set(xlabel="Mean summer temperature (°C)", ylabel="Cooling (°C)")


def main():
    rng = np.random.default_rng(10)
    n = 240
    group = rng.integers(0, 2, n)
    share = np.clip(rng.normal(0.35 + 0.12 * group, 0.12, n), 0.05, 0.75)
    cooling = 0.1 + 8 * share + rng.normal(0, 0.9, n)
    temperature = rng.uniform(12, 34, n)
    cooling_t = 0.5 + 0.32 * temperature - 0.0075 * temperature**2 + rng.normal(0, 0.45, n)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 66 * MM), layout="constrained")
        straight_fit(axes[0], share, cooling, group)
        curved_fit(axes[1], temperature, cooling_t, group)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
