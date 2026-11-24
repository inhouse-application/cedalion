"""Donut chart: parts of a whole as a ring (a), and as an inset key to a bar chart (b).
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
SECTORS = {"Irrigation": "C0", "Industry": "C1", "Households": "C2",
           "Power plants": "C3"}
# User: (sector, withdrawal in million m³)
USERS = {
    "Rice": ("Irrigation", 410), "Orchards": ("Irrigation", 160),
    "Vegetables": ("Irrigation", 95), "Chemicals": ("Industry", 120),
    "Paper": ("Industry", 70), "Food processing": ("Industry", 45),
    "Urban homes": ("Households", 150), "Rural homes": ("Households", 40),
    "Thermal cooling": ("Power plants", 55), "Hydro losses": ("Power plants", 15),
}
RING = 0.38  # ring width as a fraction of the radius
INSIDE_ABOVE = 8  # shares (%) at or above this are printed inside the ring


def whole_percent(values):
    """Percentages rounded to whole numbers that add up to 100 (largest remainder)."""
    exact = 100 * np.asarray(values, float) / np.sum(values)
    shares = np.floor(exact).astype(int)
    shares[np.argsort(shares - exact)[:100 - shares.sum()]] += 1
    return shares


def sector_totals():
    return {s: sum(v for sector, v in USERS.values() if sector == s) for s in SECTORS}


def donut(ax, values, colors, labels=None, center=None, radius=1.0):
    """Segments start at 12 o'clock and run clockwise, in the order given."""
    wedges, _ = ax.pie(values, colors=colors, radius=radius, startangle=90,
                       counterclock=False,
                       wedgeprops={"width": RING * radius, "edgecolor": "white"})
    if labels:
        for wedge, label, share in zip(wedges, labels, whole_percent(values)):
            angle = np.radians((wedge.theta1 + wedge.theta2) / 2)
            direction = np.array([np.cos(angle), np.sin(angle)])
            outside = label
            if share >= INSIDE_ABOVE:
                x, y = (1 - RING / 2) * radius * direction
                ax.text(x, y, f"{share}%", ha="center", va="center", color="white",
                        fontweight="bold")
            else:
                outside = f"{label} {share}%"
            x, y = 1.08 * radius * direction
            ax.text(x, y, outside, va="center", ha="left" if x > 0 else "right")
    if center:
        ax.text(0, 0, center, ha="center", va="center")
    ax.set_aspect("equal")
    return wedges


def bars_with_inset(ax):
    names = list(USERS)[::-1]
    sectors = [USERS[n][0] for n in names]
    values = np.array([USERS[n][1] for n in names])
    order = np.argsort(values)  # barh draws the first bar at the bottom
    ax.barh(np.arange(len(names)), values[order],
            color=[SECTORS[sectors[i]] for i in order], height=0.7)
    ax.set_yticks(np.arange(len(names)), labels=[names[i] for i in order])
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Withdrawal (million m³ per year)")
    ax.set_xlim(0, 1.05 * values.max())
    inset = ax.inset_axes((0.5, 0.03, 0.42, 0.55))  # x, y, w, h in axes fraction
    totals = sector_totals()
    wedges = donut(inset, list(totals.values()), list(SECTORS.values()),
                   center="Sector\nshare")
    for wedge, name in zip(wedges, totals):
        angle = np.radians((wedge.theta1 + wedge.theta2) / 2)
        x, y = 1.15 * np.cos(angle), 1.15 * np.sin(angle)
        inset.text(x, y, name, va="center", ha="left" if x > 0 else "right")


def main():
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 72 * MM), layout="constrained",
                                 width_ratios=(1, 1.25))
        totals = sector_totals()
        donut(axes[0], list(totals.values()), list(SECTORS.values()),
              labels=list(totals), center=f"{sum(totals.values()):}\nmillion m³")
        axes[0].set_title("a  Water withdrawal by sector", loc="left")
        bars_with_inset(axes[1])
        axes[1].set_title("b  Withdrawal by user, sector share inset", loc="left")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
