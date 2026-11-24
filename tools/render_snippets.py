"""Render the committed examples, or preview another style or width in a separate directory."""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNIPPETS = ROOT / "snippets"


def width_mm(value: str) -> float:
    width = float(value)
    if not math.isfinite(width) or width <= 0:
        raise argparse.ArgumentTypeError("width must be a positive, finite number of millimeters")
    return width


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="snippet IDs (default: all)")
    parser.add_argument("--style", default=os.environ.get("CEDALION_STYLE"),
                        help="name in styles/ or path to a .mplstyle file")
    parser.add_argument("--width", type=width_mm, default=os.environ.get("CEDALION_WIDTH_MM"),
                        metavar="MM", help="figure width in millimeters (default: 183)")
    parser.add_argument("--out", type=Path, metavar="DIR",
                        help="preview directory; style or width alone creates a temporary one")
    args = parser.parse_args(argv)

    scripts = sorted(SNIPPETS.glob("*/*/snippet.py"))
    if args.ids:
        missing = set(args.ids) - {script.parent.name for script in scripts}
        if missing:
            parser.error("unknown snippet IDs: " + ", ".join(sorted(missing)))
        scripts = [script for script in scripts if script.parent.name in args.ids]

    env = {**os.environ, "MPLBACKEND": "Agg"}
    env.pop("CEDALION_SNIPPET_PNG", None)
    if args.style:
        sheet = Path(args.style).expanduser()
        if not sheet.is_file():
            sheet = ROOT / "styles" / (args.style.removesuffix(".mplstyle") + ".mplstyle")
        if not sheet.is_file():
            parser.error(f"style sheet not found: {args.style}")
        env["CEDALION_STYLE"] = str(sheet.resolve())
    if args.width is not None:
        env["CEDALION_WIDTH_MM"] = str(args.width)
    out = args.out
    if out is None and (args.style or args.width is not None):
        out = Path(tempfile.mkdtemp(prefix="cedalion-snippets-"))
    if out is not None:
        out = out.expanduser().resolve()
        print(f"Preview: {out}", flush=True)

    failures = 0
    for script in scripts:
        rel = script.parent.relative_to(SNIPPETS)
        png = script.with_name("snippet.png")
        if out is not None:
            png = out / rel / "snippet.png"
            if png.resolve().is_relative_to(SNIPPETS):
                parser.error(f"choose a preview destination outside {SNIPPETS}")
            png.parent.mkdir(parents=True, exist_ok=True)
            env["CEDALION_SNIPPET_PNG"] = str(png)
        before = png.stat().st_mtime_ns if png.exists() else None
        proc = subprocess.run([sys.executable, script.name], cwd=script.parent, env=env,
                              capture_output=True, text=True)
        if proc.returncode:
            print(f"FAIL {rel}\n{proc.stderr}", file=sys.stderr)
        elif not png.is_file() or png.stat().st_mtime_ns == before:
            print(f"FAIL {rel}: {png} was not written", file=sys.stderr)
        else:
            print(f"ok   {rel}")
            continue
        failures += 1
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
