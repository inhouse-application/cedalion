"""A table drawn as a graphic: grouped rows, with two columns shaded by value.
Synthetic validation scores of three products at five stations."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.colors import ListedColormap, Normalize, to_rgb
from matplotlib.patches import Rectangle

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
STATIONS = ("Lindenberg", "Payerne", "Cabauw", "Sodankylä", "Izaña")
PRODUCTS = ("Satellite", "Reanalysis", "Merged")
# column: (header, left edge, width) in table units; the table is 100 wide.
COLUMNS = {
    "station": ("Station", 0, 22),
    "product": ("Product", 22, 22),
    "n": ("$N$", 44, 14),
    "r": ("$R$", 58, 21),
    "error": ("MAPE (%)", 79, 21),
}
# Shaded columns: color map, value range, and number format.
SHADING = {"r": ("Greys", (0.4, 1.0), "{:.2f}"), "error": ("Oranges", (0, 80), "{:.0f}")}
SHADE_TOP = 0.6  # use only the light part of each map, so black text stays readable
ROW_HEIGHT = 1.0
DARK_TEXT_BELOW = 0.5  # cell luminance below which the text turns white


def luminance(color):
    r, g, b = to_rgb(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def scores(rng):
    """One row per station and product: sample size, correlation and error."""
    rows = []
    for station in STATIONS:
        n = int(rng.integers(40, 160))
        for k, product in enumerate(PRODUCTS):
            r = np.clip(rng.normal(0.62 + 0.1 * k, 0.07), 0.4, 0.97)
            error = np.clip(rng.normal(55 - 10 * k, 12), 12, 78)
            rows.append({"station": station, "product": product, "n": n, "r": r,
                         "error": error})
    return rows


def cell_text(ax, column, row_y, text, **kwargs):
    _, left, width = COLUMNS[column]
    ax.text(left + width / 2, row_y, text, ha="center", va="center", **kwargs)


def table_graphic(ax, rows):
    maps = {}
    for key, (name, limits, _) in SHADING.items():
        light = ListedColormap(plt.get_cmap(name)(np.linspace(0, SHADE_TOP, 256)))
        maps[key] = ScalarMappable(Normalize(*limits), light)
    for i, row in enumerate(rows):
        y = -(i + 0.5) * ROW_HEIGHT
        first_of_group = i % len(PRODUCTS) == 0
        if first_of_group:
            cell_text(ax, "station", y, row["station"], fontweight="bold")
        cell_text(ax, "product", y, row["product"])
        cell_text(ax, "n", y, str(row["n"]))
        for key, (_, _, fmt) in SHADING.items():
            _, left, width = COLUMNS[key]
            color = maps[key].to_rgba(row[key])
            ax.add_patch(Rectangle((left, y - ROW_HEIGHT / 2), width, ROW_HEIGHT,
                                   facecolor=color, edgecolor="none", zorder=0))
            text_color = "white" if luminance(color) < DARK_TEXT_BELOW else "black"
            cell_text(ax, key, y, fmt.format(row[key]), color=text_color)
        # Rule above each row: solid between stations, dotted within a station.
        top = -i * ROW_HEIGHT
        if i == 0 or first_of_group:
            weight = 1 if i == 0 else 0.5
            ax.axhline(top, color="black", lw=weight * plt.rcParams["lines.linewidth"])
        else:
            ax.plot([COLUMNS["product"][1], 100], [top, top], color="0.5",
                    ls=(0, (1, 2)))
    for header, left, width in COLUMNS.values():
        ax.text(left + width / 2, 0.6 * ROW_HEIGHT, header, ha="center", va="center",
                fontweight="bold")
    bottom = -len(rows) * ROW_HEIGHT
    ax.axhline(bottom, color="black")
    ax.set(xlim=(0, 100), ylim=(bottom - 2.7 * ROW_HEIGHT, 1.2 * ROW_HEIGHT))
    ax.axis("off")
    return maps, bottom


def shading_keys(ax, maps, bottom):
    """A small color bar under each shaded column."""
    for key, mappable in maps.items():
        _, left, width = COLUMNS[key]
        cax = ax.inset_axes((left + 0.1 * width, bottom - 1.6 * ROW_HEIGHT,
                             0.8 * width, 0.45 * ROW_HEIGHT), transform=ax.transData)
        bar = ax.figure.colorbar(mappable, cax=cax, orientation="horizontal")
        bar.ax.tick_params(pad=1)
        bar.set_ticks(np.linspace(mappable.norm.vmin, mappable.norm.vmax, 3))


def main():
    rng = np.random.default_rng(6)
    rows = scores(rng)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, ax = plt.subplots(figsize=(width_mm * MM, 76 * MM), layout="constrained")
        maps, bottom = table_graphic(ax, rows)
        shading_keys(ax, maps, bottom)
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
