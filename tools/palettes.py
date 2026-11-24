"""Sample the colors listed in a scrap's palette.yaml from its image, and draw swatches.

Each color names a pixel (`at: [x, y]` in files[0]); its hex is the median of the pixels
around that point, so a palette can always be checked against the image.

A palette may name the published color scheme it matches (`colormap`): a matplotlib colormap
(which includes ColorBrewer, viridis, Okabe-Ito and Tableau), a Crameri scientific color map
("cmc.batlow", from cmcrameri), or "ggplot2:hue". Every key must lie within COLORMAP_TOLERANCE
of that scheme read in one of the ways `expected` lists.

A legend may use only some colors of a scheme (`steps`, with a `step` on each key). Such a
subset is recorded only when another legend of the same paper uses that scheme cut into the
same number of colors; a subset with no such evidence is printed as a candidate.

Usage: python tools/palettes.py scraps/<citationKey>/<slug>/palette.yaml [...]
       Fills every empty `hex` from its `at`, prints the colors, and prints the closest
       named color schemes for each palette.
       python tools/palettes.py --subsets scraps/<citationKey> [--apply]
       Lists subsets of schemes used elsewhere in the paper; --apply records them.
"""

from __future__ import annotations

import argparse
import io
import math
import statistics
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

SIZE = 5  # the sample is the median of a SIZE x SIZE square, which evens out JPEG noise
SIZES = {1, 3, 5}  # a color may set a smaller `size` for marks narrower than the square
TOLERANCE = 24  # largest difference per channel (0–255) between a recorded hex and the image
TYPES = {"categorical", "sequential", "diverging", "cyclic"}
KEYS = ("label", "range", "value")  # what a color stands for: legend text, color-bar class, or tick
COLORMAP_TOLERANCE = 32  # JPEG noise and resampling move a color-bar pixel further than a legend chip
SUBSET_TOLERANCE = 16  # a subset found without evidence must fit closer: choosing steps fits more schemes by chance


def sample(image: Image.Image, at, size: int = SIZE) -> str:
    x, y = at
    half = size // 2
    box = (max(x - half, 0), max(y - half, 0), min(x + half + 1, image.width), min(y + half + 1, image.height))
    data = image.crop(box).convert("RGB").tobytes()  # the small square only: converting is per pixel
    channels = (data[0::3], data[1::3], data[2::3])
    return "#" + "".join(f"{round(statistics.median(channel)):02x}" for channel in channels)


def distance(a: str, b: str) -> int:
    return max(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) for i in (1, 3, 5))


GGPLOT_HUE = "ggplot2:hue"  # R ggplot2's default discrete colors: hcl(h = 15 + 360 i / n, c = 100, l = 65)


def colormaps():
    """matplotlib's colormaps, with the Crameri scientific color maps registered as "cmc.<name>"."""
    import matplotlib

    try:
        import cmcrameri.cm  # noqa: F401
    except ImportError:
        pass
    return matplotlib.colormaps


def hcl_hex(h: float, c: float, l: float) -> str:
    """CIE polar LUV (R's hcl) to sRGB, clipped as R does."""
    xn, yn, zn = 95.047, 100.0, 108.883
    un, vn = 4 * xn / (xn + 15 * yn + 3 * zn), 9 * yn / (xn + 15 * yn + 3 * zn)
    u, v = c * math.cos(math.radians(h)), c * math.sin(math.radians(h))
    y = yn * ((l + 16) / 116) ** 3 if l > 8 else yn * l / 903.3
    up, vp = u / (13 * l) + un, v / (13 * l) + vn
    x, z = y * 9 * up / (4 * vp), y * (12 - 3 * up - 20 * vp) / (4 * vp)
    x, y, z = x / 100, y / 100, z / 100
    linear = (3.2404542 * x - 1.5371385 * y - 0.4985314 * z,
              -0.9692660 * x + 1.8760108 * y + 0.0415560 * z,
              0.0556434 * x - 0.2040259 * y + 1.0572252 * z)
    gamma = [12.92 * t if t <= 0.0031308 else 1.055 * t ** (1 / 2.4) - 0.055 for t in linear]
    return "#" + "".join(f"{round(min(max(t, 0), 1) * 255):02x}" for t in gamma)


