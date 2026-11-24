"""Callouts with leader lines on a time series and on a scatter.
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
DATA_COLOR = "C0"
MUTED = "0.7"
LEADER = {"arrowstyle": "-|>", "color": "0.15", "mutation_scale": 6,
          "shrinkA": 1, "shrinkB": 2}
BOX = {"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "0.3",
       }
OFFLINE = slice(70, 81)  # days without a reading


def synthetic_data(rng):
    day = np.arange(120)
    flow = (40 + 8 * np.sin(day / 19)
            + 160 * np.exp(-0.5 * ((day - 34) / 2.5) ** 2)
            + 70 * np.exp(-0.5 * ((day - 96) / 3) ** 2)
            + rng.normal(0, 3, day.size))
    flow[OFFLINE] = np.nan
    rain = rng.gamma(2.0, 260, 90) + 300
    runoff = 0.42 * rain + rng.normal(0, 60, rain.size)
    rain[[17, 63]] = [720, 1320]
    runoff[[17, 63]] = [640, 190]
    return day, flow, rain, runoff


def discharge_callouts(ax, day, flow):
    ax.plot(day, flow, color=DATA_COLOR)
    peak = np.nanargmax(flow)
    # xytext is in points from xy, not in data units.
    ax.annotate(f"Storm peak\n{flow[peak]:.0f} m³/s on day {day[peak]}",
                xy=(day[peak], flow[peak]), xytext=(22, -6),
                textcoords="offset points", ha="left", va="top",
                arrowprops={**LEADER, "connectionstyle": "angle3,angleA=0,angleB=90"})
    gap_mid = (OFFLINE.start + OFFLINE.stop - 1) / 2
    ax.annotate("Gauge offline", xy=(gap_mid, np.nanmax(flow[60:70])),
                xytext=(0, 26), textcoords="offset points", ha="center",
                va="bottom", arrowprops=LEADER)
    ax.set(xlim=(0, 119), ylim=(0, 240), xlabel="Day of record",
           ylabel="Discharge (m³/s)")


def outlier_callouts(ax, rain, runoff):
    ax.scatter(rain, runoff, s=6, color=MUTED, linewidths=0)
    targets = {17: ("Site 17", (-34, 4)), 63: ("Site 63", (26, -8))}
    for index, (label, offset) in targets.items():
        ax.scatter(rain[index], runoff[index], s=10, color=DATA_COLOR, zorder=3)
        ax.annotate(label, xy=(rain[index], runoff[index]), xytext=offset,
                    textcoords="offset points", ha="center", va="center",
                    bbox=BOX, arrowprops={**LEADER, "arrowstyle": "-"})
    ax.set(ylim=(0, None), xlabel="Annual rainfall (mm)", ylabel="Annual runoff (mm)")


def main():
    day, flow, rain, runoff = synthetic_data(np.random.default_rng(7))
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 62 * MM),
                                 gridspec_kw={"width_ratios": [1.6, 1]},
                                 layout="constrained")
        discharge_callouts(axes[0], day, flow)
        outlier_callouts(axes[1], rain, runoff)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
