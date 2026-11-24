"""Write a Tolaria vault of card notes for papers, scraps and snippets, and the terms they use.

A card is a view of the source files: generated, never edited by hand. The vault is a separate
folder outside the repository, so source files do not appear in Tolaria and Tolaria's own
frontmatter writes (view state such as `_width`) never touch the repository.
Each card carries what Tolaria reads: H1 title, `type:`, wikilink relations. Images are copied
into `assets/`.

Relations (Tolaria treats any field holding wikilinks as one; belongs_to/related_to/has have inverses,
and related_to shows in both directions):
  Scrap   belongs_to Paper; related_to the snippets and terms of its panels and matched colormaps
  Paper   related_to its domain terms (its scraps appear under the inverse `has`)
  Snippet related_to the chart and element terms drawn in its image (about:)
Snippet and term cards list Examples: the scraps whose panels use the term, with a thumbnail.
Term cards also list the terms used together with it in the same figures.
Scraps whose object.yaml says `archived: true` are left out of Examples and Used together.

The sources are only read: the vault is written, never the scrapbook. Frontmatter keys starting with `_`
that Tolaria added to a card are carried over; a new scrap card starts with `_archived: true` when its
object.yaml says `archived: true`. Archiving or unarchiving a card in Tolaria changes the vault only; the
run says how many scrap cards differ from their object.yaml, and tools/archive_import.py copies the
vault's marks into the scrapbook. See docs/integrations.md (Tolaria) and tools/vault.py.

Snippets and the chart and element vocabularies come from the tool root; papers, scraps and
vocab/domain.yaml from the scrapbook (tools/paths.py), read once into one set (tools/index.py). The vault's
manifest names its scrapbook: with no scrapbook, one without scraps/, or another scrapbook than the
manifest's (unless --force), nothing is written or removed (exit 2). Nothing is either when a source does
not read whole (a file or folder that cannot be read, a scrap without its paper; exit 1), when the
manifest does not read (exit 1), when two cards or images would be one file (the same name, or names
equal but for case or Unicode normalization; exit 2), or when the vault's table stops (a file of the
user's, or one the user changed, would be written or removed; exit 2). A run stopped while writing says
how many files it wrote and exits 1; running again finishes. A card is removed only when it is byte for
byte what the tool last wrote. Two snippets that share an id (in two categories) get cards named
snippet-<category>-<id>; every other snippet card is snippet-<id>.

A vault written by an older Cedalion (a manifest without hashes) stops the run, naming its cards with
the user's `_` values and the user's other files. One step makes a new vault from it, and keeps the old one
as it is: --from OLD writes the cards into the empty folder --vault, with each card's `_` lines from OLD
(never the rest of an old note), copies the user's files, and reads the new vault back.

Usage: python tools/cards.py --vault PATH [--scrapbook PATH] [--force] [--from OLD_VAULT]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path


import index
import vault as vaults
from palettes import GGPLOT_HUE, key_text, scheme_png, swatch_png
from paths import TOOL_ROOT, for_command
from vault import frontmatter

# Type notes live at the vault root, where Tolaria looks for them.
# _list_properties_display names the properties shown under each title in the note list.
TYPES = {
    "paper.md": {"type": "Type", "_icon": "book-open", "_sidebar_label": "Papers", "_order": 0,
                 "_list_properties_display": ["journal", "year"]},
    "scrap.md": {"type": "Type", "_icon": "image", "_sidebar_label": "Scraps", "_order": 1,
                 "_list_properties_display": ["paper_title", "chart"]},
    "snippet.md": {"type": "Type", "_icon": "code", "_sidebar_label": "Snippets", "_order": 2,
                   "_list_properties_display": ["category"]},
    "chart.md": {"type": "Type", "_icon": "chart-bar", "_sidebar_label": "Charts", "_order": 3},
    "element.md": {"type": "Type", "_icon": "shapes", "_sidebar_label": "Elements", "_order": 4},
    "colormap.md": {"type": "Type", "_icon": "palette", "_sidebar_label": "Colormaps", "_order": 5,
                    "_list_properties_display": ["source"]},
    "domain.md": {"type": "Type", "_icon": "tag", "_sidebar_label": "Domains", "_order": 6},
}
TERMS = {"chart": "Chart", "element": "Element", "domain": "Domain"}  # vocab file -> note type


def link(note_name: str) -> str:
    return f"[[{note_name}]]"


def colormap_note(name: str) -> str:
    return "colormap-" + re.sub(r"[^A-Za-z0-9_-]", "-", name)


def short_name(item: dict) -> str:
    """'Láng-Ritter et al. 2025', the form SKILL.md uses to cite objects."""
    authors = [c.get("lastName") or c.get("name") for c in item.get("creators") or []
               if c.get("creatorType") == "author"]
    year = str(item.get("date") or "")[:4]
    if not authors:
        who = "Anonymous"
    elif len(authors) == 1:
        who = authors[0]
    elif len(authors) == 2:
        who = f"{authors[0]} and {authors[1]}"
    else:
        who = f"{authors[0]} et al."
    return f"{who} {year}".strip()


def note(fields: dict, body: list[str]) -> str:
    fields = {k: v for k, v in fields.items() if v not in (None, [], "")}
    return "---\n" + frontmatter(fields) + "---\n\n" + "\n".join(body)


def demote(md: str) -> str:
    """Nest a file's headings one level under the card's own section heading."""
    return re.sub(r"^(#+) ", r"#\1 ", md.strip(), flags=re.M)


HIGHLIGHT = "#ff00cc"


def highlight(figure: bytes, boxes: list[list[int]], detail: bool) -> bytes | None:
    """A derived image, never the scrap itself: the figure with an outline on where the element
    sits and, for a small element, an enlarged view of it and its surroundings below. None when the
    boxes cover most of the figure (the whole figure is the example)."""
    from PIL import Image, ImageDraw

    img = Image.open(io.BytesIO(figure)).convert("RGB")
    area = sum(w * h for _, _, w, h in boxes)
    if area > 0.5 * img.width * img.height:
        return None
    if detail:
        boxes = boxes[:1]  # one representative, matched by the enlarged view below

    def outline(im, box, scale, ox=0, oy=0):
        draw = ImageDraw.Draw(im)
        x, y, w, h = box
        x0, y0, x1, y1 = (round(v) for v in ((x - ox) * scale, (y - oy) * scale, (x + w - ox) * scale, (y + h - oy) * scale))
        line, edge = 6, 2  # a saturated line between two white edges, visible on dark and light ground
        draw.rectangle([x0 - line - 2 * edge, y0 - line - 2 * edge, x1 + line + 2 * edge, y1 + line + 2 * edge], outline="white", width=edge)
        draw.rectangle([x0 - line - edge, y0 - line - edge, x1 + line + edge, y1 + line + edge], outline=HIGHLIGHT, width=line)
        draw.rectangle([x0 - edge, y0 - edge, x1 + edge, y1 + edge], outline="white", width=edge)

    scale = 1200 / img.width
    out = img.resize((1200, round(img.height * scale)))
    for box in boxes:
        outline(out, box, scale)
    if detail:
        x, y, w, h = boxes[0]
        m = 0.06 * max(img.width, img.height)  # enough surroundings to see where the element sits
        mx, my = max(w / 4, m), max(h / 4, m)
        x0, y0 = max(0, round(x - mx)), max(0, round(y - my))
        x1, y1 = min(img.width, round(x + w + mx)), min(img.height, round(y + h + my))
        if (x1 - x0) * (y1 - y0) < 0.5 * img.width * img.height:  # otherwise the figure above already shows it
            zoom = min(2.0, 1200 / (x1 - x0))  # at most twice the scrap's pixels, so nothing turns to blur
            crop = img.crop((x0, y0, x1, y1))
            crop = crop.resize((round(crop.width * zoom), round(crop.height * zoom)))
            outline(crop, boxes[0], zoom, x0, y0)
            sheet = Image.new("RGB", (1200, out.height + 24 + crop.height), "white")
            sheet.paste(out, (0, 0))
            sheet.paste(crop, ((1200 - crop.width) // 2, out.height + 24))
            ImageDraw.Draw(sheet).line([(0, out.height + 12), (1200, out.height + 12)], fill=(200, 200, 200), width=2)
            out = sheet
    buffer = io.BytesIO()
    out.save(buffer, "PNG")
    return buffer.getvalue()


class Highlights:
    """highlight() for each figure, boxes and detail once in a build: term and snippet cards show the same.
    A figure that does not open is kept in `problems`; build raises them."""

    def __init__(self):
        self.made: dict[tuple, bytes | None] = {}
        self.problems: list[str] = []

    def __call__(self, path: Path, figure: bytes, boxes: list[list[int]], detail: bool) -> bytes | None:
        key = (path, tuple(map(tuple, boxes)), detail)
        if key not in self.made:
            try:
                self.made[key] = highlight(figure, boxes, detail)
            except (OSError, ValueError) as error:  # PIL's UnidentifiedImageError is an OSError
                self.problems.append(f"{path}: the image does not open ({error})")
                self.made[key] = None
        return self.made[key]


def examples(term: str, scraps: list[dict], draw: Highlights) -> tuple[list[str], dict[str, bytes]]:
    """A thumbnail and link for each scrap whose panels use the term; where the scrap records
    where the term sits (a region, or the panels' boxes), the thumbnail highlights it."""
    lines, assets = [], {}
    for s in scraps:
        if term in s["terms"] and not s["archived"]:
            image = s["image"]
            if (boxes := s["boxes"].get(term)) and (data := draw(s["path"], s["figure"], boxes, term in s["regions"])):
                # The name carries a content hash: a viewer that caches images by name shows a redrawn one.
                image = f"{s['note']}--{term}--highlight-{hashlib.sha1(data).hexdigest()[:8]}.png"
                assets[image] = data
            lines += [f"- [[{s['note']}|{s['title']}]]", f"  ![{s['title']}|200](assets/{image})"]
    return (["## Examples", "", *lines, ""] if lines else []), assets


def snippet_names(found: list[index.Snippet]) -> dict[tuple[str, str], str]:
    """Card names: snippet-<id>, and snippet-<category>-<id> for an id two categories share."""
    shared = index.shared_ids(found)
    names = {s.key: f"snippet-{s.category}-{s.id}" if s.id in shared else f"snippet-{s.id}" for s in found}
    if len(set(names.values())) < len(names):
        clash = sorted(n for n in set(names.values()) if list(names.values()).count(n) > 1)
        raise ValueError(f"two snippets would have the card {', '.join(clash)}; rename one of them")
    return names


def snippet_cards(root: Path, found: list[index.Snippet], names: dict, terms: dict[str, set[str]], scraps: list[dict],
                  draw: Highlights) -> tuple[dict[str, str], dict[str, Path | bytes]]:
    """Cards for snippets, and their images."""
    cards, assets = {}, {}
    for snippet in found:
        d, meta, body = snippet.folder, snippet.meta, snippet.body
        name = names[snippet.key]
        if snippet.png is not None:
            assets[f"{name}.png"] = snippet.png
            body = body.replace("](snippet.png)", f"](assets/{name}.png)")
        # The terms drawn in its image; Tolaria shows related_to in both directions.
        drawn = [link(f"{vocab}-{t}") for t in meta.get("about") or [d.name]
                 for vocab in ("chart", "element") if t in terms[vocab]]
        fields = {"type": "Snippet", "category": meta.get("category"), "related_to": drawn,
                  "requires": meta.get("requires")}
        code = (snippet.code or "").rstrip()
        shown, extra = examples(d.name, scraps, draw)
        assets.update(extra)
        cards[f"{name}.md"] = note(fields, [body.strip(), "", *shown, "## Code", "",
                                            f"`{d.relative_to(root).as_posix()}/snippet.py`", "",
                                            "```python", code, "```", ""])
    return cards, assets


def scrap_card(scrap: index.Scrap, book: Path, item: dict, snippets: dict[str, list[str]]
               ) -> tuple[str, str, dict[str, bytes]]:
    d, obj = scrap.folder, scrap.obj
    panels = obj.get("panels") or []
    union = lambda key: sorted({t for p in panels for t in p.get(key) or []})  # noqa: E731
    name = f"{d.parent.name}-{d.name}"
    palettes = (scrap.palette or {}).get("palettes")
    schemes = sorted({p["colormap"] for p in palettes or [] if p.get("colormap")})
    fields = {
        "type": "Scrap",
        "belongs_to": link(d.parent.name),
        "paper_title": item.get("title"),
        # Snippets first, then plot types, elements and color schemes.
        "related_to": ([link(n) for s in union("chart") + union("element") for n in snippets.get(s, [])]
                       + [link(f"chart-{t}") for t in union("chart")]
                       + [link(f"element-{t}") for t in union("element")]
                       + [link(colormap_note(s)) for s in schemes]),
        "chart": union("chart"),  # plain names, shown as chips in the note list
        "kind": obj.get("kind"),
        "label": obj.get("label"),
        "rights": obj.get("rights"),
    }
    assets = {}
    # Two sections: the figure as drawn, then where it comes from. The image comes first, so a link
    # preview shows it.
    body = [f"# {short_name(item)}, {obj.get('label')}", "", "## Figure", ""]
    for i, f in enumerate(obj.get("files") or []):
        asset = f"{name}{'' if i == 0 else f'-{i + 1}'}{Path(f['path']).suffix}"
        assets[asset] = scrap.files[f["path"]]
        body += [f"![](assets/{asset})", ""]
    for file, heading in (("description.md", "Description"), ("notes.md", "Notes")):
        if file in scrap.texts:
            body += [f"### {heading}", "", demote(demote(scrap.texts[file])), ""]
        if file == "description.md" and palettes:
            # The swatch image is drawn from palette.yaml at build time; it is not a repository file.
            assets[f"{name}-palette.png"] = swatch_png(palettes)
            body += ["### Palette", "", f"![](assets/{name}-palette.png)", ""]
            for p in palettes:
                facts = [p["type"]]
                if p.get("bar"):
                    classes = all("range" in c for c in p["colors"])
                    facts.append(f"color bar, {len(p['colors'])} classes" if classes else "color bar, continuous")
                if p.get("steps"):
                    used = ", ".join(str(c["step"]) for c in p["colors"])
                    facts.append(f"matches {p['colormap']} cut into {p['steps']}, colors {used}")
                elif p.get("colormap"):
                    facts.append(f"matches {p['colormap']}")
                facts.append(f"panels {', '.join(map(str, p.get('panels') or []))}")
                body += [f"**{p['title']}** ({'; '.join(facts)})", "",
                         "| Key | Hex |", "|---|---|"]
                body += [f"| {key_text(c)} | `{c['hex']}` |" for c in p["colors"]]
                body.append("")
    body += ["## Source", "", f"- Paper: [[{d.parent.name}|{short_name(item)}]], {obj.get('label')}"]
    if obj.get("rights"):
        body.append(f"- Rights: {obj.get('rights')}")
    body += [f"- Folder: `{d.relative_to(book).as_posix()}/`", ""]
    if "caption.md" in scrap.texts:
        body += ["### Caption", "", demote(demote(scrap.texts["caption.md"])), ""]
    return f"{name}.md", note(fields, body), assets


def figure_order(d: Path) -> tuple:
    """fig-2 before fig-10, and main figures before supplementary ones (fig-s1) and tables."""
    m = re.fullmatch(r"([a-z]+)-(s?)(\d+)(.*)", d.name)
    return (m[1] != "fig", m[1], m[2], int(m[3]), m[4]) if m else (True, d.name, "", 0, "")


def paper_card(d: Path, item: dict, scraps: list[index.Scrap]) -> tuple[str, str]:
    fields = {
        "type": "Paper",
        "authors": ", ".join(
            f"{c.get('firstName', '')} {c.get('lastName', '')}".strip() or c.get("name", "")
            for c in item.get("creators") or []
            if c.get("creatorType") == "author"
        ),
        "year": str(item.get("date") or "")[:4],
        "journal": item.get("publicationTitle"),
        "DOI": item.get("DOI"),
        "url": item.get("url"),
        "related_to": [link(f"domain-{t['tag']}") for t in item.get("tags") or []],
    }
    body = [f"# {short_name(item)}: {item.get('title')}", ""]
    if scraps:
        body += ["## Scraps", ""]
        body += [f"- [[{d.name}-{s.slug}|{s.obj.get('label')}]]" for s in scraps]
        body.append("")
    body += ["## Source", "", f"`papers/{d.name}/`", ""]
    return f"{d.name}.md", note(fields, body)


def together(term: str, scraps: list[dict], kinds: dict[str, str]) -> list[str]:
    """Terms used in the same figures as this one, most often first."""
    counts = {}
    for s in scraps:
        if term in s["terms"] and not s["archived"]:
            for other in s["terms"] - {term}:
                counts[other] = counts.get(other, 0) + 1
    if not counts:
        return []
    lines = [f"- [[{kinds[t]}-{t}]] ({n})" for t, n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    return ["## Used together", "", "Figures that use this term also use (number of figures):", "", *lines, ""]


def drawn_by(term: str, by_term: dict[str, list[index.Snippet]], names: dict) -> list[str]:
    """The snippets whose image draws the term (their about: list), with a thumbnail."""
    lines = []
    for snippet in by_term.get(term, []):
        name, title = names[snippet.key], snippet.title or snippet.id
        image = f"  ![{title}|200](assets/{name}.png)" if snippet.has("snippet.png") else None
        lines += [f"- [[{name}|{title}]]", *([image] if image else [])]
    return ["## Snippets", "", *lines, ""] if lines else []


def term_cards(definitions: dict[str, dict], scraps: list[dict], draw: Highlights, by_term: dict, names: dict
               ) -> tuple[dict[str, str], dict[str, set[str]], dict[str, bytes]]:
    """One note per vocabulary term; the scraps, papers and snippets using it link to it."""
    cards, terms, assets = {}, {}, {}
    kinds = {t: v for v in ("chart", "element") for t in definitions[v]}
    for vocab, kind in TERMS.items():
        terms[vocab] = set(definitions[vocab])
        for term, entry in definitions[vocab].items():
            # Titled by the common name; the term id is what object.yaml and item.yaml use.
            extra = []
            if vocab != "domain":
                shown, images = examples(term, scraps, draw)
                assets.update(images)
                extra = [*shown, *drawn_by(term, by_term, names), *together(term, scraps, kinds)]
            cards[f"{vocab}-{term}.md"] = note({"type": kind, "term": term},
                                               [f"# {entry['name']}", "", str(entry["definition"]), "",
                                                *extra, "## Source", "", f"`vocab/{vocab}.yaml`", ""])
    return cards, terms, assets


def colormap_cards(palettes: list[dict]) -> tuple[dict[str, str], dict[str, bytes], list[tuple[str, str]]]:
    """One note per named color scheme that a palette matches, with an image of the scheme."""
    cards, assets, origins = {}, {}, []
    names = sorted({p["colormap"] for data in palettes for p in data["palettes"] if p.get("colormap")})
    for name in names:
        source = ("ggplot2 (R)" if name == GGPLOT_HUE else "Crameri scientific color maps (cmcrameri)"
                  if name.startswith("cmc.") else "matplotlib")
        stem = colormap_note(name)
        assets[f"{stem}.png"] = scheme_png(name)
        cards[f"{stem}.md"] = note({"type": "Colormap", "source": source},
                                   [f"# {name}", "", f"![](assets/{stem}.png)", "", f"Source: {source}.", ""])
        origins += [(f"{stem}.md", f"colormap {name}"), (f"assets/{stem}.png", f"colormap {name}")]
    return cards, assets, origins


def scrap_index(scraps: list[index.Scrap], items: dict[str, dict]) -> list[dict]:
    """One entry per scrap with an image: its card name, short title, first image asset, panel terms,
    archived flag."""
    entries = []
    for scrap in scraps:
        d, obj = scrap.folder, scrap.obj
        item = items.get(scrap.paper) or {}
        files = obj.get("files") or []
        if not files:
            continue
        name = f"{scrap.paper}-{scrap.slug}"
        boxes = {}
        for region in obj.get("regions") or []:
            boxes.setdefault(region["term"], []).append(region["xywh"])
        for p in obj.get("panels") or []:
            for t in (p.get("chart") or []) + (p.get("element") or []):
                if p.get("xywh") and not any(r["term"] == t for r in obj.get("regions") or []):
                    boxes.setdefault(t, []).append(p["xywh"])
        entries.append({"note": name, "title": f"{short_name(item)}, {obj.get('label')}",
                        "image": f"{name}{Path(files[0]['path']).suffix}", "path": d / files[0]["path"],
                        "figure": scrap.files[files[0]["path"]], "boxes": boxes,
                        "regions": {r["term"] for r in obj.get("regions") or []},
                        "terms": {t for p in obj.get("panels") or [] for k in ("chart", "element") for t in p.get(k) or []},
                        "archived": bool(obj.get("archived"))})
    return entries


def build(found: index.Sources) -> tuple[dict[str, str], dict[str, bytes]]:
    """Cards from a whole source set (tools/index.py, read with images): the tool root's snippets and
    vocabularies, the scrapbook's papers, scraps and domains. Raises index.Unreadable when a figure does not
    open, ValueError when two sources would write the same vault file."""
    root, book = found.root, found.book
    snippets = found.snippets
    names = snippet_names(snippets)
    by_term: dict[str, list[index.Snippet]] = {}
    for snippet in snippets:
        for term in dict.fromkeys(snippet.about):
            by_term.setdefault(term, []).append(snippet)
    by_id: dict[str, list[str]] = {}
    for snippet in snippets:
        by_id.setdefault(snippet.id, []).append(names[snippet.key])
    scraps = found.scraps
    items = {paper.key: paper.item for paper in found.papers}
    entries = scrap_index(scraps, items)
    draw = Highlights()
    definitions = {vocab: found.vocab.get(vocab, {}) for vocab in TERMS}

    cards = {name: note(fields, [f"# {name[:-3].capitalize()}", ""]) for name, fields in TYPES.items()}
    origins = [(name, f"type {name[:-3]}") for name in TYPES]
    cards_t, terms, assets_t = term_cards(definitions, entries, draw, by_term, names)
    cards.update(cards_t)
    origins += [(name, f"term {name[:-3]}") for name in cards_t]
    origins += [(f"assets/{a}", f"highlight {a}") for a in assets_t]
    cards_c, assets_c, origins_c = colormap_cards([s.palette for s in scraps if s.palette])
    cards.update(cards_c)
    origins += origins_c
    cards_s, assets = snippet_cards(root, snippets, names, terms, entries, draw)
    for snippet in snippets:
        sname = names[snippet.key]
        origins.append((f"{sname}.md", f"snippet {snippet.category}/{snippet.id}"))
        if snippet.png is not None:
            origins.append((f"assets/{sname}.png", f"snippet {snippet.category}/{snippet.id}"))
    origins += [(f"assets/{a}", f"highlight {a}") for a in assets if "--highlight-" in a]
    assets.update(assets_c)
    assets.update(assets_t)
    cards.update(cards_s)
    for paper in found.papers:
        d, item = paper.folder, paper.item
        mine = sorted((s for s in scraps if s.paper == d.name), key=lambda s: figure_order(s.folder))
        name, text = paper_card(d, item, mine)
        cards[name] = text
        origins.append((name, f"paper {d.name}"))
        for s in mine:
            name, text, a = scrap_card(s, book, item, by_id)
            cards[name] = text
            assets.update(a)
            origins.append((name, f"scrap {s.paper}/{s.slug}"))
            origins += [(f"assets/{k}", f"scrap {s.paper}/{s.slug}") for k in a]
    if draw.problems:
        raise index.Unreadable(draw.problems)
    if clash := vaults.collisions(origins):
        raise ValueError("two sources would write the same vault file: " + "; ".join(clash))
    return cards, assets


def initial_marks(scraps: list[index.Scrap], keep: set[str] = frozenset()) -> dict[str, list[str]]:
    """The first `_` lines for new scrap cards: `_archived: true` when object.yaml says `archived: true`,
    except for cards in KEEP (present in an older vault being migrated)."""
    return {f"{s.paper}-{s.slug}.md": [f"{vaults.ARCHIVED}: true\n"]
            for s in scraps if s.obj.get("archived") and f"{s.paper}-{s.slug}.md" not in keep}


def card_user_lines(name: str, seen: dict[str, vaults.Seen], initial: dict[str, list[str]],
                    override_view: dict[str, list[str]]) -> list[str]:
    if name in override_view:
        return list(override_view[name])
    found = seen.get(name)
    if found and found.state == "user":
        return list(found.user)
    if not found or found.state == "absent":
        return list(initial.get(name, []))
    return []


def sync_overrides(scraps: list[index.Scrap], seen: dict[str, vaults.Seen],
                   agreed: dict[str, bool]) -> dict[str, list[str]]:
    """For --sync-from-book: update `_archived` on existing cards whose scrapbook changed upstream
    (book_changed) or that are archived in the scrapbook without a vault checkpoint (unreconciled R=True, V=False)."""
    overrides: dict[str, list[str]] = {}
    for s in scraps:
        name = f"{s.paper}-{s.slug}.md"
        found = seen.get(name)
        if not found or found.state not in ("written", "user"):
            continue
        r = bool(s.obj.get("archived"))
        v = vaults.archived(found.user)
        b = agreed.get(f"{s.paper}/{s.slug}")
        status = vaults.archive_status(r, v, b)
        if status == "book_changed" or (status == "unreconciled" and r and not v):
            overrides[name] = vaults.with_archived_mark(found.user, r)
    return overrides


def next_agreed(scraps: list[index.Scrap], seen: dict[str, vaults.Seen], initial: dict[str, list[str]],
                override_view: dict[str, list[str]], prev: dict[str, bool]) -> dict[str, bool]:
    """Update the per-scrap agreed checkpoint ONLY where R == V after this run; preserve existing B where
    R != V so upstream changes and local changes remain distinguishable."""
    out: dict[str, bool] = {}
    for s in scraps:
        key = f"{s.paper}/{s.slug}"
        name = f"{s.paper}-{s.slug}.md"
        r = bool(s.obj.get("archived"))
        v = vaults.archived(card_user_lines(name, seen, initial, override_view))
        if r == v:
            out[key] = r
        elif key in prev:
            out[key] = prev[key]
    return out


def report_archive_status(book: Path, vault: Path, vault_id: str, scraps: list[index.Scrap],
                          seen: dict[str, vaults.Seen], initial: dict[str, list[str]],
                          override_view: dict[str, list[str]], agreed: dict[str, bool]) -> None:
    """Print clear, separate lines for scrapbook-side archive changes vs local vault archive differences."""
    book_changed, unreconciled_book, local_diff = [], [], []
    for s in scraps:
        key = f"{s.paper}/{s.slug}"
        name = f"{s.paper}-{s.slug}.md"
        r = bool(s.obj.get("archived"))
        v = vaults.archived(card_user_lines(name, seen, initial, override_view))
        status = vaults.archive_status(r, v, agreed.get(key))
        if status == "book_changed":
            book_changed.append(key)
        elif status == "unreconciled" and r and not v:
            unreconciled_book.append(key)
        elif status in ("vault_changed", "unreconciled"):
            local_diff.append(key)
    if book_changed:
        noun = "card changed" if len(book_changed) == 1 else "cards changed"
        print(f"{len(book_changed)} scrap {noun} in the scrapbook since this vault last agreed "
              f"({', '.join(book_changed[:5])}{' ...' if len(book_changed) > 5 else ''}): "
              f"run pixi run cards --vault \"{vault}\" --sync-from-book to update vault cards")
    if unreconciled_book:
        noun = "card is" if len(unreconciled_book) == 1 else "cards are"
        print(f"{len(unreconciled_book)} scrap {noun} archived in the scrapbook without a vault mark "
              f"({', '.join(unreconciled_book[:5])}{' ...' if len(unreconciled_book) > 5 else ''}): "
              f"run pixi run cards --vault \"{vault}\" --sync-from-book to mark them in this vault")
    if local_diff:
        owner, _ = vaults.is_archive_owner(book, vault, vault_id)
        if owner:
            noun = "card differs" if len(local_diff) == 1 else "cards differ"
            print(f"{len(local_diff)} scrap {noun} from object.yaml in archive mark: "
                  f"run pixi run archive-import --vault \"{vault}\"")
        else:
            noun = "card has" if len(local_diff) == 1 else "cards have"
            print(f"{len(local_diff)} scrap {noun} personal archive marks in this vault "
                  "(reader; only the owner vault updates object.yaml)")


def report_older(vault: Path, book: Path, manifest: vaults.Manifest, older: vaults.Older) -> int:
    """Explain why an older vault (manifest version 1, without hashes) is not overwritten in place, list its
    cards with the user's `_` values and the user's personal files, and name the one step to make a new vault."""
    print(f"nothing written to {vault}: its {vaults.MANIFEST} is from an older Cedalion (without hashes), "
          "so it is kept as it is.", file=sys.stderr)
    if older.unread:
        print("Cards in it that could not be read:", file=sys.stderr)
        for line in older.unread:
            print(f"  {line}", file=sys.stderr)
    print(f"Cards in it with your `_` values ({len(older.carried)}):", file=sys.stderr)
    for name, lines in older.carried.items():
        keys = ", ".join(vaults.view_values(lines))
        print(f"  {name} ({keys})", file=sys.stderr)
    if older.gone:
        print(f"Cards in it with your `_` values that this scrapbook no longer makes ({len(older.gone)}):",
              file=sys.stderr)
        for name in older.gone:
            print(f"  {name}", file=sys.stderr)
    print(f"Your own files in it ({len(older.personal)}):", file=sys.stderr)
    for rel in older.personal:
        print(f"  {rel}", file=sys.stderr)
    new_vault = vault.with_name(vault.name + "-new")
    force_flag = " --force" if manifest.scrapbook not in (None, str(book)) else ""
    print(f"To make a new vault with those `_` values and your files (keeping {vault} as it is):\n"
          f"  pixi run cards --from \"{vault}\" --vault \"{new_vault}\" --scrapbook \"{book}\"{force_flag}",
          file=sys.stderr)
    return 2


def is_empty_dir(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return True
    return path.is_dir() and not path.is_symlink() and not any(path.iterdir())


def migrate(root: Path, book: Path, old: Path, vault: Path, force: bool) -> int:
    """Make a new vault at VAULT from the sources and carry over only the user's `_` lines and personal files
    from OLD, leaving OLD as it is. Staged in a sibling temporary directory and moved into place only once
    cards, personal files and links are verified."""
    if not is_empty_dir(vault):
        print(f"--from needs a new or empty --vault folder; {vault} already exists and is not empty.",
              file=sys.stderr)
        return 2
    book_lock = vaults.Lock(book, "another run is writing this scrapbook")
    old_lock = vaults.Lock(old, "another cards run is writing this vault")
    staging: Path | None = None
    try:
        old_manifest = vaults.read_manifest(old)
        if not old_manifest.there:
            print(f"{old} has no {vaults.MANIFEST}; nothing written to {vault}.", file=sys.stderr)
            return 2
        if old_manifest.scrapbook not in (None, str(book)) and not force:
            print(f"{old} was made from {old_manifest.scrapbook}, not {book}; nothing written. "
                  "Pass --force to build the new vault from this scrapbook.", file=sys.stderr)
            return 2
        found = index.sources(root, book, images=True).whole()
        try:
            cards, assets = build(found)
        except ValueError as problem:
            print(f"{problem}; nothing written.", file=sys.stderr)
            return 2
        older = vaults.survey_older(old, old_manifest, set(cards))
        if older.unread:
            raise index.Unreadable([f"{old / line}" for line in older.unread])
        if older.gone and not force:
            print(f"nothing written to {vault}; these cards in {old} carry your `_` values and are no longer made:",
                  file=sys.stderr)
            for name in older.gone:
                print(f"  {name}", file=sys.stderr)
            return 2
        made = {**{n: t.encode("utf-8") for n, t in cards.items()}, **{f"assets/{a}": d for a, d in assets.items()}}
        made_folded = {vaults.folded(n): n for n in made}
        clash = [f"{rel} (would collide with {made_folded[vaults.folded(rel)]})"
                 for rel in older.personal if vaults.folded(rel) in made_folded]
        if clash:
            print(f"nothing written to {vault}; your files in {old} would collide with generated cards:",
                  file=sys.stderr)
            for line in clash:
                print(f"  {line}", file=sys.stderr)
            return 2
        old_links = vaults.links(old, older.personal)
        initial = {**initial_marks(found.scraps, older.present), **older.carried}
        vault.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".cedalion-migrate-", dir=vault.parent))
        manifest = vaults.Manifest()
        seen = vaults.classify(staging, manifest, made)
        agreed = next_agreed(found.scraps, seen, initial, {}, {})
        planned = vaults.plan(book, manifest, seen, made, initial, agreed=agreed)
        vaults.write(staging, planned)
        vaults.copy_personal(old, staging, older.personal)
        wrong = vaults.verify(staging, planned) + vaults.verify_personal(old, staging, older.personal)
        for name, lines in older.carried.items():
            text = (staging / name).read_text(encoding="utf-8") if (staging / name).is_file() else ""
            split = vaults.view_lines(text)
            if split is None or split[1] != lines:
                wrong.append(name)
        new_links = vaults.links(staging, older.personal)
        broken_links = [f"{rel} -> [[{target}]]" for rel, targets in old_links.items()
                        for target in sorted(targets - new_links.get(rel, set()))]
        if wrong or broken_links:
            for item in wrong:
                print(f"verify failed in {vault}: {item}", file=sys.stderr)
            for item in broken_links:
                print(f"broken link in {vault}: {item}", file=sys.stderr)
            return 1
        if not is_empty_dir(vault):
            print(f"{vault} ceased to be empty during migration; nothing replaced.", file=sys.stderr)
            return 2
        if vault.exists():
            vault.rmdir()
        os.replace(staging, vault)
        staging = None
    except OSError as error:
        print(f"migration stopped ({error.filename or vault}: {error.strerror or error}); "
              f"{vault} was left clean, and {old} is untouched. Run again to retry.", file=sys.stderr)
        return 1
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        old_lock.close()
        book_lock.close()
    print(f"{len(cards)} notes and {len(assets)} images in {vault} "
          f"(carried `_` values of {len(older.carried)} cards and copied {len(older.personal)} personal paths "
          f"from {old}, which was left as it was)")
    report_archive_status(book, vault, planned.vault_id, found.scraps, seen, initial, {}, planned.agreed)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vault", type=Path, required=True, help="Tolaria vault folder outside the repository")
    ap.add_argument("--scrapbook", type=Path, help="scrapbook folder (default: see tools/paths.py)")
    ap.add_argument("--force", action="store_true", help="rewrite a vault made from another scrapbook")
    ap.add_argument("--sync-from-book", action="store_true",
                    help="copy archive marks that changed in the scrapbook into this vault's cards")
    ap.add_argument("--from", dest="from_vault", type=Path, metavar="OLD_VAULT",
                    help="make a new vault in --vault carrying `_` values and personal files from OLD_VAULT")
    args = ap.parse_args()
    root, book, vault = TOOL_ROOT, for_command(args.scrapbook, part="scraps"), args.vault.expanduser().resolve()
    if book is None:
        print(f"no scrapbook found; not writing {vault}, so its cards stay as they are. "
              "Pass --scrapbook PATH or set CEDALION_SCRAPBOOK.", file=sys.stderr)
        return 2
    if any(vault == r or r in vault.parents for r in (root, book)):
        ap.error("the vault must be outside the tool root and the scrapbook")
    if args.from_vault is not None:
        old = args.from_vault.expanduser().resolve()
        if any(old == r or r in old.parents for r in (root, book)):
            ap.error("--from vault must be outside the tool root and the scrapbook")
        if old == vault or old in vault.parents or vault in old.parents:
            ap.error("--from and --vault must be separate folders")
    try:
        if args.from_vault is not None:
            return migrate(root, book, args.from_vault.expanduser().resolve(), vault, args.force)
        return run(root, book, vault, args)
    except index.Unreadable as bad:
        for problem in bad.problems:
            print(f"does not read: {problem}", file=sys.stderr)
        print(f"nothing written to {vault}: cards are made from every file or not at all",
              file=sys.stderr)
        return 1


def run(root: Path, book: Path, vault: Path, args) -> int:
    """Read the vault's manifest and the sources, build, plan every write by the vault's table, then write
    (tools/vault.py). index.Unreadable from any read; vaults.Stop when a file of the user's is in the way."""
    book_lock = vaults.Lock(book, "another run is writing this scrapbook")
    lock = vaults.Lock(vault, "another cards run is writing this vault")
    try:
        manifest = vaults.read_manifest(vault)
        if manifest.older is not None:
            found = index.sources(root, book, images=True).whole()
            cards, _ = build(found)
            return report_older(vault, book, manifest, vaults.survey_older(vault, manifest, set(cards)))
        if manifest.scrapbook not in (None, str(book)) and not args.force:
            print(f"{vault} was made from {manifest.scrapbook}, not {book}; nothing written. "
                  "Use another --vault, or --force to rewrite it from this scrapbook.", file=sys.stderr)
            return 2
        found = index.sources(root, book, images=True).whole()
        try:
            cards, assets = build(found)
        except ValueError as problem:
            print(f"{problem}; nothing written.", file=sys.stderr)
            return 2
        made = {**{n: t.encode("utf-8") for n, t in cards.items()}, **{f"assets/{a}": d for a, d in assets.items()}}
        seen = vaults.classify(vault, manifest, made)
        initial = initial_marks(found.scraps)
        prev_agreed = manifest.agreed if manifest.scrapbook in (None, str(book)) else {}
        overrides = sync_overrides(found.scraps, seen, prev_agreed) if args.sync_from_book else {}
        agreed = next_agreed(found.scraps, seen, initial, overrides, prev_agreed)
        planned = vaults.plan(book, manifest, seen, made, initial, override_view=overrides, agreed=agreed)
        vaults.write(vault, planned)
        if wrong := vaults.verify(vault, planned):
            for name in wrong:
                print(f"verify failed in {vault}: {name}", file=sys.stderr)
            return 1
    except vaults.Stop as stop:
        print(f"nothing written to {vault}; these files of the vault are not as the tool last "
              "wrote them, or carry your values, and the run would change or remove them:", file=sys.stderr)
        for line in stop.lines:
            print(f"  {line}", file=sys.stderr)
        print("Move them out of the vault (or back as they were), or use another --vault.", file=sys.stderr)
        return 2
    except vaults.Partial as partial:
        print(f"stopped while writing {vault} ({partial.done} of {partial.total} files written: {partial.why}); "
              "run the command again to finish.", file=sys.stderr)
        return 1
    finally:
        lock.close()
        book_lock.close()
    print(f"{len(cards)} notes and {len(assets)} images in {vault} "
          f"({sum(n.endswith('.md') for n in planned.writes)} notes written, {len(planned.deletes)} removed)")
    report_archive_status(book, vault, planned.vault_id, found.scraps, seen, initial, overrides, planned.agreed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