def placements(palette: dict) -> list[list[float]]:
    """Where each key may sit on a 0–1 colormap.

    With `bar` (the pixels at the two ends of the color bar, low end first), each key is
    placed by projecting its `at` onto the bar, so ticks need not sit at the bar's ends.
    Ticks without a bar are spread by value. Classes and legend entries, listed from the low
    end, are tried at class centers and at evenly spaced points from end to end (as R's
    discrete viridis and brewer scales sample).
    """
    colors = palette["colors"]
    n = len(colors)
    if palette.get("bar"):
        (x0, y0), (x1, y1) = palette["bar"]
        length = (x1 - x0) ** 2 + (y1 - y0) ** 2
        return [[((c["at"][0] - x0) * (x1 - x0) + (c["at"][1] - y0) * (y1 - y0)) / length
                 for c in colors]] if length else []
    if all("value" in c for c in colors):
        values = [float(c["value"]) for c in colors]
        low, high = min(values), max(values)
        return [[(v - low) / (high - low) for v in values]] if high > low else []
    if n > 1 and all("range" in c or "label" in c for c in colors):
        return [[(i + 0.5) / n for i in range(n)], [i / (n - 1) for i in range(n)]]
    return []


def cuts(name: str, steps: int) -> list[list[str]]:
    """The colors of `name` cut into `steps` colors, low end first, each way it is commonly cut.

    A qualitative palette (a listed colormap of at most 32 colors) is its listed colors; a
    continuous one is sampled from end to end and at class centers; ggplot2:hue is hue_pal(steps).
    """
    from matplotlib.colors import ListedColormap, to_hex

    if name == GGPLOT_HUE:
        return [[hcl_hex(15 + 360 * i / steps, 100, 65) for i in range(steps)]]
    maps = colormaps()
    if name not in maps:
        return []
    cmap = maps[name]
    if isinstance(cmap, ListedColormap) and cmap.N <= 32:
        return [[to_hex(c) for c in cmap.colors]] if steps == cmap.N else []
    grids = [[(i + 0.5) / steps for i in range(steps)]]
    if steps > 1:
        grids.append([i / (steps - 1) for i in range(steps)])
    return [[to_hex(cmap(x)) for x in grid] for grid in grids]


def qualitative_size(name: str) -> int | None:
    from matplotlib.colors import ListedColormap

    cmap = colormaps().get(name) if name != GGPLOT_HUE else None
    return cmap.N if isinstance(cmap, ListedColormap) and cmap.N <= 32 else None


def expected(name: str, palette: dict) -> list[list[str]]:
    """The colors each way of reading `name` would give for this palette's keys.

    With `steps`, the scheme was cut into that many colors and each key names its `step`
    (0 = low end), so a legend may use only some of the colors. Without it, keys are placed
    along the bar, by value, or in order (see `placements`); a qualitative palette is read from
    its first color.
    """
    from matplotlib.colors import to_hex

    colors = palette["colors"]
    n = len(colors)
    if palette.get("steps"):
        return [[cut[c["step"]] for c in colors] for cut in cuts(name, palette["steps"])
                if all(0 <= c.get("step", -1) < len(cut) for c in colors)]
    if name == GGPLOT_HUE:
        return [] if palette.get("bar") else cuts(name, n)
    if name not in colormaps():
        return []
    if (size := qualitative_size(name)) is not None:
        listed = not palette.get("bar") and all("label" in c for c in colors) and n <= size
        return [cuts(name, size)[0][:n]] if listed else []
    cmap = colormaps()[name]
    return [[to_hex(cmap(x)) for x in where] for where in placements(palette)]


def colormap_distance(name: str, palette: dict) -> int | None:
    colors = palette["colors"]
    options = expected(name, palette)
    if not options:
        return None
    return min(max(distance(e, c["hex"]) for e, c in zip(option, colors)) for option in options)


def rgb(hex_: str) -> tuple[int, int, int]:
    return tuple(int(hex_[i:i + 2], 16) for i in (1, 3, 5))


def ordered_subset(colors: list[str], cut: list[str]) -> tuple[int, list[int]] | None:
    """Best assignment of the colors, in order, to increasing positions of `cut` (min-max distance)."""
    n, m = len(colors), len(cut)
    if n > m:
        return None
    a, b = [rgb(c) for c in colors], [rgb(c) for c in cut]
    gap = [[max(abs(x - y) for x, y in zip(ca, cb)) for cb in b] for ca in a]
    # best[i][j]: smallest worst gap placing colors 0..i with color i at position j
    best = [gap[0][:]]
    back = [[None] * m]
    for i in range(1, n):
        row, prev, run, arg = [None] * m, [None] * m, None, None
        for j in range(m):
            if j > 0 and best[i - 1][j - 1] is not None and (run is None or best[i - 1][j - 1] < run):
                run, arg = best[i - 1][j - 1], j - 1
            if run is not None:
                row[j], prev[j] = max(run, gap[i][j]), arg
        best.append(row)
        back.append(prev)
    ends = [(v, j) for j, v in enumerate(best[-1]) if v is not None]
    if not ends:
        return None
    score, j = min(ends)
    steps = [j]
    for i in range(n - 1, 0, -1):
        j = back[i][j]
        steps.append(j)
    return score, steps[::-1]


