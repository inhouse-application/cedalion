"""Network graph without a graph library: force-directed layout (a), two-layer graph (b).
Synthetic data. Writes snippet.png next to this file.
"""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
GROUPS = {"Coastal": "C0", "Inland": "C1", "Mountain": "C2"}
PER_GROUP = 8
LINK_WITHIN, LINK_BETWEEN = 0.45, 0.025  # probability of an edge
ITERATIONS = 500
# Panel b: clusters in each year and the pairs that overlap in space.
YEAR_1 = ("A", "B", "C", "D")
YEAR_2 = ("P", "Q", "R", "S")
OVERLAPS = (("A", "P"), ("B", "P"), ("C", "Q"), ("D", "R"), ("D", "S"))
COMPONENT_COLORS = ("C0", "C1", "C2", "C3")  # mixed 70% with white when drawn
NODE_COLOR = "#4a4a4a"


def random_graph(rng):
    """Symmetric weight matrix with dense links within groups and few between them."""
    groups = np.repeat(np.arange(len(GROUPS)), PER_GROUP)
    n = len(groups)
    same = groups[:, None] == groups[None, :]
    linked = rng.random((n, n)) < np.where(same, LINK_WITHIN, LINK_BETWEEN)
    weights = np.triu(linked, 1) * rng.uniform(0.2, 1.0, (n, n))
    return weights + weights.T, groups


def force_layout(weights, rng, iterations=ITERATIONS):
    """Fruchterman-Reingold: all nodes repel, linked nodes attract; the step cools."""
    n = len(weights)
    k = 1 / np.sqrt(n)  # ideal edge length on a unit square
    position = rng.random((n, 2))
    step = 0.1
    for _ in range(iterations):
        delta = position[:, None, :] - position[None, :, :]
        distance = np.maximum(np.linalg.norm(delta, axis=2), 1e-3)
        force = k**2 / distance**2 - weights * distance / k  # along delta, per unit
        np.fill_diagonal(force, 0)
        move = (delta * force[:, :, None]).sum(axis=1)
        length = np.maximum(np.linalg.norm(move, axis=1, keepdims=True), 1e-9)
        position += move / length * np.minimum(length, step)
        step *= 0.99
    position -= position.mean(axis=0)
    return position / np.abs(position).max()


def edge_width(weight):
    """Line width for a link weight, in the network and in its key."""
    return (0.2 + weight) * plt.rcParams["lines.linewidth"]


def network(ax, weights, groups, position):
    rows, cols = np.nonzero(np.triu(weights))
    for i, j in zip(rows, cols):
        ax.plot(*position[[i, j]].T, color="0.55", lw=edge_width(weights[i, j]),
                solid_capstyle="round", zorder=1)
    degree = (weights > 0).sum(axis=1)
    colors = np.array(list(GROUPS.values()))[groups]
    ax.scatter(*position.T, s=node_area(degree), c=colors, edgecolors="white",
               zorder=2)
    # adjustable="datalim" changes the data limits, not the axes box.
    ax.set_aspect("equal", adjustable="datalim")
    ax.margins(0.08)
    ax.axis("off")
    handles = [Line2D([], [], ls="", marker="o", ms=5, mfc=c, mec="white")
               for c in GROUPS.values()]
    labels = list(GROUPS)
    for d in (2, 5, 8):
        handles.append(Line2D([], [], ls="", marker="o", ms=np.sqrt(node_area(d)),
                              mfc="0.6", mec="white"))
        labels.append(f"{d} links")
    for w in (0.2, 1.0):
        handles.append(Line2D([], [], color="0.55", lw=edge_width(w)))
        labels.append(f"Weight {w:.1f}")
    ax.legend(handles, labels, loc="upper left", bbox_to_anchor=(1.0, 1.0),
              frameon=False, title="Station group, links, weight", alignment="left",
              labelspacing=0.7)


def node_area(degree):
    """Marker area (pt²) for a node with this many links."""
    return 8 + 7 * np.asarray(degree)


def components(nodes, edges):
    """Connected components by union-find; returns a list of node lists."""
    parent = {node: node for node in nodes}

    def root(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for a, b in edges:
        parent[root(a)] = root(b)
    groups = {}
    for node in nodes:
        groups.setdefault(root(node), []).append(node)
    return list(groups.values())


def convex_hull(points):
    """Monotone chain; returns hull vertices in order (two points stay two points)."""
    points = sorted(map(tuple, points))
    if len(points) < 3:
        return points

    def turn(o, a, b):  # z of the cross product (a - o) x (b - o)
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def half(sequence):
        chain = []
        for p in sequence:
            while len(chain) >= 2 and turn(chain[-2], chain[-1], p) <= 0:
                chain.pop()
            chain.append(p)
        return chain[:-1]

    return half(points) + half(points[::-1])


def two_layer(ax):
    position = {name: (k, 1.0) for k, name in enumerate(YEAR_1)}
    position |= {name: (k, 0.0) for k, name in enumerate(YEAR_2)}
    pale = [tuple(0.3 * c + 0.7 for c in to_rgb(color)) for color in COMPONENT_COLORS]
    for color, members in zip(pale, components(position, OVERLAPS)):
        hull = convex_hull([position[m] for m in members])
        # A thick stroke with round joins pads the hull around the nodes; a hull
        # of two nodes becomes a capsule.
        ax.add_patch(Polygon(hull, closed=True, facecolor=color, edgecolor=color,
                             linewidth=26, joinstyle="round", capstyle="round", zorder=0))
    for a, b in OVERLAPS:
        ax.plot(*zip(position[a], position[b]), color="black", zorder=1)
    for names in (YEAR_1, YEAR_2):
        xy = np.array([position[n] for n in names])
        ax.scatter(*xy.T, s=130, color=NODE_COLOR, edgecolors="white",
                   zorder=2)
        for name, (x, y) in zip(names, xy):
            ax.text(x, y, name, ha="center", va="center", color="white",
                    fontweight="bold", zorder=3)
    for label, y in (("Clusters, year 1", 1.0), ("Clusters, year 2", 0.0)):
        ax.text(-0.55, y, label, ha="right", va="center")
    ax.set(xlim=(-2.2, len(YEAR_1) - 0.4), ylim=(-0.45, 1.45))
    ax.axis("off")


def main():
    rng = np.random.default_rng(21)
    weights, groups = random_graph(rng)
    position = force_layout(weights, rng)
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, figsize=(width_mm * MM, 72 * MM), layout="constrained",
                                 width_ratios=(1.2, 1))
        network(axes[0], weights, groups, position)
        two_layer(axes[1])
        axes[0].set_title("a  Force-directed layout", loc="left")
        axes[1].set_title("b  Two-layer graph, connected components shaded", loc="left")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
