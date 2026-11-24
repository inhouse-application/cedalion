"""Validate papers, scraps and snippets, and report each scrap's level.

Levels are derived from the files present (docs/levels.md). Exit status is 1 if any error is found.
Snippets, styles and vocabularies come from the tool root; papers, scraps and vocab/domain.yaml from the
scrapbook (tools/paths.py). Without a scrapbook only the tool root is checked.

Usage: python tools/check.py [--quiet] [--scrapbook PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
from pathlib import Path

from PIL import Image

import index
import tokens
from check_palettes import check_palette, check_subset_evidence
from paths import TOOL_ROOT, for_command, shown

RIGHTS = re.compile(r"^(CC-[A-Z-]+-\d\.\d|CC0-1\.0|LicenseRef-[A-Za-z0-9.-]+|NOASSERTION)$")
NOT_STATED = "not stated"
# Version of the PDF a caption was copied from: version of record, accepted manuscript, or preprint.
PDF_VERSIONS = {"vor", "accepted-manuscript", "preprint"}
# A caption that is empty or only a label ("Fig. 2", "**Figure S3:**").
LABEL_ONLY = re.compile(r"(?:(?:supplementary\s+)?(?:fig(?:ure)?|table)\.?\s*[A-Z]?\d+[a-z]?\s*[.:|]?)?", re.I)


def label_only(caption: str) -> bool:
    """True for an empty caption or one that is only its label, once bold and italic marks are gone."""
    return bool(LABEL_ONLY.fullmatch(re.sub(r"[*_]", "", caption).strip()))


class Report:
    def __init__(self, book: Path | None = None) -> None:
        self.errors: list[str] = []
        self.roots = (book, TOOL_ROOT)

    def err(self, where: Path | str, msg: str) -> None:
        self.errors.append(f"{shown(where, *self.roots) if isinstance(where, Path) else where}: {msg}")


def check_paper(paper: index.Paper, r: Report, domains: set[str]) -> None:
    """A paper whose item.yaml read (tools/index.py): the fields a scrap's levels rely on, and its tags."""
    d, item = paper.folder, paper.item
    for field in ("itemType", "citationKey", "title", "creators", "date", "DOI"):
        if not item.get(field):
            r.err(d / "item.yaml", f"missing {field}")
    if item.get("citationKey") != d.name:
        r.err(d / "item.yaml", f"citationKey {item.get('citationKey')!r} differs from directory name")
    for tag in item.get("tags") or []:
        if tag.get("tag") not in domains:
            r.err(d / "item.yaml", f"tag {tag.get('tag')!r} not in vocab/domain.yaml")


def located(value, path: Path, field: str, r: Report) -> bool:
    """A Level 2 value is a mapping with a non-empty loc, or says 'not stated'."""
    if isinstance(value, list):
        return all(located(v, path, field, r) for v in value) and bool(value)
    if not isinstance(value, dict):
        r.err(path, f"{field}: expected a mapping with loc")
        return False
    texts = [v for k, v in value.items() if k != "loc"]
    if any(isinstance(t, str) and t.strip().lower() == NOT_STATED for t in texts):
        return True
    if not value.get("loc"):
        r.err(path, f"{field}: missing loc")
        return False
    if not any(t not in (None, "") for t in texts):
        r.err(path, f"{field}: empty value")
        return False
    return True


def check_paper_context(paper: index.Paper | None, r: Report) -> bool:
    if paper is None or paper.context is None:
        return False
    path, ctx = paper.folder / "context.yaml", paper.context
    ok = True
    for field in ("question", "method", "data", "region", "period", "n", "software"):
        if field not in ctx:
            r.err(path, f"missing {field}")
            ok = False
        elif not located(ctx[field], path, field, r):
            ok = False
    return ok


def nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def positive_int(value) -> bool:
    return type(value) is int and value >= 1