def whole_cuts(palette: dict) -> list[list[str]]:
    """The cuts of its scheme that a legend using the scheme whole matches; they can be evidence.

    Only legends of class or entry keys without a bar qualify. A qualitative palette qualifies
    when the legend shows its complete listed sequence.
    """
    name, colors = palette.get("colormap"), palette.get("colors") or []
    if (not isinstance(name, str) or palette.get("bar") or palette.get("steps")
            or not all("label" in c or "range" in c for c in colors)):
        return []
    size = qualitative_size(name)
    if size is not None and size != len(colors):
        return []
    return [cut for cut in cuts(name, len(colors))
            if max(distance(a, c["hex"]) for a, c in zip(cut, colors)) <= COLORMAP_TOLERANCE]


def paper_whole_cuts(palettes: dict[Path, object]) -> dict[tuple[str, int], list[tuple[list[str], Path, dict]]]:
    """(scheme, number of colors) -> [(cut, palette.yaml, palette)] for every legend of one paper that uses
    a scheme whole (whole_cuts): the evidence a subset of that scheme needs. PALETTES are the paper's
    palette.yaml files as read; malformed ones are skipped."""
    found: dict[tuple[str, int], list[tuple[list[str], Path, dict]]] = {}
    for path, data in palettes.items():
        listed = data.get("palettes") if isinstance(data, dict) else None
        for p in listed if isinstance(listed, list) else []:
            if not isinstance(p, dict) or p.get("steps") is not None:
                continue
            try:
                for cut in whole_cuts(p):
                    found.setdefault((p["colormap"], len(cut)), []).append((cut, path, p))
            except (TypeError, ValueError, KeyError, AttributeError):
                pass
    return found


def subset_fit(name: str, palette: dict, largest: int = 12) -> tuple[int, int, list[int]] | None:
    """The fewest steps (up to `largest`) at which the keys are an ordered subset of `name`.

    Only legends of three or more classes or entries qualify; fewer colors fit too many schemes.
    Returns (distance, steps, step of each key), preferring fewer steps among fits within tolerance.
    """
    colors = [c["hex"] for c in palette["colors"]]
    n = len(colors)
    if n < 3 or palette.get("bar") or not all("label" in c or "range" in c for c in palette["colors"]):
        return None
    size = qualitative_size(name)
    sizes = [size] if size else ([n] if name == GGPLOT_HUE else []) + list(range(n + 1, largest + 1))
    if name == GGPLOT_HUE:
        sizes = list(range(n, largest + 1))
    found = None
    for steps in sizes:
        for cut in cuts(name, steps):
            fit = ordered_subset(colors, cut)
            if fit and (found is None or fit[0] < found[0]):
                found = (fit[0], steps, fit[1])
        if found and found[0] <= SUBSET_TOLERANCE:
            return found
    return found


def closest_colormaps(palette: dict, count: int = 3) -> list[tuple]:
    """Closest named schemes: (distance, name) read whole, or (distance, name, steps, step list)."""
    scores = []
    for name in [*colormaps(), GGPLOT_HUE]:
        whole = colormap_distance(name, {k: v for k, v in palette.items() if k != "steps"})
        if whole is not None:
            scores.append((whole, name))
        part = subset_fit(name, palette)
        if part and (whole is None or part[0] < whole):
            scores.append((part[0], name, part[1], part[2]))
    return sorted(scores, key=lambda s: (s[0], len(s)))[:count]


def key_text(color: dict) -> str:
    if "label" in color:
        return str(color["label"])
    if "range" in color:
        low, high = ("…" if v is None else v for v in color["range"])
        return f"{low} to {high}"
    return str(color.get("value"))


