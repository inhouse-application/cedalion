"""Color measures, and a look at colors under normal vision, deuteranopia and protanopia.

Usage: python tools/color.py view COLOR [...] [--out PNG]
       COLOR is a hex value, a Matplotlib color sequence or colormap ("okabe_ito",
       "cmc.batlowS"), or "tol.<scheme>" from styles/cedalion.tokens.json.
       Prints the CAM02-UCS distance of the closest pair under each vision; a continuous
       colormap is only drawn (seven samples), since its pairs depend on the sampling.
"""

from __future__ import annotations

import argparse
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

VISIONS = ("normal", "deuteranopia", "protanopia")


def rgb(colors) -> np.ndarray:
    """sRGB in 0–1 from hex strings or RGB(A) tuples."""
    from matplotlib.colors import to_rgb

    return np.array([to_rgb(c) for c in colors], dtype=float).reshape(-1, 3)


def luminance(values: np.ndarray) -> np.ndarray:
    """WCAG relative luminance of sRGB values in 0–1."""
    linear = np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)
    return linear @ [0.2126, 0.7152, 0.0722]


def simulate(values: np.ndarray) -> list[np.ndarray]:
    """sRGB as seen under each of VISIONS."""
    from colorspacious import cspace_convert

    return [values] + [np.clip(cspace_convert(values, {"name": "sRGB1+CVD", "cvd_type": kind, "severity": 100},
                                              "sRGB1"), 0, 1)
                       for kind in ("deuteranomaly", "protanomaly")]


def distances(values: np.ndarray) -> np.ndarray:
    """Pairwise CAM02-UCS distances under each of VISIONS: shape (3, n, n)."""
    from colorspacious import cspace_convert

    v = np.stack([cspace_convert(s, "sRGB1", "CAM02-UCS") for s in simulate(values)])
    return np.linalg.norm(v[:, :, None] - v[:, None], axis=-1)


def colors(name: str) -> list[str]:
    """Hex values of a named scheme, or the name itself when it is a color."""
    import matplotlib
    from matplotlib.colors import is_color_like, to_hex

    if name.startswith("tol."):
        try:
            from tools import tokens
        except ImportError:  # run as python tools/color.py
            import tokens
        return [h for _, h in tokens.palettes(tokens.load())[name]]
    if name.startswith("cmc."):
        import cmcrameri.cm  # noqa: F401  registers the cmc.* names
    if name in matplotlib.color_sequences:
        return [to_hex(c) for c in matplotlib.color_sequences[name]]
    if name in matplotlib.colormaps:
        cmap = matplotlib.colormaps[name]
        return [to_hex(c) for c in (cmap(np.linspace(0, 1, 7)) if sampled(name) else cmap.colors)]
    if is_color_like(name):
        return [to_hex(name)]
    raise ValueError(f"{name!r} is not a color, color sequence, colormap or tol.<scheme>")


def sampled(name: str) -> bool:
    """A continuous colormap, whose colors here are samples."""
    import matplotlib

    if name.startswith("cmc."):
        import cmcrameri.cm  # noqa: F401
    # Color sequences and Crameri's categorical maps ("cmc.batlowS") are lists of colors;
    # other colormaps are continuous even when stored as 256 listed steps.
    base = name.removesuffix("_r")
    return (base not in matplotlib.color_sequences and name in matplotlib.colormaps
            and not (base.startswith("cmc.") and base.endswith("S")))


def view(hexes: list[str], out: Path | None, pairs_too: bool = True) -> str:
    pairs = list(combinations(range(len(hexes)), 2)) if pairs_too else []
    d = distances(rgb(hexes)) if pairs else None
    lines = []
    for k, vision in enumerate(VISIONS):
        if pairs:
            i, j = min(pairs, key=lambda p: d[k][p])
            lines.append(f"{vision:<13} closest {hexes[i]} / {hexes[j]}  {d[k, i, j]:.1f}")
    if out:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(len(VISIONS), 1, figsize=(0.5 * len(hexes) + 1.4, 1.6))
        for ax, vision, seen in zip(axes, VISIONS, simulate(rgb(hexes))):
            ax.imshow(seen[None], aspect="auto")
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_ylabel(vision, rotation=0, ha="right", va="center", fontsize=7)
        fig.tight_layout()
        fig.savefig(out, dpi=200)
        lines.append(f"wrote {out}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("view", help="closest pairs and swatches under each vision")
    v.add_argument("colors", nargs="+")
    v.add_argument("--out", type=Path, metavar="PNG")
    args = parser.parse_args(argv)
    try:
        hexes = [h for name in args.colors for h in colors(name)]
    except (ValueError, KeyError) as e:
        parser.error(str(e))
    print(view(hexes, args.out, not any(sampled(name) for name in args.colors)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