def check_source(source, path: Path, field: str, r: Report, *, caption: bool) -> bool:
    if not isinstance(source, dict) or source.get("type") not in ("jats", "pdf"):
        r.err(path, f"{field} needs a JATS or PDF source")
        return False
    if source["type"] == "jats":
        checks = {"id": nonempty}
        if caption:
            checks["element"] = nonempty
    else:
        checks = {
            "file": nonempty,
            "sha256": lambda v: isinstance(v, str) and re.fullmatch(r"[0-9a-fA-F]{64}", v),
            "version": lambda v: isinstance(v, str) and v in PDF_VERSIONS,
            "url": nonempty,
        }
        if caption:
            checks["page"] = positive_int
    valid = True
    for name, check in checks.items():
        if not check(source.get(name)):
            r.err(path, f"invalid or missing {field}.{name}")
            valid = False
    return valid


def check_boxes(obj: dict, obj_path: Path, size: tuple[int, int], r: Report) -> None:
    """Panel `xywh` and `regions` are pixel boxes inside files[0] (of SIZE); a region names a term its panels use."""
    width, height = size
    used = {t for p in obj.get("panels") or [] for k in ("chart", "element") for t in p.get(k) or []}

    def inside(box, where):
        ok = (isinstance(box, list) and len(box) == 4 and all(isinstance(n, int) and n >= 0 for n in box)
              and box[2] > 0 and box[3] > 0 and box[0] + box[2] <= width and box[1] + box[3] <= height)
        if not ok:
            r.err(obj_path, f"{where}: xywh must be four whole pixels inside the {width}x{height} image")

    for p in obj.get("panels") or []:
        if p.get("xywh") is not None:
            inside(p["xywh"], f"panel {p.get('id')}")
    for i, region in enumerate(obj.get("regions") or []):
        term = region.get("term") if isinstance(region, dict) else None
        if term not in used:
            r.err(obj_path, f"regions[{i}]: term {term!r} is not used by any panel")
        inside(region.get("xywh") if isinstance(region, dict) else None, f"regions[{i}]")


def scrap_files(scrap: index.Scrap, papers: dict, r: Report, v: dict[str, set[str]]) -> bool:
    """Level 0: where the figure comes from, under what rights, and its files with their hashes."""
    d, obj, obj_path, key = scrap.folder, scrap.obj, scrap.path, scrap.paper
    l0 = True
    for field in ("kind", "label", "label_source", "paper", "url", "contentUrl", "accessDate", "rights", "files"):
        if not obj.get(field):
            r.err(obj_path, f"missing {field}")
            l0 = False
    if obj.get("kind") and obj["kind"] not in v["kind"]:
        r.err(obj_path, f"kind {obj['kind']!r} not in vocab/kind.yaml")
        l0 = False
    if obj.get("paper") != key:
        r.err(obj_path, f"paper {obj.get('paper')!r} differs from directory {key!r}")
        l0 = False
    if key not in papers:
        r.err(obj_path, f"papers/{key}/item.yaml missing")
        l0 = False
    if obj.get("rights") and not RIGHTS.match(str(obj["rights"])):
        r.err(obj_path, f"rights {obj['rights']!r} is not an SPDX id, LicenseRef-… or NOASSERTION")
    for f in obj.get("files") or []:
        if f["path"] not in scrap.files:
            r.err(obj_path, f"file {f.get('path')!r} missing")
            l0 = False
        elif hashlib.sha256(scrap.files[f["path"]]).hexdigest() != f.get("sha256"):
            r.err(obj_path, f"sha256 of {f['path']} does not match")
            l0 = False
    return l0


