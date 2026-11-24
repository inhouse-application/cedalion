"""Stack pairwise comparison brackets above grouped distributions without overlap.
Synthetic leaf nitrogen under four fertiliser levels; p-values from a two-sided permutation test."""

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MM = 1 / 25.4
STYLE_DIR = Path(__file__).resolve().parent / "../../../styles"
# Fertiliser level, sample size, mean and standard deviation of leaf nitrogen (mg/g).
GROUPS = [("Control", 24, 18.0, 2.4), ("Low", 24, 19.4, 2.6),
          ("Medium", 24, 21.0, 2.5), ("High", 24, 23.5, 2.8)]
COLORS = ("0.55", "#8fb3c4", "#4f86a0", "#1d5570")
N_PERMUTATIONS = 9999
STEP = 0.13  # vertical distance between bracket levels, as a fraction of the data range
TIP = 0.25  # bracket tip length, as a fraction of STEP
STARS = ((0.001, "***"), (0.01, "**"), (0.05, "*"))
BRACKET = {"color": "black"}


def permutation_p(a, b, rng):
    """Two-sided permutation p-value for a difference in means."""
    pooled = np.concatenate([a, b])
    observed = abs(a.mean() - b.mean())
    shuffled = rng.permuted(np.tile(pooled, (N_PERMUTATIONS, 1)), axis=1)
    diffs = np.abs(shuffled[:, :a.size].mean(axis=1) - shuffled[:, a.size:].mean(axis=1))
    return (np.sum(diffs >= observed) + 1) / (N_PERMUTATIONS + 1)


def format_p(p):
    """p-value text; at the permutation floor, report an upper bound."""
    floor = 1 / (N_PERMUTATIONS + 1)
    if p <= floor:
        # Mathtext sets the exponent's hyphen as a typographic minus.
        return f"$p$ < 10$^{{{np.log10(floor):.0f}}}$"
    if p < 0.001:
        exponent = int(np.floor(np.log10(p)))
        return f"$p$ = {p / 10**exponent:.1f} × 10$^{{{exponent}}}$"
    return f"$p$ = {p:.3f}" if p < 0.01 else f"$p$ = {p:.2f}"


def format_stars(p):
    return next((stars for limit, stars in STARS if p < limit), "n.s.")


def stack_brackets(pairs, tops, step):
    """Height for each pair; shorter spans are placed first, lower down.

    A bracket sits one step above the highest point it spans and one step above
    every placed bracket that shares a category with it.
    """
    placed = []
    for left, right in sorted(pairs, key=lambda pair: (pair[1] - pair[0], pair[0])):
        height = max(tops[left:right + 1]) + step
        for other_left, other_right, other_height in placed:
            if other_left <= right and left <= other_right:
                height = max(height, other_height + step)
        placed.append((left, right, height))
    return placed


def draw_brackets(ax, samples, pairs, p_values, label):
    """Draw the brackets and return the y limit that leaves room above the highest."""
    tops = [values.max() for values in samples]
    span = max(tops) - min(values.min() for values in samples)
    step = STEP * span
    placed = stack_brackets(pairs, tops, step)
    for left, right, height in placed:
        tip = height - TIP * step
        ax.plot([left, left, right, right], [tip, height, height, tip], **BRACKET)
        ax.annotate(label(p_values[(left, right)]), ((left + right) / 2, height),
                    xytext=(0, 1), textcoords="offset points", ha="center", va="bottom")
    return max(height for *_, height in placed) + step


def draw_groups(ax, samples, rng):
    ax.boxplot(samples, positions=range(len(samples)), widths=0.45, showfliers=False,
               medianprops={"color": "black"})
    for x, (values, color) in enumerate(zip(samples, COLORS)):
        jitter = rng.uniform(-0.12, 0.12, values.size)
        ax.scatter(x + jitter, values, s=4, color=color, linewidths=0, zorder=3)
    ax.set_xticks(range(len(GROUPS)), labels=[name for name, *_ in GROUPS])
    ax.set_xlabel("Fertiliser level")
    ax.set_ylabel("Leaf nitrogen (mg/g)")


def main():
    rng = np.random.default_rng(5)
    samples = [rng.normal(mean, sd, n) for _, n, mean, sd in GROUPS]
    against_control = [(0, 1), (0, 2), (0, 3)]
    neighbors = [(0, 1), (1, 2), (2, 3), (1, 3)]
    p_values = {pair: permutation_p(samples[pair[0]], samples[pair[1]], rng)
                for pair in sorted(set(against_control + neighbors))}
    default = STYLE_DIR / "default.mplstyle"
    sheets = [default] if default.is_file() else []
    if selected := os.environ.get("CEDALION_STYLE"):
        sheet = Path(selected).expanduser()
        sheets.append(sheet if sheet.is_file() else STYLE_DIR / (selected.removesuffix(".mplstyle") + ".mplstyle"))
    width_mm = float(os.environ.get("CEDALION_WIDTH_MM", 183))
    with plt.style.context(sheets):
        fig, axes = plt.subplots(1, 2, sharey=True, figsize=(width_mm * MM, 70 * MM),
                                 layout="constrained")
        tops = []
        for ax, pairs, label, letter in ((axes[0], against_control, format_p, "a"),
                                         (axes[1], neighbors, format_stars, "b")):
            draw_groups(ax, samples, rng)
            tops.append(draw_brackets(ax, samples, pairs, p_values, label))
            ax.annotate(letter, xy=(0, 1), xycoords="axes fraction", xytext=(0, 4),
                        textcoords="offset points", fontweight="bold", fontsize="large")
        # The panels share y, so the taller bracket stack sets the limit for both.
        axes[0].set_ylim(top=max(tops))
        axes[0].set_yticks(np.arange(14, 29, 2))
        for ax in axes:
            ax.spines["left"].set_bounds(ax.get_ylim()[0], 28)
        axes[1].tick_params(labelleft=False)
        axes[1].set_ylabel("")
        fig.savefig(os.environ.get("CEDALION_SNIPPET_PNG", Path(__file__).with_name("snippet.png")), dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
