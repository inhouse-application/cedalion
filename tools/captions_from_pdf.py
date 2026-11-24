"""Extract missing figure captions from locally held PDFs. Check the results on the printed pages.

Each PDF needs a provenance file next to it, <citationKey>.yaml, with
  version: vor | accepted-manuscript | preprint
  url: <where the PDF was obtained>
Both are copied into caption_source. Scraps and the default PDF folder are in the scrapbook (tools/paths.py).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
import yaml

import add_scrap
from add_scrap import write_yaml
from caption_regions import FIGURE, LIGATURES, blocks, line_text, reading_regions
from pdffigures import caption_locations, locator_jar, run_batch


# A 0.10 em gap separates the measured 0.149 em word breaks from letter
# spacing (up to 0.027 em) without adding spaces at a mere font change.
SPACE_GAP_EM = 0.10
# Marks a caption read by the fallback; it may be a contents line or stop at a page break.
WITHOUT_LOCATOR = object()
WORD = re.compile(r"[^\W_]+(?:-[^\W_]+)*")
WRAP = re.compile(rf"{WORD.pattern}(?:-\n{WORD.pattern})+")


def document_spellings(doc):
    """Collect independent spellings without treating wrap fragments as words."""
    words = set()
    flags = fitz.TEXTFLAGS_TEXT & ~fitz.TEXT_DEHYPHENATE
    for page in doc:
        text = page.get_text("text", flags=flags).translate(LIGATURES).casefold()
        # Neither fragment of an observed wrap establishes another word's spelling.
        intact = re.sub(rf"{WORD.pattern}(?:[-\u00ad]\n{WORD.pattern})+", " ", text)
        words.update(WORD.findall(intact))
    return words


def marked_line(line):
    """Read glyphs in order, preserving baseline shifts and visible horizontal gaps."""
    base = max(line["spans"], key=lambda s: s["size"])
    parts = []
    prev = None
    for span in line["spans"]:
        offset = span["origin"][1] - base["origin"][1]
        tag = None
        if span["size"] < 0.85 * base["size"] and abs(offset) > 0.1 * base["size"]:
            tag = "sub" if offset > 0 else "sup"
        chars = []
        for char in span["chars"]:
            c = char["c"]
            if prev is not None and not (prev["c"].isspace() or c.isspace()):
                gap = char["origin"][0] - prev["bbox"][2]
                if line["dir"] == (1.0, 0.0) and gap > SPACE_GAP_EM * base["size"]:
                    if chars:
                        chars.append(" ")
                    else:
                        parts.append(" ")
            chars.append(c)
            prev = char
        text = "".join(chars)
        parts.append(f"<{tag}>{text}</{tag}>" if tag and text else text)
    # Adjacent shifted spans (a subscript split by a comma or font change) form one tag.
    return re.sub(r"</(sub|sup)><\1>", "", "".join(parts)).strip()


def resolve_wraps(text, spellings):
    """Keep ambiguous hard wraps visible and report each one to the caller."""
    text = text.translate(LIGATURES)
    text = re.sub(r"\u00ad\n(?=\w)", "", text)
    review = []

    def replace(match):
        parts = match[0].split("-\n")
        joined = "".join(parts)
        hyphenated = "-".join(parts)
        if (all(part[0].islower() for part in parts[1:]) and joined.casefold() in spellings
                and hyphenated.casefold() not in spellings):
            # A word wrapping twice could also have a genuine internal hyphen at
            # only one of the breaks. Retain it when the document is ambiguous.
            if len(parts) == 2 or not any(
                    word != joined.casefold() and word.replace("-", "") == joined.casefold().replace("-", "")
                    for word in spellings):
                return joined
        review.append(hyphenated)
        return hyphenated

    text = WRAP.sub(replace, text)
    # Non-word neighbors (math, markup, punctuation) supply no lexical evidence.
    for match in re.finditer(r"(\S*-)[^\S\n]*\n(?!\n)(\S+)", text):
        review.append("".join(match.groups()))
    return text, review


def read_caption(doc, label, regions, spellings, follow=True):
    clips = reading_regions(doc, label, regions) if follow else regions
    if not clips:
        return None
    lines = []
    previous = None
    seen = set()
    flags = fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES
    for page, *coords in clips:
        box = fitz.Rect(coords)
        blocks = doc[page - 1].get_text("rawdict", clip=box, flags=flags)["blocks"]
        for block in blocks:
            for index, line in enumerate(block["lines"]):
                text = marked_line(line)
                key = (page, tuple(line["bbox"]), text)
                if key in seen:
                    continue
                seen.add(key)
                size = max(span["size"] for span in line["spans"])
                if previous and index == 0:
                    p, old, old_size = previous
                    if (p == page and abs(line["bbox"][0] - old[0]) < size
                            and line["bbox"][1] - old[3] > old_size / 2):
                        lines.append("")
                lines.append(text)
                previous = (page, line["bbox"], size)
    text, review = resolve_wraps("\n".join(lines), spellings)
    match = FIGURE.match(text)
    if not match or match[2] != label:
        return None
    body = text[match.end():].strip()
    if not body:
        return None
    body = "\n\n".join(" ".join(p.split()) for p in body.split("\n\n") if p.strip())
    return clips[0][0], f"**{match[1]}** {body}\n", review


def caption_paragraph(block):
    """Bounds of a block's lines up to the first gap wider than half a line."""
    box = previous = fitz.Rect(block["lines"][0]["bbox"])
    for line in block["lines"][1:]:
        current = fitz.Rect(line["bbox"])
        if current.y0 - previous.y1 > previous.height / 2:
            break
        box |= current
        previous = current
    return tuple(box)