def scrap_figure(scrap: index.Scrap, size: tuple[int, int], r: Report, v: dict[str, set[str]]
                 ) -> tuple[bool, bool, bool]:
    """Level 1: the caption and its source, the panels with their terms and boxes, the description.
    Whether each is complete: (caption, description, panels)."""
    d, obj, obj_path = scrap.folder, scrap.obj, scrap.path
    has_caption = "caption.md" in scrap.texts
    if has_caption and label_only(scrap.texts["caption.md"]):
        r.err(d / "caption.md", "caption has no text beyond its label")
        has_caption = False
    source = obj.get("caption_source")
    if has_caption and not source:
        r.err(obj_path, "caption.md exists but caption_source is empty")
        has_caption = False
    if source is not None and not check_source(source, obj_path, "caption_source", r, caption=True):
        has_caption = False
    has_desc = "description.md" in scrap.texts
    panels = obj.get("panels") or []
    panels_ok = bool(panels) and bool(obj.get("layout"))
    for p in panels:
        if not p.get("id"):
            r.err(obj_path, "panel without id")
            panels_ok = False
        if not p.get("chart"):
            r.err(obj_path, f"panel {p.get('id')}: no chart term")
            panels_ok = False
        for term in p.get("chart") or []:
            if term not in v["chart"]:
                r.err(obj_path, f"panel {p.get('id')}: chart {term!r} not in vocab/chart.yaml")
                panels_ok = False
        for term in p.get("element") or []:
            if term not in v["element"]:
                r.err(obj_path, f"panel {p.get('id')}: element {term!r} not in vocab/element.yaml")
                panels_ok = False
    check_boxes(obj, obj_path, size, r)
    layout = obj.get("layout") or {}
    if panels and layout.get("panels") != len(panels):
        r.err(obj_path, f"layout.panels={layout.get('panels')} but {len(panels)} panels listed")
        panels_ok = False
    if has_desc:
        text = scrap.texts["description.md"]
        for section in ("## alt-text", "## long-desc"):
            if section not in text:
                r.err(d / "description.md", f"missing section {section!r}")
                has_desc = False
        for p in panels:
            if p.get("id") not in (None, "-") and f"**{p['id']}**" not in text:
                r.err(d / "description.md", f"no long-desc entry for panel {p['id']}")
                has_desc = False
    return has_caption, has_desc, panels_ok


def scrap_context(scrap: index.Scrap, paper: index.Paper | None, r: Report, v: dict[str, set[str]]) -> bool | None:
    """Level 2: the scrap's role and claim with their locations, and the paper's context. None without
    a context.yaml."""
    ctx_path, ctx = scrap.folder / "context.yaml", scrap.context
    if ctx is None:
        return None
    l2 = True
    if ctx.get("role") not in v["role"]:
        r.err(ctx_path, f"role {ctx.get('role')!r} not in vocab/role.yaml")
        l2 = False
    claim = ctx.get("claim") or {}
    if not (claim.get("quote") and claim.get("loc")):
        r.err(ctx_path, "claim needs quote and loc")
        l2 = False
    if not check_paper_context(paper, r):
        l2 = False
    return l2


def check_scrap(scrap: index.Scrap, papers: dict[str, index.Paper], r: Report, v: dict[str, set[str]]) -> str:
    """The level (docs/levels.md) of a scrap whose object.yaml read (tools/index.py), reporting what keeps it
    from the next. PAPERS are the papers that read, by key."""
    if not scrap_files(scrap, papers, r, v):
        return "-"
    first = scrap.obj["files"][0]["path"]
    try:
        image = Image.open(io.BytesIO(scrap.files[first]))
    except (OSError, ValueError) as error:
        r.err(scrap.folder / first, f"the image does not open ({error})")
        return "-"
    if scrap.palette is not None:
        check_palette(scrap.folder / "palette.yaml", scrap.palette, scrap.obj, image, r)
    has_caption, has_desc, panels_ok = scrap_figure(scrap, image.size, r, v)
    if not (has_caption and has_desc and panels_ok):
        return "0 (+description)" if has_desc and panels_ok else "0"
    if not scrap_context(scrap, papers.get(scrap.paper), r, v):
        return "1"
    return "3" if "notes.md" in scrap.texts else "2"


