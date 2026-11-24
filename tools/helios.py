"""Run each snippet the way a reader would, and list terms whose links are missing.

  python tools/helios.py [ID ...] [--json] [--jobs N]
      Copy each snippet.py alone into an empty folder and run `python snippet.py` there, with
      no CEDALION_* variables. Reports a script that fails or writes no PNG named snippet.png
      beside itself, and an ID that two folders share.

  python tools/helios.py gaps [TERM ...] [--unused] [--scrapbook DIR] [--json]
      Chart and element terms recorded on one side only: term-without-snippet (tagged in
      scraps, drawn by no snippet), term-without-example (drawn by snippets, tagged in no
      scrap) and term-only-in-archived, each with the snippets that draw it (about:) and the
      active scraps and panels tagged with it. --unused adds terms with neither. Naming terms
      lists those terms whatever their state. A scrap counts when it lists an image file.
      The scrapbook is found as tools/paths.py describes and must hold scraps/. A scrap, snippet
      or vocabulary that does not read (tools/index.py) stops it: what is missing cannot be told
      from a part.

Each line is `file | what | where | measured`. Lines state what was observed; none is a rule.
Exit 0 when it ran, 1 when a snippet did not run or wrote no image, or gaps found a file that does
not read, 2 for bad arguments.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

import index
import paths

ROOT = paths.TOOL_ROOT
TIMEOUT = 300  # seconds for one snippet
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FAILURES = {"does-not-run", "png-not-written", "not-listed"}
Row = tuple[str, str, str, str]  # file, what, where, measured


def line(row: Row) -> str:
    return " | ".join(" ".join(str(v).split()).replace("|", "/") for v in row)


def runnable(found: index.Sources) -> list[index.Snippet]:
    """Every snippet of the set with a snippet.py. Two folders can share an ID; none is dropped."""
    return [snippet for snippet in found.snippets if snippet.has("snippet.py")]


def run_snippet(folder: Path, root: Path) -> list[Row]:
    """Run a copy of snippet.py alone in an empty folder, as someone who took only that file would."""
    script = f"{folder.relative_to(root).as_posix()}/snippet.py"
    env = {k: v for k, v in os.environ.items() if not k.startswith("CEDALION_")}
    env["MPLBACKEND"] = "Agg"
    with tempfile.TemporaryDirectory(prefix="helios-") as tmp:
        shutil.copy(folder / "snippet.py", tmp)
        try:
            # A syntax error or any other failure is whatever Python says last; odd bytes stay readable.
            done = subprocess.run([sys.executable, "snippet.py"], cwd=tmp, env=env, capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=TIMEOUT)
            said = [text for text in done.stderr.splitlines() if text.strip()]
            failure = (said[-1] if said else f"exit {done.returncode}") if done.returncode else None
        except subprocess.TimeoutExpired:
            failure = f"still running after {TIMEOUT} s"
        if failure:
            return [(script, "does-not-run", "copied alone", failure)]
        png = Path(tmp, "snippet.png")
        if not png.is_file():
            return [(script, "png-not-written", "copied alone", "no snippet.png beside the script")]
        try:
            if png.read_bytes()[:8] != PNG_SIGNATURE:
                raise ValueError("not a PNG")
            with Image.open(png) as image:
                image.load()
        except Exception:  # whatever Pillow raises for a file it cannot decode
            return [(script, "png-not-written", "copied alone", "snippet.png is not a PNG image")]
    return []


def shared_ids(chosen: list[index.Snippet], root: Path) -> list[Row]:
    """One line for each folder whose ID another folder also has."""
    shared, rows = index.shared_ids(chosen), []
    for snippet in chosen:
        if snippet.id in shared:
            others = [o.folder.relative_to(root).as_posix() for o in chosen if o.id == snippet.id and o is not snippet]
            rows.append((f"{snippet.folder.relative_to(root).as_posix()}/snippet.py", "id-in-two-folders", snippet.id,
                         "also " + ", ".join(others)))
    return rows


def tagged(scraps: list[index.Scrap]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """term -> "key/slug (panels)" for active scraps and for archived ones. As on the cards, a
    scrap counts only when it lists an image file."""
    active, archived = {}, {}
    for scrap in scraps:
        obj = scrap.obj
        if not obj.get("files"):
            continue
        panels = {}
        for panel in obj.get("panels") or []:
            for term in (panel.get("chart") or []) + (panel.get("element") or []):
                panels.setdefault(term, []).append(str(panel.get("id")))
        for term, ids in panels.items():
            name = f"{scrap.paper}/{scrap.slug} ({', '.join(ids)})"
            (archived if obj.get("archived") else active).setdefault(term, []).append(name)
    return active, archived


def gap_rows(found: index.Sources, only: list[str], unused: bool) -> list[Row]:
    """The rows of `gaps` from a whole source set (tools/index.py; Sources.whole)."""
    terms = {term: f"vocab/{vocab}.yaml" for vocab in ("chart", "element") for term in found.vocab[vocab]}
    if unknown := [term for term in only if term not in terms]:
        raise ValueError(f"not a chart or element term: {', '.join(unknown)}")
    drawing = runnable(found)
    shared = index.shared_ids(drawing)
    drawn = {}
    for snippet in drawing:
        # An ID two folders share is shown with its category, so both stay visible.
        name = f"{snippet.category}/{snippet.id}" if snippet.id in shared else snippet.id
        for term in snippet.about:
            drawn.setdefault(term, []).append(name)
    active, archived = tagged(found.scraps)
    rows = []
    for term in only or terms:
        by, here, old = drawn.get(term), active.get(term), archived.get(term)
        if here and by:
            what = "term-linked"
        elif here:
            what = "term-without-snippet"
        elif old:
            what = "term-only-in-archived"
        else:
            what = "term-without-example" if by else "term-unused"
        if not only and (what == "term-linked" or (what == "term-unused" and not unused)):
            continue
        parts = ["snippets: " + (", ".join(by) if by else "none"), "scraps: " + ("; ".join(here) if here else "none")]
        if old:
            parts.append("archived: " + "; ".join(old))
        rows.append((terms[term], what, term, ". ".join(parts)))
    return rows


def show(rows: list[Row], as_json: bool) -> None:
    for row in rows:
        print(json.dumps(dict(zip(("file", "what", "where", "measured"), row)), ensure_ascii=False)
              if as_json else line(row))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    gaps = argv[:1] == ["gaps"]
    parser = argparse.ArgumentParser(prog="helios.py gaps" if gaps else "helios.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="one JSON object per line")
    if gaps:
        parser.add_argument("terms", nargs="*", metavar="TERM", help="list these terms whatever their state")
        parser.add_argument("--unused", action="store_true", help="also list terms with no snippet and no scrap")
        parser.add_argument("--scrapbook", type=Path, metavar="DIR", help="folder that holds scraps/")
        args = parser.parse_args(argv[1:])
        # Exits 2 when there is none, or when it has papers/ only: that may be the wrong folder.
        book = paths.for_command(args.scrapbook, required=True, part="scraps")
        try:
            show(gap_rows(index.sources(ROOT, book).whole(), args.terms, args.unused), args.json)
        except ValueError as problem:
            parser.error(str(problem))
        except index.Unreadable as bad:
            for problem in bad.problems:
                print(f"does not read: {problem}", file=sys.stderr)
            print("helios gaps stopped: nothing is listed from a part of the files", file=sys.stderr)
            return 1
        return 0
    parser.add_argument("ids", nargs="*", metavar="ID", help="snippet IDs (default: all)")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1), metavar="N",
                        help="snippets run at the same time")
    args = parser.parse_args(argv)
    sources = index.sources(ROOT, None)
    found = runnable(sources)
    # A snippet folder that cannot be listed is one that cannot be run.
    unlisted = [(paths.shown(p.path, ROOT), "not-listed", "snippets", p.why) for p in sources.problems
                if p.why.startswith("its files cannot be listed")]
    if missing := sorted(set(args.ids) - {snippet.id for snippet in found}):
        parser.error("unknown snippet IDs: " + ", ".join(missing))
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    chosen = [snippet for snippet in found if not args.ids or snippet.id in args.ids]
    with ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(lambda snippet: run_snippet(snippet.folder, ROOT), chosen))
    rows = unlisted + shared_ids(chosen, ROOT) + [row for result in results for row in result]
    show(rows, args.json)
    return int(any(row[1] in FAILURES for row in rows))


if __name__ == "__main__":
    sys.exit(main())
