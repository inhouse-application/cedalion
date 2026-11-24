"""Number the months on a seasonal loop, outside the line, with error bars.
Synthetic monthly stream temperature and dissolved oxygen for two streams."""

import os
from pathlib import Path

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
LINE_COLOR = "C0"
LABEL_COLOR = "#9a3d12"
OFFSET = 7       # first distance from point to label center (points)
LABEL_GAP = 9    # smallest distance between two label centers (points)
CLEARANCE = 5    # smallest distance from a label center to the line (points)
LEADER_FROM = 14  # draw a leader line when a label ends farther away (points)
# Stream name, summer warming (°C), spring oxygen peak (mg/L) and how tightly
# the winter months bunch together (a higher power gives a tighter cluster).
STREAMS = (("Upland stream", 14, 1.4, 2), ("Lowland stream", 17, 0.5, 4))


def monthly_means(warming, bloom, bunching):
    """Return water temperature and dissolved oxygen with their spreads."""
    phase = 2 * np.pi * np.arange(12) / 12
    summer = (1 - np.cos(phase)) / 2  # 0 in January, 1 in July
    temperature = 3 + warming * summer ** bunching
    oxygen = 13.5 - 0.3 * temperature + bloom * np.sin(phase - 0.6)
    return temperature, oxygen, 0.4 + 0.06 * temperature, 0.25 + 0.03 * temperature


def to_points(ax, x, y):
    """Data coordinates to page coordinates in points."""
    pixels = ax.transData.transform(np.column_stack([x, y]))
    return pixels * 72 / ax.figure.dpi


def outward_normals(xy):
    """Unit normals of a closed path, pointing out of the loop."""
    tangent = np.roll(xy, -1, axis=0) - np.roll(xy, 1, axis=0)
    normal = np.column_stack([tangent[:, 1], -tangent[:, 0]])
    x, y = xy.T
    area = np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y) / 2
    normal *= np.sign(area)  # right of the tangent is outside for a counter-clockwise loop
    return normal / np.linalg.norm(normal, axis=1, keepdims=True)


def spread_labels(xy, normals, steps=300):
    """Start labels on the normals, then push them off each other and the line."""
    labels = xy + OFFSET * normals
    ring = np.r_[xy, xy[:1]]
    fractions = np.linspace(0, 1, 20, endpoint=False)[:, None, None]
    line = (ring[:-1] + fractions * np.diff(ring, axis=0)).reshape(-1, 2)
    for _ in range(steps):
        push = np.zeros_like(labels)
        for obstacles, distance in ((labels, LABEL_GAP), (line, CLEARANCE)):
            apart = labels[:, None, :] - obstacles[None, :, :]
            length = np.linalg.norm(apart, axis=2)
            close = (length < distance) & (length > 1e-9)
            overlap = np.where(close, distance - length, 0)
            push += np.sum(apart / np.maximum(length, 1e-9)[..., None]
                           * overlap[..., None], axis=1)
        if not push.any():
            break
        labels += 0.3 * push
    return labels


def draw_stream(ax, name, warming, bloom, bunching):
    temperature, oxygen, x_spread, y_spread = monthly_means(warming, bloom,
                                                           bunching)
    ax.errorbar(temperature, oxygen, xerr=x_spread, yerr=y_spread, fmt="none",
                ecolor="0.6", capsize=0, zorder=1)
    ax.plot(np.r_[temperature, temperature[0]], np.r_[oxygen, oxygen[0]],
            color=LINE_COLOR, zorder=2)
    ax.scatter(temperature, oxygen, s=6, color=LINE_COLOR, zorder=3)
    ax.set_title(name, loc="left")
    return temperature, oxygen


def number_months(ax, x, y):
    xy = to_points(ax, x, y)
    labels = spread_labels(xy, outward_normals(xy))
    halo = [pe.withStroke(linewidth=plt.rcParams["lines.linewidth"], foreground="white")]
    for month, point, label, xi, yi in zip(range(1, 13), xy, labels, x, y):
        offset = label - point
        leader = None
        if np.hypot(*offset) > LEADER_FROM:
            leader = {"arrowstyle": "-", "color": LABEL_COLOR,
                      "shrinkA": 1, "shrinkB": 2}
        ax.annotate(str(month), (xi, yi), xytext=offset,
                    textcoords="offset points", ha="center", va="center",
                    color=LABEL_COLOR, fontweight="bold", path_effects=halo,
                    arrowprops=leader, zorder=4)


def main():
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, sharex=True, sharey=True,
                                 figsize=(width_mm * MM, 70 * MM))
        fig.subplots_adjust(left=0.07, right=0.985, top=0.9, bottom=0.14,
                            wspace=0.12)
        loops = [draw_stream(ax, *stream) for ax, stream in zip(axes, STREAMS)]
        axes[0].set(xlim=(0, 22), ylim=(6, 14), xticks=np.arange(0, 21, 5))
        # Limits and layout are final here, so transData gives page positions.
        for ax, (x, y) in zip(axes, loops):
            number_months(ax, x, y)
            ax.set_xlabel("Water temperature (°C)")
        axes[0].set_ylabel("Dissolved oxygen (mg/L)")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
