"""Run figure scripts and report text boxes outside the saved area.

--measure adds text box intersections, the smallest text, the lowest text contrast, the
legend pair closest in any of normal vision, deuteranopia and protanopia, and labels whose
color differs between legends. Values come from the draw that writes each file.

Usage: python tools/flint.py SCRIPT.py [...] [--measure] [--json]
Each line is `file | what | where | measured`. The scripts still save their figures.
Exit 0 when the scripts ran, 1 when one failed, 2 for bad arguments.
"""

import argparse
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass
from io import StringIO
from itertools import combinations
import json
import os
from pathlib import Path
import runpy
import sys
import traceback
from unittest.mock import patch

import numpy as np
from matplotlib.colors import to_hex
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[1]
if not __package__:  # Also support python tools/flint.py from outside the checkout.
    sys.path.insert(0, str(ROOT))

from tools.color import VISIONS, distances, luminance  # noqa: E402
from tools.flint_context import build_context, capture  # noqa: E402

SAVEFIG = Figure.savefig


@dataclass(frozen=True)
class Record:
    file: str
    what: str
    where: str
    measured: str

    def __str__(self):
        return " | ".join(" ".join(v.split()).replace("|", "/") for v in asdict(self).values())


def contrast(text) -> float:
    bg = np.array(text.background)
    alpha = text.color[3]
    fg = np.array(text.color[:3]) * alpha + bg * (1 - alpha)
    dark, light = sorted((luminance(fg), luminance(bg)))
    return (light + 0.05) / (dark + 0.05)


def measure(fig, more=False, **savefig_kwargs) -> list[tuple[str, str, str]]:
    """(what, where, measured) for one figure as savefig would write it."""
    return report(build_context(fig, **savefig_kwargs), more)


def report(ctx, more=False) -> list[tuple[str, str, str]]:
    out = []
    x0, y0, x1, y1 = ctx.canvas
    for t in ctx.texts:
        left, bottom, right, top = t.bbox
        outside = max(x0 - left, y0 - bottom, right - x1, top - y1)
        if outside > 0:
            out.append(("outside-canvas", t.where, f"{outside:.2f} pt"))
    if not more:
        return out

    for a, b in combinations(ctx.texts, 2):
        l1, b1, r1, t1 = a.bbox
        l2, b2, r2, t2 = b.bbox
        area = max(0, min(r1, r2) - max(l1, l2)) * max(0, min(t1, t2) - max(b1, b2))
        if area > 0:
            out.append(("box-intersection", f"{a.where} / {b.where}", f"{area:.2f} pt²"))
    if ctx.texts:
        smallest = min(ctx.texts, key=lambda t: t.size)
        out.append(("smallest-text", smallest.where, f"{smallest.size:.3g} pt"))
    backed = [t for t in ctx.texts if t.background is not None]
    if backed:
        lowest = min(backed, key=contrast)
        out.append(("lowest-contrast", lowest.where, f"{contrast(lowest):.2f}:1"))

    for legend in ctx.legends:
        # Entries that differ in marker, line, hatch or size are told apart without color.
        groups = {}
        for e in legend.entries:
            if e.color is not None:
                groups.setdefault((e.marker, e.linestyle, e.hatch, e.size, e.linewidth), []).append(e)
        pairs = []
        for entries in groups.values():
            if len(entries) > 1:
                d = distances(np.array([e.color[:3] for e in entries]))
                pairs += [(d[:, i, j], entries[i], entries[j]) for i, j in combinations(range(len(entries)), 2)]
        if pairs:
            d, a, b = min(pairs, key=lambda p: p[0].min())
            out.append(("pair-closest-in-any-vision", f"{legend.where} {a.label!r} / {b.label!r}",
                        ", ".join(f"{v} {x:.1f}" for v, x in zip(VISIONS, d)) + " (CAM02-UCS)"))

    drawn = {}  # label -> legend -> colors
    for legend in ctx.legends:
        for e in legend.entries:
            if e.color is not None and e.label.strip() and not e.label.startswith("_"):
                drawn.setdefault(e.label, {}).setdefault(legend.where, set()).add(to_hex(e.color))
    for label, legends in drawn.items():
        if len(legends) > 1 and len(set().union(*legends.values())) > 1:
            out.append(("label-colors", repr(label),
                        ", ".join(f"{' '.join(sorted(c))} in {w}" for w, c in legends.items())))
    return out


def measure_script(script, plt, more=False):
    """Run a script; measure each figure in the draw that saves it, and each one left open."""
    results = []
    saved = set()

    def savefig(fig, *args, **kwargs):
        results.extend(report(capture(fig, lambda: SAVEFIG(fig, *args, **kwargs)), more))
        saved.add(fig)

    cwd = os.getcwd()
    try:
        with patch.object(Figure, "savefig", savefig), redirect_stdout(StringIO()), \
                patch.object(sys, "argv", [str(script)]), \
                patch.object(sys, "path", [str(script.resolve().parent), *sys.path]):
            try:
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit as stop:
                if stop.code not in (0, None):
                    raise RuntimeError(f"exited with {stop.code}") from None
            for number in plt.get_fignums():
                fig = plt.figure(number)
                if fig not in saved:
                    results.extend(measure(fig, more))
    finally:
        os.chdir(cwd)
        plt.close("all")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scripts", nargs="+", type=Path)
    parser.add_argument("--measure", action="store_true", help="also list the measurements for a person to judge")
    parser.add_argument("--json", action="store_true", help="one JSON object per line")
    args = parser.parse_args(argv)
    import matplotlib.pyplot as plt
    plt.switch_backend("Agg")
    failed = False
    for script in args.scripts:
        try:
            rows = measure_script(script, plt, args.measure)
        except Exception:  # a broken script is reported; the others still run
            print(f"{script}: failed\n{traceback.format_exc()}", file=sys.stderr)
            failed = True
            continue
        for row in rows:
            record = Record(str(script), *row)
            print(json.dumps(asdict(record), ensure_ascii=False) if args.json else record)
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
