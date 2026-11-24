"""Hourly pavement temperatures on a diverging scale centered on a 20 °C baseline.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
BASELINE = 20  # °C
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def pavement_temperatures():
    """Return a week of readings with a daily peak in the afternoon."""
    hours = np.arange(24)
    afternoon = np.array([14, 14, 15, 16, 15, 14, 15])
    peak_rise = np.array([6, 8, 10, 12, 9, 7, 5])
    cycle = np.cos(2 * np.pi * (hours - afternoon[:, None]) / 24)
    warming = peak_rise[:, None] * np.maximum(cycle, 0)
    cooling = 4 * np.minimum(cycle, 0)
    return 20 + warming + cooling


def draw_week(ax, temperatures):
    half = max(BASELINE - temperatures.min(), temperatures.max() - BASELINE)
    norm = Normalize(vmin=BASELINE - half, vmax=BASELINE + half)
    image = ax.imshow(temperatures, norm=norm, cmap="RdBu_r", aspect="auto",
                      interpolation="nearest")
    ax.set_yticks(np.arange(len(DAYS)), labels=DAYS)
    ax.set_xticks([0, 4, 8, 12, 16, 20, 23])
    ax.set_xlabel("Hour of day")
    return image


def main():
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, ax = plt.subplots(figsize=(width_mm * MM, 69 * MM), layout="constrained")
        image = draw_week(ax, pavement_temperatures())
        colorbar = fig.colorbar(image, ax=ax, orientation="vertical", pad=0.025)
        low, high = image.get_clim()
        ticks = np.linspace(low, high, 7)
        labels = [f"{value:g}" for value in ticks]
        labels[len(ticks) // 2] += " (baseline)"
        colorbar.set_ticks(ticks, labels=labels)
        colorbar.set_label("Pavement temperature (°C)")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=600)
        plt.close(fig)


if __name__ == "__main__":
    main()
