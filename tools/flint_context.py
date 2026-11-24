"""Capture a figure as plain values while Matplotlib draws it for savefig, so the values
describe the saved file: its area, DPI, layout and background. Coordinates are points from
the bottom left of the saved area; colors are sRGB floats in [0, 1]."""

from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from unittest.mock import patch
from typing import Literal

import numpy as np
from matplotlib import colors
from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.figure import Figure
from matplotlib.collections import Collection
from matplotlib.legend import Legend
from matplotlib.lines import Line2D
from matplotlib.offsetbox import DrawingArea
from matplotlib.patches import Patch
from matplotlib.path import Path
from matplotlib.text import Annotation, Text
from matplotlib.transforms import Bbox

type RGB = tuple[float, float, float]
type Box = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class TextRecord:
    text: str
    bbox: Box
    size: float
    color: tuple[float, float, float, float]
    background: RGB | None
    kind: Literal["layout", "data"]
    axes_index: int | None
    where: str


@dataclass(frozen=True, slots=True)
class LegendEntry:
    """Each encoding tuple has one item per drawn component of the legend key."""

    label: str
    color: RGB | None
    marker: tuple
    linestyle: tuple
    hatch: tuple
    size: tuple
    linewidth: tuple


@dataclass(frozen=True, slots=True)
class LegendRecord:
    where: str
    axes_index: int | None
    entries: tuple[LegendEntry, ...]


@dataclass(frozen=True, slots=True)
class Context:
    canvas: Box  # the saved area
    texts: tuple[TextRecord, ...]
    legends: tuple[LegendRecord, ...]


def over(rgba, bg):
    rgba = np.asarray(rgba)
    return rgba[..., :3] * rgba[..., 3:] + bg * (1 - rgba[..., 3:])


def background(box, pixels):
    """Estimate the background from the median rendered pixel in the visible box."""
    height, width = pixels.shape[:2]
    x0, y0 = np.maximum(np.floor(box.min).astype(int), 0)
    x1, y1 = np.minimum(np.ceil(box.max).astype(int), (width, height))
    if x0 >= x1 or y0 >= y1:
        return None
    rgba = pixels[height-y1:height-y0, x0:x1] / 255
    return np.median(over(rgba, 1), axis=(0, 1))


def handle_color(handle):
    if handle is None or not handle.get_visible():
        return None
    if isinstance(handle, Line2D):
        candidates = [handle.get_color()] if handle.get_linestyle() != "None" else [
            handle.get_markerfacecolor(), handle.get_markeredgecolor()]
    elif isinstance(handle, (Patch, Collection)):
        candidates = [handle.get_facecolor(), handle.get_edgecolor()]
    else:
        return None
    for color in candidates:
        rgba = colors.to_rgba_array(color, alpha=handle.get_alpha())
        if len(rgba) and rgba[0, 3] > 0:
            return rgba[0]


def visible_artists(artist, where, axes, data):
    """Walk visible parents, including inset axes, figure legends and color bars."""
    if not artist.get_visible():
        return
    if isinstance(artist, Axes):
        where = axes[artist]
    if isinstance(artist, Axis):
        if not getattr(artist.axes, "_axis3don", artist.axes.axison):
            return
        # Axis.draw uses this same subset; locators often return extra off-screen ticks.
        children = [artist.label, artist.offsetText, *artist._update_ticks()]
    else:
        children = artist.get_children()
    if isinstance(artist, (Legend, Text)):
        role = "data" if artist in data else "layout"
        yield artist, where, role
    for child in children:
        yield from visible_artists(child, where, axes, data)


def geometry(value):
    """Make Matplotlib's marker paths and dash sequences immutable and comparable."""
    if isinstance(value, Path):
        return geometry(value.vertices), geometry(value.codes)
    if isinstance(value, (tuple, list, np.ndarray)):
        return tuple(geometry(element) for element in value)
    return value


def encoding(handle):
    if isinstance(handle, Line2D):
        marker = ("line", geometry(handle.get_marker()), handle.get_fillstyle())
        # get_linestyle() reports "--" for custom dash patterns.
        linestyle = (handle.get_linestyle(), geometry(handle._unscaled_dash_pattern))
        return (marker, linestyle, None, handle.get_markersize(),
                (handle.get_linewidth(), handle.get_markeredgewidth()))
    if isinstance(handle, Patch):
        return ((type(handle).__name__, handle.get_fill()), geometry(handle.get_linestyle()),
                handle.get_hatch(), None, handle.get_linewidth())
    if isinstance(handle, Collection):
        return ((type(handle).__name__, geometry(handle.get_paths())), geometry(handle.get_linestyles()),
                handle.get_hatch(), geometry(handle.get_sizes()) if hasattr(handle, "get_sizes") else None,
                geometry(handle.get_linewidths()))
    return None