def check_tokens(r: Report) -> None:
    tree = tokens.load()
    for problem in tokens.problems(tree):
        r.err(tokens.TOKENS, problem)
    for path, text in tokens.sheets(tree).items():
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            r.err(path, "differs from styles/cedalion.tokens.json; run python tools/tokens.py")


def check_snippets(found: index.Sources, r: Report) -> set[str]:
    """The snippets that read (the set reports the others)."""
    ids = set()
    names = {term: entry.get("name", "") for vocab in ("chart", "element") for term, entry in found.vocab[vocab].items()}
    for snippet in found.snippets:
        d, md, meta = snippet.folder, snippet.folder / "snippet.md", snippet.meta
        if snippet.error:
            continue
        if meta.get("id") != d.name:
            r.err(md, f"id {meta.get('id')!r} differs from directory name")
        if meta.get("category") != d.parent.name:
            r.err(md, f"category {meta.get('category')!r} differs from parent directory")
        title = snippet.title or ""
        name = names.get(d.name)
        # The title is the term's common name; only a named variant may precede it ("Split violin plot").
        if name and not title.lower().endswith(name.lower()):
            r.err(md, f"title {title!r} must end with the term's name {name!r}")
        # about: the chart and element terms drawn in snippet.png, its own term first.
        about = meta.get("about") or []
        if not about or about[0] != d.name:
            r.err(md, "about must list the terms drawn in snippet.png, starting with its id")
        for term in about:
            if term not in names:
                r.err(md, f"about term {term!r} is not in vocab/chart.yaml or vocab/element.yaml")
        for name in ("snippet.py", "snippet.png"):
            if not (d / name).exists():
                r.err(d, f"missing {name}")
        ids.add(d.name)
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quiet", action="store_true", help="print only errors and the summary")
    parser.add_argument("--scrapbook", type=Path, help="scrapbook folder (default: see tools/paths.py)")
    args = parser.parse_args()
    book = for_command(args.scrapbook)
    if book is None:
        print("no scrapbook found: checking the tool root only (snippets, styles, vocabularies)")
    elif book != TOOL_ROOT:
        print(f"scrapbook: {book}")

    r = Report(book)
    found = index.sources(TOOL_ROOT, book, images=True)
    # Each file that does not read is one error; the rest is checked. Missing parts are reported below.
    for problem in found.unreadable():
        r.err(problem.path, problem.why)
    v = {name: set(terms) for name, terms in found.vocab.items()}
    papers = {paper.key: paper for paper in found.papers if not paper.error}
    for paper in papers.values():
        check_paper(paper, r, v["domain"])
    check_tokens(r)
    check_snippets(found, r)
    levels: dict[str, str] = {}
    if book:
        by_paper: dict[str, dict] = {}
        for scrap in found.scraps:
            if scrap.palette is not None:
                by_paper.setdefault(scrap.paper, {})[scrap.folder / "palette.yaml"] = scrap.palette
        for paper in sorted(by_paper):
            check_subset_evidence(by_paper[paper], r)
        for scrap in found.scraps:
            levels[f"{scrap.paper}/{scrap.slug}"] = "-" if scrap.error else check_scrap(scrap, papers, r, v)

    if not args.quiet:
        width = max((len(k) for k in levels), default=0)
        for k, lvl in levels.items():
            print(f"{k:<{width}}  {lvl}")
    counts: dict[str, int] = {}
    for lvl in levels.values():
        counts[lvl] = counts.get(lvl, 0) + 1
    print("levels:", ", ".join(f"{k}: {n}" for k, n in sorted(counts.items())), f"(total {len(levels)})")
    for e in r.errors:
        print("ERROR", e, file=sys.stderr)
    print(f"{len(r.errors)} error(s)")
    return 1 if r.errors else 0


if __name__ == "__main__":
    sys.exit(main())
