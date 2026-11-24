"""Palette checks of tools/check.py: each palette.yaml against its image, and a legend that uses some
colors of a scheme against the paper's other legends (tools/palettes.py describes both).

The functions take what check.py has read (each palette.yaml once) and report through its Report.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from palettes import COLORMAP_TOLERANCE, KEYS, SIZE, SIZES, TOLERANCE, TYPES, colormap_distance, distance, paper_whole_cuts, sample

HEX = re.compile(r"^#[0-9a-f]{6}$")


def check_palette(path: Path, data, obj: dict, image: Image.Image, r) -> None:
    """Each color names what it stands for and a pixel of IMAGE (files[0]) whose color matches its hex.
    DATA is palette.yaml as read."""
    palettes = data.get("palettes") if isinstance(data, dict) else None
    if not isinstance(palettes, list) or not palettes or not all(isinstance(p, dict) for p in palettes):
        r.err(path, "palettes must be a non-empty list of mappings")
        return
    if not all(isinstance(p.get("colors"), list) and all(isinstance(c, dict) for c in p["colors"])
               for p in palettes):
        r.err(path, "every palette needs a list of color mappings")
        return
    ids = {str(p.get("id")) for p in obj.get("panels") or []}
    for i, p in enumerate(palettes):
        where = f"palettes[{i}]"
        if not p.get("title"):
            r.err(path, f"{where}: missing title")
        if p.get("type") not in TYPES:
            r.err(path, f"{where}: type {p.get('type')!r} is not one of {sorted(TYPES)}")
        for pid in p.get("panels") or []:
            if str(pid) not in ids:
                r.err(path, f"{where}: panel {pid!r} not in object.yaml")
        if not p.get("colors"):
            r.err(path, f"{where}: no colors")
        bar = p.get("bar")
        if bar is not None and not (isinstance(bar, list) and len(bar) == 2 and all(
                isinstance(end, list) and len(end) == 2 and all(isinstance(v, int) for v in end) for end in bar)):
            r.err(path, f"{where}: bar needs two pixels [[x, y], [x, y]], low end first")
        if p.get("steps") is not None and not (
                type(p["steps"]) is int and isinstance(p.get("colormap"), str)
                and all(isinstance(c.get("step"), int) for c in p.get("colors") or [])):
            r.err(path, f"{where}: steps needs a colormap and an integer step on every color")
            continue
        ready = bool(p.get("colors")) and all(
            HEX.match(str(c.get("hex"))) and isinstance(c.get("at"), list) and len(c["at"]) == 2
            for c in p["colors"])
        if bar is not None and not (isinstance(bar, list) and len(bar) == 2):
            ready = False
        if p.get("colormap") is not None and not isinstance(p["colormap"], str):
            r.err(path, f"{where}: colormap must be a name")
            ready = False
        if p.get("colormap") and ready:
            try:
                gap = colormap_distance(p["colormap"], p)
            except (TypeError, ValueError, KeyError, IndexError) as exc:
                r.err(path, f"{where}: cannot compare with {p['colormap']}: {exc}")
                continue
            if gap is None:
                r.err(path, f"{where}: colormap {p['colormap']!r} is not a matplotlib colormap or keys lack values")
            elif gap > COLORMAP_TOLERANCE:
                r.err(path, f"{where}: colors differ from {p['colormap']} by up to {gap}")
        for j, c in enumerate(p.get("colors") or []):
            here = f"{where}.colors[{j}]"
            if sum(k in c for k in KEYS) != 1:
                r.err(path, f"{here}: needs exactly one of {', '.join(KEYS)}")
            if "range" in c and not (isinstance(c["range"], list) and len(c["range"]) == 2
                                     and any(v is not None for v in c["range"])):
                r.err(path, f"{here}: range needs two bounds, printed ticks or null where unprinted")
            if not HEX.match(str(c.get("hex"))):
                r.err(path, f"{here}: hex {c.get('hex')!r} is not #rrggbb")
                continue
            at = c.get("at")
            if not (isinstance(at, list) and len(at) == 2 and all(isinstance(v, int) for v in at)
                    and 0 <= at[0] < image.width and 0 <= at[1] < image.height):
                r.err(path, f"{here}: at {at!r} is not a pixel of {obj['files'][0]['path']}")
                continue
            if type(c.get("size", SIZE)) is not int or c.get("size", SIZE) not in SIZES:
                r.err(path, f"{here}: size {c.get('size')!r} is not one of {sorted(SIZES)}")
                continue
            found = sample(image, at, c.get("size", SIZE))
            if distance(found, c["hex"]) > TOLERANCE:
                r.err(path, f"{here}: hex {c['hex']} but the image is {found} at {at}")




def check_subset_evidence(palettes: dict[Path, object], r) -> None:
    """A legend recorded as some colors of a scheme needs another legend of the paper using it whole,
    and its colors must match a cut such a legend matched (class centers, end to end, or listed).
    PALETTES are the palette.yaml files of one paper as read; malformed ones are skipped here
    (check_palette reports them)."""
    whole = paper_whole_cuts(palettes)
    for path, data in palettes.items():
        listed = data.get("palettes") if isinstance(data, dict) else None
        for i, p in enumerate(listed if isinstance(listed, list) else []):
            if not (isinstance(p, dict) and p.get("steps") is not None and isinstance(p.get("colormap"), str)
                    and type(p["steps"]) is int):
                continue
            evidence = [cut for cut, _, _ in whole.get((p["colormap"], p["steps"]), [])]
            if not evidence:
                r.err(path, f"palettes[{i}]: no legend in this paper uses {p['colormap']} whole in {p['steps']} colors")
                continue
            try:
                gap = min(max(distance(cut[c["step"]], c["hex"]) for c in p["colors"]) for cut in evidence)
            except (TypeError, KeyError, IndexError, ValueError, AttributeError):
                continue
            if gap > COLORMAP_TOLERANCE:
                r.err(path, f"palettes[{i}]: colors differ by up to {gap} from the {p['colormap']} cut "
                            f"the whole legend matched")