def legend_record(legend, where, index, pixels, renderer):
    bg = None if pixels is None else background(legend.get_window_extent(renderer), pixels)
    entries = []
    # Each DrawingArea contains one key, including all proxies in a tuple handle.
    areas = legend.findobj(DrawingArea)
    for label, area in zip(legend.get_texts(), areas, strict=True):
        handles = [h for h in area.get_children() if h.get_visible()]
        shapes = [encoding(h) for h in handles]
        color = None
        fields = ((), (), (), (), ())
        if shapes and None not in shapes:
            fields = tuple(zip(*shapes))
            rgba = handle_color(handles[0])
            if rgba is not None:
                color = tuple(over(rgba, 1 if bg is None else bg))
        entries.append(LegendEntry(label.get_text(), color, *fields))
    return LegendRecord(where + " legend", index, tuple(entries))


@contextmanager
def sampled_backgrounds(renderer, backgrounds):
    """On a raster renderer, note the painted background under each text before its ink."""
    if not hasattr(renderer, "buffer_rgba"):
        yield
        return
    draw_text = renderer.draw_text

    def sample(gc, x, y, s, prop, angle, ismath=False, mtext=None):
        if mtext is not None:
            box = Text.get_window_extent(mtext, renderer)
            if np.isfinite(box.extents).all():
                backgrounds[mtext] = background(box, np.asarray(renderer.buffer_rgba()))
        return draw_text(gc, x, y, s, prop, angle, ismath, mtext)

    own = renderer.__dict__.get("draw_text")  # savefig's tight-box pass replaces methods too
    renderer.draw_text = sample
    try:
        yield
    finally:
        if renderer.__dict__.get("draw_text") is sample:  # the canvas keeps its renderer
            if own is None:
                del renderer.draw_text
            else:
                renderer.draw_text = own


def snapshot(fig, renderer, backgrounds) -> Context:
    pixels = np.asarray(renderer.buffer_rgba()) if hasattr(renderer, "buffer_rgba") else None
    ordered = dict.fromkeys([*fig.axes, *fig.findobj(Axes)])  # Inset axes can be children.
    indices = {ax: i for i, ax in enumerate(ordered)}
    data = {text for ax in indices for text in ax.texts}
    px_per_pt = fig.dpi / 72
    color_bars = {i for ax, i in indices.items() if ax.get_label() == "<colorbar>"}
    texts, legends, seen = [], [], {}
    for artist, index, role in visible_artists(fig, None, indices, data):
        where = "figure" if index is None else f"axes[{index}]"
        if index in color_bars:
            where += " color bar"
        if isinstance(artist, Legend):
            seen[where] = n = seen.get(where, 0) + 1  # two legends on one axes stay apart
            legends.append(legend_record(artist, where + (f" #{n}" if n > 1 else ""), index, pixels, renderer))
            continue
        if not artist.get_text().strip() or isinstance(artist, Annotation) and not artist._check_xy(renderer):
            continue
        rgba = colors.to_rgba(artist.get_color(), artist.get_alpha())
        # Annotation.get_window_extent also includes its arrow.
        box = Text.get_window_extent(artist, renderer)
        if not rgba[3] or not np.isfinite(box.extents).all() or box.width <= 0 or box.height <= 0:
            continue
        if artist.get_clip_on() and artist.get_clip_box() is not None:
            box = Bbox.intersection(box, artist.get_clip_box())
            if box is None:
                continue
        bg = backgrounds.get(artist)
        if bg is None and pixels is not None:  # multiline text, strokes and TeX bypass draw_text's artist
            bg = background(box, pixels)
        texts.append(TextRecord(artist.get_text(), tuple(box.extents / px_per_pt), artist.get_fontsize(),
                                rgba, None if bg is None else tuple(bg),
                                role, index, f"{where} {role} {artist.get_text()!r}"))
    return Context((0, 0, *(fig.bbox.size / px_per_pt)), tuple(texts), tuple(legends))


def capture(fig, save) -> Context:
    """Run save() (a savefig call) and return the figure as its last draw left it."""
    shots = []
    draw = Figure.draw

    def recording(self, renderer):
        backgrounds = {}
        with sampled_backgrounds(renderer, backgrounds):
            draw(self, renderer)
        if self is fig:
            shots.append(snapshot(self, renderer, backgrounds))

    with patch.object(Figure, "draw", recording):
        save()
    return shots[-1]


def build_context(fig, **savefig_kwargs) -> Context:
    """The figure as savefig would write it to a PNG with these keyword arguments."""
    return capture(fig, lambda: fig.savefig(BytesIO(), **{"format": "png", **savefig_kwargs}))