def scheme_png(name: str) -> bytes:
    """A named scheme as an image: chips for a qualitative palette, otherwise a gradient."""
    size = qualitative_size(name) or (8 if name == GGPLOT_HUE else None)
    colors = cuts(name, size)[0] if size else cuts(name, 256)[0]
    width, height = 512, 40
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    step = width / len(colors)
    for i, color in enumerate(colors):
        draw.rectangle((round(i * step), 0, round((i + 1) * step) - (2 if size else 0), height), fill=color)
    buf = io.BytesIO()
    image.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def swatch_png(palettes: list[dict]) -> bytes:
    """One row per palette: title, then a chip and its key for each color."""
    font = ImageFont.load_default(size=14)
    chip, gap, row = 22, 8, 34
    widths = [sum(chip + gap + int(font.getlength(key_text(c))) + 2 * gap for c in p["colors"])
              for p in palettes]
    title_w = max(int(font.getlength(str(p["title"]))) for p in palettes) + 2 * gap
    image = Image.new("RGB", (title_w + max(widths) + gap, row * len(palettes) + gap), "white")
    draw = ImageDraw.Draw(image)
    for i, p in enumerate(palettes):
        y = gap + i * row
        draw.text((gap, y + 3), str(p["title"]), fill="black", font=font)
        x = title_w
        for c in p["colors"]:
            draw.rectangle((x, y, x + chip, y + chip), fill=c["hex"], outline="#808080")
            x += chip + gap
            draw.text((x, y + 3), key_text(c), fill="black", font=font)
            x += int(font.getlength(key_text(c))) + 2 * gap
    buf = io.BytesIO()
    image.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def fill(path: Path) -> None:
    data = yaml.safe_load(path.read_text())
    obj = yaml.safe_load(path.with_name("object.yaml").read_text())
    image = Image.open(path.with_name(obj["files"][0]["path"]))
    for p in data["palettes"]:
        for c in p["colors"]:
            if not c.get("hex"):
                c["hex"] = sample(image, c["at"], c.get("size", SIZE))
            print(f"{p['title']}: {key_text(c)} {c['hex']} at {c['at']}")
        print(f"{p['title']}: closest color schemes", closest_colormaps(p))
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=None))


def paper_subsets(paper: Path, apply: bool = False) -> None:
    """Find legends that use some colors of a scheme another legend of the paper uses whole."""
    files = sorted(paper.glob("*/palette.yaml"))
    data = {f: yaml.safe_load(f.read_text()) for f in files}
    # (name, steps) -> [(a cut a whole legend matched, where it comes from)]
    cuts_used = {key: [(cut, f"{f.parent.name} {p['title']!r}") for cut, f, p in found]
                 for key, found in paper_whole_cuts(data).items()}
    for f, d in data.items():
        changed = False
        for p in d["palettes"]:
            if p.get("colormap") or len(p["colors"]) < 3 or p.get("bar"):
                continue
            hexes = [c["hex"] for c in p["colors"]]
            if all(max(rgb(h)) - min(rgb(h)) < 12 for h in hexes):
                continue  # grays fit any gray ramp
            fits = []
            for (name, steps), sources in cuts_used.items():
                for cut, source in sources:
                    fit = ordered_subset(hexes, cut)
                    if fit and fit[0] <= COLORMAP_TOLERANCE:
                        fits.append((fit[0], name, steps, fit[1], source))
            if fits:
                score, name, steps, picked, source = min(fits)
                print(f"{f.parent.name} {p['title']!r}: {name} cut into {steps}, steps {picked}, "
                      f"distance {score} (as {source})")
                if apply:
                    for c, step in zip(p["colors"], picked):
                        c["step"] = step
                    items = list(p.items())
                    p.clear()
                    for key, value in items:
                        p[key] = value
                        if key == "panels":
                            p["colormap"], p["steps"] = name, steps
                    changed = True
                continue
            loose = [(r[0], name, r[1], r[2]) for name in [*colormaps(), GGPLOT_HUE]
                     if (r := subset_fit(name, p)) and r[0] <= SUBSET_TOLERANCE]
            if loose:
                print(f"{f.parent.name} {p['title']!r}: candidate only, no other legend uses it:",
                      sorted(loose)[:3])
        if changed:
            f.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True, default_flow_style=None))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", type=Path,
                        help="palette.yaml files, or with --subsets scraps/<citationKey> folders")
    parser.add_argument("--subsets", action="store_true", help="list legends using some colors of a scheme")
    parser.add_argument("--apply", action="store_true", help="with --subsets, record the evidence-backed ones")
    args = parser.parse_args()
    if args.apply and not args.subsets:
        parser.error("--apply needs --subsets")
    for path in args.paths:
        if args.subsets and not path.is_dir():
            parser.error(f"{path} is not a scraps/<citationKey> folder")
        if not args.subsets and not path.is_file():
            parser.error(f"{path} is not a palette.yaml file")
    for path in args.paths:
        paper_subsets(path, apply=args.apply) if args.subsets else fill(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
