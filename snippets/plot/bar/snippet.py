"""Bar charts: sorted horizontal bars colored by group (a) and signed bars colored by sign (b).
Synthetic predictor importance for a streamflow model and monthly streamflow anomalies."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
GROUP_COLORS = {"Climate": "C0", "Soil": "C1", "Land cover": "C2",
                 "Terrain": "C3"}
# Predictor, group, and share of model skill (%). Shares add to 100.
PREDICTORS = [
    ("Precipitation", "Climate", 31.4), ("Snow fraction", "Climate", 6.2),
    ("Aridity index", "Climate", 14.8), ("Soil depth", "Soil", 4.1),
    ("Clay content", "Soil", 3.0), ("Forest cover", "Land cover", 11.6),
    ("Impervious area", "Land cover", 8.7), ("Mean slope", "Terrain", 9.9),
    ("Elevation", "Terrain", 7.6), ("Drainage density", "Terrain", 2.7),
]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
          "Dec"]
SIGN_COLORS = {"Above normal": "#e08214", "Below normal": "#2c7bb6"}


def sorted_bars(ax):
    """Largest bar at the top; the value printed just past each bar end."""
    ranked = sorted(PREDICTORS, key=lambda p: p[2])  # barh draws the first entry at the bottom
    names = [name for name, _, _ in ranked]
    values = [value for *_, value in ranked]
    colors = [GROUP_COLORS[group] for _, group, _ in ranked]
    bars = ax.barh(names, values, height=0.7, color=colors)
    ax.bar_label(bars, labels=[f"{v:.1f}%" for v in values], padding=2)
    ax.set_xlim(0, 1.15 * max(values))
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Share of model skill (%)")
    handles = [Patch(color=color, label=group) for group, color in GROUP_COLORS.items()]
    ax.legend(handles=handles, loc="lower right", frameon=False, title="Predictor group",
              alignment="left")


def signed_bars(ax, anomaly):
    """Color by sign, with a zero line the bars grow from."""
    colors = [SIGN_COLORS["Above normal" if v >= 0 else "Below normal"] for v in anomaly]
    ax.bar(range(len(MONTHS)), anomaly, width=0.7, color=colors)
    ax.axhline(0, color="0.2")
    ax.set_xticks(range(len(MONTHS)), labels=MONTHS)
    ax.tick_params(axis="x", length=0)
    ax.set_xlim(-0.6, len(MONTHS) - 0.4)
    top = 10 * np.ceil(np.abs(anomaly).max() / 10)
    ax.set_ylim(-top, top)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="0.9")
    ax.set(ylabel="Streamflow anomaly (%)", xlabel="Month (2023)")
    handles = [Patch(color=color, label=label) for label, color in SIGN_COLORS.items()]
    ax.legend(handles=handles, loc="upper right", frameon=False)


def main():
    rng = np.random.default_rng(12)
    season = 28 * np.sin(2 * np.pi * (np.arange(12) - 1.5) / 12)
    anomaly = season + rng.normal(0, 9, 12)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 68 * MM),
                                 gridspec_kw={"width_ratios": [1, 1.2]},
                                 layout="constrained")
        sorted_bars(axes[0])
        signed_bars(axes[1], anomaly)
        for ax, letter in zip(axes, "ab"):
            ax.annotate(letter, xy=(0, 1), xycoords="axes fraction", xytext=(0, 4),
                        textcoords="offset points", fontweight="bold", fontsize="large")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
