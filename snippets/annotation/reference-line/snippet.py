"""Mark a set point, an intervention time and 1:1 agreement with labeled lines.

Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
GUIDE = {"color": "0.45", "linestyle": "--", "zorder": 1}
DATA_COLOR = "C0"
SET_POINT = 20
START_HOUR = 8


def heating_record(ax, hour, measured):
    ax.axhline(SET_POINT, **GUIDE)
    ax.axvline(START_HOUR, **GUIDE)
    ax.annotate(f"Set point ({SET_POINT} °C)", (0.02, SET_POINT),
                xycoords=ax.get_yaxis_transform(), xytext=(0, 3),
                textcoords="offset points", ha="left", va="bottom")
    ax.annotate("Heating starts", (START_HOUR, 0.97),
                xycoords=ax.get_xaxis_transform(), xytext=(3, 0),
                textcoords="offset points", ha="left", va="top")
    ax.plot(hour, measured, "-o", color=DATA_COLOR, ms=2.5, zorder=2)
    ax.set(xlim=(0, 24), ylim=(14, 22), xlabel="Time (h)",
           ylabel="Measured temperature (°C)", xticks=np.arange(0, 25, 4))


def agreement(ax, measured, model):
    limits = (14, 22)
    ax.axline((0, 0), slope=1, **GUIDE)
    ax.set(xlim=limits, ylim=limits, aspect="equal",
           xlabel="Measured temperature (°C)", ylabel="Model temperature (°C)")
    ax.annotate("1:1 agreement", (21.7, 21.7), xytext=(0, 3),
                textcoords="offset points", rotation=45, rotation_mode="anchor",
                ha="right", va="bottom")
    ax.scatter(measured, model, s=12, color=DATA_COLOR, zorder=2)


def main():
    rng = np.random.default_rng(3)
    hour = np.arange(25)
    elapsed = np.maximum(hour - START_HOUR, 0)
    model = SET_POINT - 4 * np.exp(-elapsed / 4)
    measured = model + rng.normal(0, 0.32, len(hour))
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 66 * MM),
                                 gridspec_kw={"width_ratios": [1.7, 1]},
                                 layout="constrained")
        heating_record(axes[0], hour, measured)
        agreement(axes[1], measured, model)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=600)
        plt.close(fig)


if __name__ == "__main__":
    main()
