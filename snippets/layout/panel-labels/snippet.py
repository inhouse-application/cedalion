"""Label unequal panels at a fixed distance from each axes' upper-left corner.
A synthetic storm shown as streamflow, rainfall and cumulative volume."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import StrMethodFormatter

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"


def panel_label(ax, letter):
    """Anchor to the axes, then apply a physical offset in points."""
    ax.annotate(letter, xy=(0, 1), xycoords="axes fraction",
                xytext=(0, 4), textcoords="offset points",
                ha="left", va="bottom", fontweight="bold", fontsize="large")


def draw_storm(flow_ax, rain_ax, volume_ax):
    hours = np.arange(49)
    rain = np.round(8 * np.exp(-((hours - 13) / 4) ** 2))
    response = hours * np.exp(-hours / 4)
    flow = 3500 + 95 * np.convolve(rain, response)[:len(hours)]
    flow_ax.plot(hours, flow, color="C0")
    flow_ax.set_ylabel("Streamflow (L/s)")
    flow_ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))

    rain_ax.bar(hours, rain, color="#777777", width=0.9)
    rain_ax.set_ylabel("Rainfall (mm/h)")

    # Integrate adjacent hourly flow readings in liters, then convert to ML.
    hourly_volume = (flow[:-1] + flow[1:]) / 2 * 3600 / 1e6
    volume = np.r_[0, np.cumsum(hourly_volume)]
    volume_ax.plot(hours, volume, color="C1")
    volume_ax.set_ylabel("Volume (ML)")

    for ax in (flow_ax, rain_ax, volume_ax):
        ax.set_xlim(0, 48)
        ax.set_xticks([0, 12, 24, 36, 48])
    rain_ax.set_ylim(bottom=0)
    volume_ax.set_ylim(bottom=0)
    flow_ax.set_xlabel("Time since start (h)")
    volume_ax.set_xlabel("Time since start (h)")
    rain_ax.tick_params(labelbottom=False)


def main():
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig = plt.figure(figsize=(width_mm * MM, 78 * MM), layout="constrained")
        grid = fig.add_gridspec(2, 2, width_ratios=(1.7, 1))
        flow_ax = fig.add_subplot(grid[:, 0])
        rain_ax = fig.add_subplot(grid[0, 1])
        volume_ax = fig.add_subplot(grid[1, 1], sharex=rain_ax)
        draw_storm(flow_ax, rain_ax, volume_ax)
        for ax, letter in zip((flow_ax, rain_ax, volume_ax), "abc"):
            panel_label(ax, letter)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
