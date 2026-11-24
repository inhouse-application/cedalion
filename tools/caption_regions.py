"""Read PDF characters from caption locations, following same-style text across columns."""

import re

import fitz

FIGURE = re.compile(r"^(Fig(?:ure)?\.?\s+([A-Z]?\d+[a-z]?)[.:]?)(?=\s|$)", re.I)
LIGATURES = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
                           "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"})


FLAGS = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES


def line_text(line):
    # The glyphs of a subscript can be in another span with no intervening space.
    return "".join(span["text"] for span in line["spans"])


def blocks(page, clip=None):
    parts = []
    for block in page.get_text("dict", flags=FLAGS, clip=clip)["blocks"]:
        lines = []
        bounds = fitz.Rect()
        for line in block["lines"]:
            if not line_text(line).strip():
                # A blank line can precede a caption in the same block and hide its label.
                continue
            box = fitz.Rect(line["bbox"])
            if lines and box.y0 < bounds.y1 and (box.x1 < bounds.x0 or box.x0 > bounds.x1):
                # Some content streams group side-by-side columns into one block.
                parts.append({"lines": lines, "bbox": tuple(bounds)})
                lines = []
                bounds = fitz.Rect()
            lines.append(line)
            bounds |= box
        if lines:
            parts.append({"lines": lines, "bbox": tuple(bounds)})
    return parts


def font_size(block):
    # Weight by visible characters so a math index cannot set the paragraph size.
    sizes = sorted((s["size"], len(s["text"].strip()))
                   for line in block["lines"] for s in line["spans"])
    middle = sum(count for _, count in sizes) / 2
    for size, count in sizes:
        middle -= count
        if middle <= 0:
            return size
    return 0


def touches(line, rect):
    box = fitz.Rect(line["bbox"])
    midline = (box.y0 + box.y1) / 2
    return rect.y0 <= midline <= rect.y1 and min(rect.x1, box.x1) > max(rect.x0, box.x0)


def unreported_continuation(doc, previous_page, previous, first, size):
    """Infer a next-page seed only for an unfinished line near the bottom margin."""
    sheet = doc[previous_page - 1]
    last = line_text(previous["lines"][-1]).rstrip()
    if (previous_page == len(doc) or previous["bbox"][3] < sheet.rect.height * 0.88
            or not last or last.endswith((".", "!", "?"))):
        return None
    page = doc[previous_page]
    hits = []
    for block in blocks(page, fitz.Rect(0, 0, page.rect.width, page.rect.height * 0.18)):
        line = block["lines"][0]
        text = line_text(line).lstrip()
        if (text and (text[0].islower() or text[0].isdigit())
                and abs(line["bbox"][0] - first["bbox"][0]) <= size
                and abs(font_size(block) - size) <= 0.35):
            hits.append(fitz.Rect(line["bbox"]))
    return hits[0] if len(hits) == 1 else None


def reading_regions(doc, label, regions):
    """Seed a labeled PDF block from native coordinates, then recover continuations.

    No reference text or manual figure geometry enters this step. Retain the native
    regions and the actual reading clips separately for inspection.
    """
    if not regions:
        return []
    seeds = {}
    for p, *coords in regions:
        if 1 <= p <= len(doc) and not fitz.Rect(coords).is_empty:
            seeds.setdefault(p, []).append(fitz.Rect(coords))
    pages = {p: blocks(doc[p - 1]) for p in seeds}
    anchor = None
    for p, page_blocks in pages.items():
        for i, block in enumerate(page_blocks):
            first = block["lines"][0]
            match = FIGURE.match(line_text(first))
            if (match and match[2] == label and
                    any(touches(first, box) for box in seeds[p])):
                anchor = (p, i)
                break
        if anchor:
            break
    if anchor is None:
        return []

    start, index = anchor
    initial = pages[start][index]
    size = font_size(initial)
    chosen = [anchor]
    # Within the caption band, read a column downwards before moving right.
    # Page content streams can put a right column before the left one.
    for p in range(start, len(doc) + 1):
        if p not in pages:
            continue

        def reading_order(index):
            x, y, _, _ = pages[p][index]["bbox"]
            column = round((x - initial["bbox"][0]) / max(size, 1))
            # A run-in label can be its own block on the caption body's first line (PNAS);
            # taller glyphs can put that body's top a fraction above the label's, so rows are
            # compared in units of the font size and ties keep content-stream order.
            return column, round(y / max(size, 1)), index

        for i in sorted(range(len(pages[p])), key=reading_order):
            if p == start and reading_order(i) <= reading_order(index):
                continue
            block = pages[p][i]
            first = block["lines"][0]
            box = fitz.Rect(block["bbox"])
            last_p, last_i = chosen[-1]
            prev = fitz.Rect(pages[last_p][last_i]["bbox"])
            same_column = abs(box.x0 - prev.x0) <= size
            follows = same_column and -1 <= box.y0 - prev.y1 <= size * 1.5
            next_column = (0 <= box.x0 - prev.x1 <= size * 6
                           and abs(box.y0 - prev.y0) <= size)
            indicated = any(touches(first, seed) for seed in seeds[p])
            if not (indicated or (p == last_p and (follows or next_column))):
                continue
            if FIGURE.match(line_text(first)) or abs(font_size(block) - size) > 0.35:
                continue
            chosen.append((p, i))
        if p + 1 not in pages and chosen[-1][0] == p:
            inferred = unreported_continuation(doc, p, pages[p][chosen[-1][1]], initial, size)
            if inferred is not None:
                seeds[p + 1] = [inferred]
                pages[p + 1] = blocks(doc[p])
    clips = []
    for p, i in chosen:
        box = fitz.Rect(pages[p][i]["bbox"])
        # Counter float rounding at the text layer's own glyph edges.
        clips.append([p, box.x0 - 0.1, box.y0 - 0.1, box.x1 + 0.1, box.y1 + 0.1])
    return clips