def extract_pdf(pdf, labels):
    """Read the requested figure numbers without modifying any scrap."""
    jar = locator_jar()
    found = defaultdict(list)
    with TemporaryDirectory(prefix="cedalion-caption-") as tmp:
        # The locator, glyph reader and provenance hash must see identical bytes.
        folder = Path(tmp)
        data = pdf.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        snapshot = folder / pdf.name
        snapshot.write_bytes(data)
        run_batch(snapshot, folder, jar)
        with fitz.open(stream=data, filetype="pdf") as doc:
            spellings = document_spellings(doc)
            for item, region in caption_locations(snapshot, folder):
                number = str(item["name"])
                if number in labels:
                    candidate = read_caption(doc, number, [region], spellings)
                    if candidate:
                        found[number].append(candidate)
            for number in labels - set(found):
                # The locator does not report "Figure S1:" labels. Seed from the one block that
                # opens with the label and its punctuation, which a bare page heading lacks.
                # Such supplements set captions and body text in one font, so read only the
                # label's own paragraph instead of following same-size continuations.
                opening = re.compile(rf"^Fig(?:ure)?\.?\s+{re.escape(number)}[.:]", re.I)
                regions = [[i + 1, *caption_paragraph(block)] for i, page in enumerate(doc)
                           for block in blocks(page) if opening.match(line_text(block["lines"][0]))]
                candidate = read_caption(doc, number, regions, spellings, follow=False) if len(regions) == 1 else None
                # A paragraph cut by a page break, or a contents line, does not end a sentence.
                if candidate and re.search(r"[.!?][)\"'’”]?\s*$", candidate[1]):
                    page, caption, review = candidate
                    found[number].append((page, caption, [*review, WITHOUT_LOCATOR]))
    return digest, found


def capture_paper(pdf, scraps):
    provenance_path = pdf.with_suffix(".yaml")
    if not provenance_path.is_file():
        print(f"skip {pdf.stem}: missing provenance file {provenance_path.name}", file=sys.stderr)
        return False
    provenance = yaml.safe_load(provenance_path.read_text())
    if (not isinstance(provenance, dict)
            or provenance.get("version") not in {"vor", "accepted-manuscript", "preprint"}
            or not isinstance(provenance.get("url"), str) or not provenance["url"].strip()):
        raise ValueError(f"Expected PDF version and source URL in {provenance_path}")
    objects = [(path, yaml.safe_load(path.read_text())) for path in scraps]
    labels = {match[2] for _, obj in objects if (match := FIGURE.fullmatch(obj["label"]))}
    digest, blocks = extract_pdf(pdf, labels)
    ok = True
    for path, obj in objects:
        label = FIGURE.fullmatch(obj["label"])
        candidates = blocks.get(label[2], []) if label else []
        if len(candidates) != 1:
            print(f"{path.parent}: {len(candidates)} caption blocks for {obj['label']}", file=sys.stderr)
            ok = False
            continue
        page, caption, wraps = candidates[0]
        caption_source = {"type": "pdf", "file": pdf.name, "sha256": digest, "page": page,
                          "version": provenance["version"], "url": provenance["url"]}
        # Publish under the scrapbook lock, re-reading current object.yaml so concurrent edits
        # (such as archive marks) are preserved and an existing caption.md is never overwritten.
        lock = add_scrap.vaults.Lock(add_scrap.ROOT, "another run is writing this scrapbook") if add_scrap.ROOT else None
        try:
            caption_dest = path.with_name("caption.md")
            if caption_dest.exists():
                continue
            latest = yaml.safe_load(path.read_text()) if path.exists() else {}
            if not isinstance(latest, dict):
                raise ValueError(f"Expected a mapping in {path}")
            latest["caption_source"] = caption_source
            obj_text = yaml.safe_dump(latest, sort_keys=False, allow_unicode=True, width=120)
            add_scrap.vaults.replace(path, obj_text.encode("utf-8"))
            add_scrap.vaults.replace(caption_dest, caption.encode("utf-8"))
        finally:
            if lock is not None:
                lock.close()
        dest = path.parent.relative_to(add_scrap.ROOT) if path.is_relative_to(add_scrap.ROOT) else path.parent
        print(f"ok   {dest} (PDF p. {page})")
        for wrap in wraps:
            if wrap == WITHOUT_LOCATOR:
                print("     check on the printed page: read without the locator, from the label's own paragraph")
            else:
                print(f"     check printed hyphen: {wrap}")
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-dir", type=Path,
                        help="directory of <citationKey>.pdf files (default: .cache/pdf in the scrapbook)")
    parser.add_argument("--scrapbook", type=Path, help="scrapbook folder (default: see tools/paths.py)")
    args = parser.parse_args()
    add_scrap.use_scrapbook(args.scrapbook)
    pdf_dir = args.pdf_dir or add_scrap.CACHE / "pdf"
    try:
        locator_jar()
    except FileNotFoundError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    pending = defaultdict(list)
    for path in sorted((add_scrap.ROOT / "scraps").glob("*/*/object.yaml")):
        if not path.with_name("caption.md").exists():
            label = FIGURE.fullmatch(yaml.safe_load(path.read_text()).get("label") or "")
            # Supplementary figures (Figure S1, S2 …) are read from <citationKey>.supplement.pdf.
            name = f"{path.parent.parent.name}{'.supplement' if label and label[2].upper().startswith('S') else ''}.pdf"
            pending[name].append(path)
    ok = True
    for name, scraps in pending.items():
        pdf = pdf_dir / name
        if not pdf.is_file():
            print(f"skip {pdf.stem}: missing {pdf.name}")
            continue
        try:
            if not capture_paper(pdf, scraps):
                ok = False
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"FAIL {pdf}: {exc}", file=sys.stderr)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
