"""Partial dependence on one predictor with ICE curves (a–c) and on two at once (d).
A fixed function stands in for a fitted model."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
N = 600
# column: axis label
FEATURES = {
    "tree": "Tree cover (%)",
    "impervious": "Impervious surface (%)",
    "elevation": "Elevation (m)",
}
GRID = 40  # grid points per predictor
GRID_PERCENTILES = (2, 98)  # grid range, as percentiles of the observed values
ICE_SHOWN = 60  # ICE curves drawn per panel
BOOTSTRAPS = 300
SUPPORT = 0.06  # d: hide cells with no observation within this fraction of each range
PDP_COLOR = "C0"
ICE_COLOR = "0.75"


def sample(rng):
    """Correlated predictors: more impervious surface where there is less tree cover."""
    tree = np.clip(rng.gamma(2.0, 12.0, N), 0, 90)
    impervious = np.clip(80 - 0.8 * tree + rng.normal(0, 12, N), 0, 100)
    elevation = rng.uniform(20, 400, N)
    return {"tree": tree, "impervious": impervious, "elevation": elevation}


def model(data):
    """Stand-in for a fitted model: land surface temperature (°C) in summer."""
    tree, impervious, elevation = data["tree"], data["impervious"], data["elevation"]
    cooling = 7.0 / (1 + np.exp(-(tree - 30) / 7))
    heating = 0.08 * impervious * (1 - tree / 120)
    return 38 - cooling + heating - 0.008 * elevation


def grid_for(values):
    return np.linspace(*np.percentile(values, GRID_PERCENTILES), GRID)


def ice(data, feature, grid):
    """Prediction for every row (rows) with the feature set to each grid value (columns)."""
    curves = np.empty((N, len(grid)))
    for k, value in enumerate(grid):
        curves[:, k] = model({**data, feature: np.full(N, value)})
    return curves


def partial_dependence(ax, data, feature, rng):
    grid = grid_for(data[feature])
    curves = ice(data, feature, grid)
    shown = rng.choice(N, ICE_SHOWN, replace=False)
    ax.plot(grid, curves[shown].T, color=ICE_COLOR, alpha=0.7, lw=0.25 * plt.rcParams["lines.linewidth"])
    resampled = curves[rng.integers(0, N, (BOOTSTRAPS, N))].mean(axis=1)
    low, high = np.percentile(resampled, (2.5, 97.5), axis=0)
    ax.fill_between(grid, low, high, color=PDP_COLOR, alpha=0.25, lw=0)
    ax.plot(grid, curves.mean(axis=0), color=PDP_COLOR)
    # Rug of observed values; y is in axes fraction.
    ax.plot(data[feature], np.zeros(N), "|", color="black", ms=3,
            transform=ax.get_xaxis_transform())
    ax.set_xlabel(FEATURES[feature])


def supported(gx, gy, x, y):
    """True for grid cells with at least one observation within SUPPORT of each range."""
    span_x, span_y = gx[-1] - gx[0], gy[-1] - gy[0]
    dx = (gx[None, :, None] - x[None, None, :]) / span_x
    dy = (gy[:, None, None] - y[None, None, :]) / span_y
    return (np.hypot(dx, dy) < SUPPORT).any(axis=2)


def partial_dependence_2d(ax, data, first="tree", second="impervious"):
    gx, gy = grid_for(data[first]), grid_for(data[second])
    xx, yy = np.meshgrid(gx, gy)
    surface = np.empty_like(xx)
    for (i, j), _ in np.ndenumerate(xx):
        surface[i, j] = model({**data, first: np.full(N, xx[i, j]),
                               second: np.full(N, yy[i, j])}).mean()
    surface = np.ma.masked_where(~supported(gx, gy, data[first], data[second]), surface)
    mesh = ax.pcolormesh(gx, gy, surface, cmap="YlOrRd", shading="nearest",
                         rasterized=True)
    lines = ax.contour(gx, gy, surface, levels=np.arange(30, 46, 2), colors="black")
    ax.clabel(lines, fmt="%d", fontsize="small", inline_spacing=2)
    ax.scatter(data[first], data[second], s=0.5, color="0.2", linewidths=0, alpha=0.6)
    ax.set(xlim=(gx[0], gx[-1]), ylim=(gy[0], gy[-1]),
           xlabel=FEATURES[first], ylabel=FEATURES[second])
    return mesh


def main():
    rng = np.random.default_rng(8)
    data = sample(rng)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 4, figsize=(width_mm * MM, 56 * MM), layout="constrained",
                                 width_ratios=(1, 1, 1, 1.25))
        for ax, feature, letter in zip(axes[:3], FEATURES, "abc"):
            partial_dependence(ax, data, feature, rng)
            ax.set_title(letter, loc="left", fontweight="bold")
        for ax in axes[1:3]:
            ax.sharey(axes[0])
            ax.tick_params(labelleft=False)
        axes[0].set_ylabel("Predicted surface temperature (°C)")
        mesh = partial_dependence_2d(axes[3], data)
        axes[3].set_title("d", loc="left", fontweight="bold")
        colorbar = fig.colorbar(mesh, ax=axes[3], aspect=25, pad=0.02)
        colorbar.set_label("Predicted surface temperature (°C)")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
