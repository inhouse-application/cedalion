"""The sources the tools read, read once: the snippets and vocabularies of the tool root, and the papers
and scraps of a scrapbook, with every file of theirs a tool uses. `sources()` makes the one set; cards,
helios gaps and check take it, and read nothing else of the sources.

A snippet is a folder snippets/<category>/<id>/, keyed by (category, id) since two categories can hold the
same id; a paper is papers/<key>/; a scrap is scraps/<paper>/<slug>/. Reading one gives one of three
outcomes:
  read        its file holds what this module requires of it (below, one function per kind)
  absent      the folder is not there, or holds nothing but dot files and __pycache__: it is not listed
  unreadable  the folder holds files, but its own file is missing, does not parse, or lacks what is
              required; or a folder on the way cannot be listed: listed with `error`, and an empty reading
Every problem of the set is a Problem: an unreadable file or folder, or a missing part another refers to
(a scrap's paper, a file object.yaml lists). check reports the unreadable ones and goes on (it reports
missing parts itself); cards and helios gaps take `whole()`, which raises Unreadable on any problem, so
that nothing is written or concluded from a part.
"""

from __future__ import annotations

import os
import re
import stat
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
DOI = re.compile(r"10\.\d{4,9}/\S+")
TEXTS = ("caption.md", "description.md", "notes.md")  # a scrap's texts the tools show
VOCABS = {"chart": True, "element": True, "kind": False, "role": False}  # tool root: name -> named


@dataclass(frozen=True)
class Problem:
    path: Path
    why: str
    kind: str = "unreadable"  # unreadable, or missing: a part another refers to is not there

    def __str__(self) -> str:
        return f"{self.path}: {self.why}"


class Unreadable(Exception):
    """Sources that cannot be read whole; `problems` are "<path>: <why>" lines."""

    def __init__(self, problems: list):
        self.problems = [str(p) for p in problems]
        super().__init__("; ".join(self.problems))


# --- What each kind requires -------------------------------------------------------------------------

def scrap_problem(obj) -> str | None:
    """object.yaml: a mapping with fields, whose files, panels and regions have the shape tools read."""
    if obj is None:
        return "object.yaml is empty"
    if not isinstance(obj, dict):
        return "object.yaml is not a mapping"
    if not obj:
        return "object.yaml is empty"
    files = obj.get("files")
    if files is not None and not (isinstance(files, list) and all(isinstance(f, dict) and isinstance(f.get("path"), str)
                                                                  for f in files)):
        return "object.yaml: files must be a list of mappings with a path"
    panels = obj.get("panels")
    if panels is not None and not (isinstance(panels, list) and all(isinstance(p, dict) for p in panels)):
        return "object.yaml: panels must be a list of mappings"
    for p in panels or []:
        if any(p.get(k) is not None and not isinstance(p[k], list) for k in ("chart", "element")):
            return "object.yaml: a panel's chart and element must be lists"
    regions = obj.get("regions")
    if regions is not None and not (isinstance(regions, list) and all(
            isinstance(r, dict) and isinstance(r.get("term"), str) and isinstance(r.get("xywh"), list) for r in regions)):
        return "object.yaml: regions must be a list of mappings with a term and an xywh"
    if obj.get("archived") is not None and not isinstance(obj["archived"], bool):
        return "object.yaml: archived must be true or false"
    return None


def snippet_problem(meta) -> str | None:
    """snippet.md's front matter: a mapping with its id and category, and about as a list of terms."""
    if not isinstance(meta, dict):
        return "front matter is not a mapping"
    if not (isinstance(meta.get("id"), str) and isinstance(meta.get("category"), str)):
        return "front matter needs an id and a category"
    if meta.get("about") is not None and not (isinstance(meta["about"], list) and all(isinstance(t, str) for t in meta["about"])):
        return "front matter: about must be a list of terms"
    return None


def paper_problem(record, key: str) -> str | None:
    """item.yaml: a mapping with its folder's citationKey, a DOI of the form 10.<digits>/<suffix> or none,
    and a title that is text. The export reads the scrapbook's committed records with this too."""
    if not isinstance(record, dict) or record.get("citationKey") != key:
        return f"has no citationKey {key}"
    doi = record.get("DOI")
    if doi is not None and not (isinstance(doi, str) and (doi == "" or DOI.fullmatch(doi.strip()))):
        return "has a DOI that is not 10.<digits>/<suffix>"
    if record.get("title") is not None and not isinstance(record["title"], str):
        return "has a title that is not text"
    return None


def palette_problem(data) -> str | None:
    """palette.yaml: palettes, each with a title, a type and colors that have a hex (tools/palettes.py)."""
    palettes = data.get("palettes") if isinstance(data, dict) else None
    if not isinstance(palettes, list) or not palettes or not all(isinstance(p, dict) for p in palettes):
        return "palette.yaml: palettes must be a non-empty list of mappings"
    for p in palettes:
        if not (isinstance(p.get("title"), str) and isinstance(p.get("type"), str) and isinstance(p.get("colors"), list)
                and all(isinstance(c, dict) and isinstance(c.get("hex"), str) for c in p["colors"])):
            return "palette.yaml: each palette needs a title, a type and colors with a hex"
    return None


def vocab_problem(data, named: bool = True) -> str | None:
    """A vocabulary: a mapping of terms; for the named ones (chart, element, domain) term -> {name, definition}."""
    if not isinstance(data, dict) or not data:
        return "is not a mapping of terms"
    for term, entry in data.items() if named else ():
        if not (isinstance(entry, dict) and isinstance(entry.get("name"), str) and isinstance(entry.get("definition"), str)):
            return f"term {term!r} needs a name and a definition"
    return None


def context_problem(data) -> str | None:
    """context.yaml of a scrap or a paper: a mapping (check.py reports what it should hold)."""
    return None if isinstance(data, dict) else "context.yaml is not a mapping"


# --- Reading ---------------------------------------------------------------------------------------------

def read_text(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        return None, "does not read as UTF-8"
    except OSError as error:
        return None, f"cannot be read ({error.strerror})"


def read_bytes(path: Path) -> tuple[bytes | None, str | None]:
    try:
        return path.read_bytes(), None
    except OSError as error:
        return None, f"cannot be read ({error.strerror})"


def yaml_text(text: str):
    """(data, error) of YAML text."""
    try:
        return yaml.safe_load(text), None
    except yaml.YAMLError:
        return None, "does not parse"


def read_yaml(path: Path):
    """(data, error) of a YAML file that is there."""
    text, error = read_text(path)
    return (None, error) if error else yaml_text(text)


def listing(folder: Path) -> tuple[list[Path], str | None]:
    """The entries of a folder in name order, or the reason it cannot be listed."""
    try:
        return sorted(Path(e.path) for e in os.scandir(folder)), None
    except OSError as error:
        return [], f"its files cannot be listed ({error.strerror})"


def what(path: Path) -> tuple[str, str | None]:
    """What is at PATH: absent, file, folder or other; and why it cannot be told (a folder on the way that
    cannot be read)."""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return "absent", None
    except OSError as error:
        return "other", f"cannot be reached ({error.strerror})"
    if stat.S_ISLNK(mode):
        try:
            mode = path.stat().st_mode
        except OSError:
            return "other", "is a link that leads nowhere"
    return ("file" if stat.S_ISREG(mode) else "folder" if stat.S_ISDIR(mode) else "other"), None


def hidden(path: Path) -> bool:
    return path.name.startswith(".") or path.name == "__pycache__"


def holds_files(folder: Path) -> tuple[bool, list[Problem]]:
    """Whether the folder holds anything but dot files, dot folders and __pycache__; a folder under it that
    cannot be listed is a Problem (and then it is taken to hold files: what is there cannot be told)."""
    found, todo = False, [folder]
    while todo:
        current = todo.pop()
        listed, error = listing(current)
        if error:
            return True, [Problem(current, error)]
        for entry in listed:
            if hidden(entry):
                continue
            if entry.is_dir() and not entry.is_symlink():
                todo.append(entry)
            else:
                found = True
    return found, []


def folders(parent: Path, depth: int) -> tuple[list[Path], list[Problem]]:
    """The folders DEPTH levels under PARENT, not hidden, in path order, and the folders that cannot be listed."""
    found, problems = [parent], []
    for _ in range(depth):
        below = []
        for f in found:
            if what(f)[0] != "folder":
                continue
            entries, error = listing(f)
            if error:
                problems.append(Problem(f, error))
            below += [c for c in entries if c.is_dir() and not hidden(c)]
        found = below
    return found, problems


def front_matter(text: str) -> tuple[dict | None, str, str | None]:
    """(fields, body, error) of a note: fields is None when there is no front matter."""
    m = FRONT_MATTER.match(text)
    if not m:
        return None, text, ("front matter has no closing ---" if text.startswith("---\n") else None)
    meta, error = yaml_text(m.group(1))
    if error:
        return None, text[m.end():], "front matter does not parse"
    return ({} if meta is None else meta), text[m.end():], None


def h1(body: str) -> str | None:
    return next((line[2:].strip() for line in body.splitlines() if line.startswith("# ")), None)


@dataclass(frozen=True)
class Snippet:
    folder: Path
    meta: dict = field(default_factory=dict)   # front matter of snippet.md; {} when unreadable
    body: str = ""                              # snippet.md after the front matter
    text: str | None = None                     # snippet.md as read, None without one
    error: str | None = None                    # why it is unreadable
    code: str | None = None                     # snippet.py, None without one
    png: bytes | None = None                    # snippet.png, read when the set is made with images

    @property
    def category(self) -> str:
        return self.folder.parent.name

    @property
    def id(self) -> str:
        return self.folder.name

    @property
    def key(self) -> tuple[str, str]:
        return self.category, self.id

    @property
    def path(self) -> Path:
        return self.folder / "snippet.md"

    @property
    def about(self) -> list[str]:
        """The terms its image draws, as snippet.md lists them."""
        return list(self.meta.get("about") or [])

    @property
    def title(self) -> str | None:
        return h1(self.body)

    def has(self, name: str) -> bool:
        return (self.folder / name).is_file()


@dataclass(frozen=True)
class Scrap:
    folder: Path
    obj: dict = field(default_factory=dict)      # object.yaml; {} when unreadable
    error: str | None = None
    palette: dict | None = None                  # palette.yaml; None when there is none or it does not read
    texts: dict = field(default_factory=dict)    # TEXTS that are there -> their text
    context: dict | None = None                  # context.yaml; None when there is none or it does not read
    files: dict = field(default_factory=dict)    # the files object.yaml lists -> bytes, read with images
    source: str = ""                             # object.yaml as read (cards edits its archive mark in it)

    @property
    def paper(self) -> str:
        return self.folder.parent.name

    @property
    def slug(self) -> str:
        return self.folder.name

    @property
    def key(self) -> tuple[str, str]:
        return self.paper, self.slug

    @property
    def path(self) -> Path:
        return self.folder / "object.yaml"


@dataclass(frozen=True)
class Paper:
    folder: Path
    item: dict = field(default_factory=dict)  # item.yaml; {} when unreadable
    error: str | None = None
    context: dict | None = None               # context.yaml; None when there is none or it does not read

    @property
    def key(self) -> str:
        return self.folder.name

    @property
    def path(self) -> Path:
        return self.folder / "item.yaml"


def optional_yaml(path: Path, problem, problems: list[Problem]):
    """A YAML file that may be absent: its data, or None when it is absent or does not read (a Problem)."""
    kind, error = what(path)
    if kind == "absent":
        return None
    if kind != "file":
        problems.append(Problem(path, error or "is not a file"))
        return None
    data, error = read_yaml(path)
    error = error or problem(data)
    if error:
        problems.append(Problem(path, error))
        return None
    return data


def optional_text(path: Path, problems: list[Problem]) -> str | None:
    kind, error = what(path)
    if kind == "absent":
        return None
    text, error = read_text(path) if kind == "file" else (None, error or "is not a file")
    if error:
        problems.append(Problem(path, error))
    return text


def read_snippet(folder: Path, images: bool, problems: list[Problem]) -> Snippet:
    md = folder / "snippet.md"
    code = optional_text(folder / "snippet.py", problems)
    png = None
    if images and what(folder / "snippet.png")[0] != "absent":
        png, error = read_bytes(folder / "snippet.png")
        if error:
            problems.append(Problem(folder / "snippet.png", error))
    if what(md)[0] != "file":
        problems.append(Problem(md, "no snippet.md"))
        return Snippet(folder, error="no snippet.md", code=code, png=png)
    text, error = read_text(md)
    if error:
        problems.append(Problem(md, error))
        return Snippet(folder, error=f"snippet.md {error}", code=code, png=png)
    meta, body, error = front_matter(text)
    if meta is None and error is None:
        error = "missing YAML front matter"
    error = error or snippet_problem(meta)
    if error:
        problems.append(Problem(md, error))
    return Snippet(folder, {} if error else meta, body, text, error, code, png)


def read_scrap(folder: Path, images: bool, problems: list[Problem]) -> Scrap:
    path = folder / "object.yaml"
    if what(path)[0] != "file":
        problems.append(Problem(path, "no object.yaml"))
        return Scrap(folder, error="no object.yaml")
    text, error = read_text(path)
    obj, error = (None, error) if error else yaml_text(text)
    error = f"object.yaml {error}" if error else scrap_problem(obj)
    if error:
        problems.append(Problem(path, error))
        return Scrap(folder, error=error)
    texts = {name: shown for name in TEXTS if (shown := optional_text(folder / name, problems)) is not None}
    files = {}
    for f in obj.get("files") or []:
        where = folder / f["path"]
        if what(where)[0] != "file":
            problems.append(Problem(where, "is listed in object.yaml but not there", "missing"))
        elif images:
            data, error = read_bytes(where)
            if error:
                problems.append(Problem(where, error))
            else:
                files[f["path"]] = data
    return Scrap(folder, obj, None, optional_yaml(folder / "palette.yaml", palette_problem, problems), texts,
                 optional_yaml(folder / "context.yaml", context_problem, problems), files, text)


def read_paper(folder: Path, problems: list[Problem]) -> Paper:
    path = folder / "item.yaml"
    if what(path)[0] != "file":
        problems.append(Problem(path, "no item.yaml"))
        return Paper(folder, error="no item.yaml")
    item, error = read_yaml(path)
    problem = error or paper_problem(item, folder.name)
    if problem:
        problems.append(Problem(path, f"item.yaml {problem}"))
        return Paper(folder, error=f"item.yaml {problem}")
    return Paper(folder, item, None, optional_yaml(folder / "context.yaml", context_problem, problems))


def entries(parent: Path, depth: int, read, kind, problems: list[Problem]) -> list:
    """Every folder DEPTH levels under PARENT that holds files, read with READ; one under which a folder
    cannot be listed is a KIND entry with that error, and is not read."""
    found, listed = folders(parent, depth)
    problems += listed
    out = []
    for folder in found:
        holds, unlisted = holds_files(folder)
        problems += unlisted
        if unlisted:
            out.append(kind(folder, error=unlisted[0].why))
        elif holds:
            out.append(read(folder))
    return out


def read_vocab(path: Path, required: bool, named: bool, problems: list[Problem]) -> dict:
    kind, error = what(path)
    if kind == "absent":
        if required:
            problems.append(Problem(path, "missing"))
        return {}
    if kind != "file":
        problems.append(Problem(path, error or "is not a file"))
        return {}
    data, error = read_yaml(path)
    error = error or vocab_problem(data, named)
    if error:
        problems.append(Problem(path, error))
        return {}
    return data


@dataclass
class Sources:
    """The set: the tool root's snippets and vocabularies, the scrapbook's papers and scraps, and every
    problem met reading them."""
    root: Path
    book: Path | None
    snippets: list[Snippet]
    papers: list[Paper]
    scraps: list[Scrap]
    vocab: dict[str, dict]
    problems: list[Problem]

    def unreadable(self) -> list[Problem]:
        return [p for p in self.problems if p.kind == "unreadable"]

    def whole(self) -> "Sources":
        """The set when nothing is missing or unreadable; else Unreadable, naming each problem."""
        if self.problems:
            raise Unreadable(self.problems)
        return self


def sources(root: Path, book: Path | None, images: bool = False) -> Sources:
    """Read the sources once (IMAGES: also every scrap file and snippet image, as bytes), with the relations
    a tool relies on: each scrap's paper is there."""
    problems: list[Problem] = []
    snippets = entries(root / "snippets", 2, lambda f: read_snippet(f, images, problems), Snippet, problems)
    papers = entries(book / "papers", 1, lambda f: read_paper(f, problems), Paper, problems) if book else []
    scraps = entries(book / "scraps", 2, lambda f: read_scrap(f, images, problems), Scrap, problems) if book else []
    vocab = {name: read_vocab(root / "vocab" / f"{name}.yaml", True, named, problems) for name, named in VOCABS.items()}
    if book:
        vocab["domain"] = read_vocab(book / "vocab/domain.yaml", False, True, problems)
    keys = {p.key for p in papers}
    for scrap in scraps:
        if not scrap.error and scrap.paper not in keys:
            problems.append(Problem(scrap.folder, f"its paper papers/{scrap.paper} is not there", "missing"))
    return Sources(root, book, snippets, papers, scraps, vocab, problems)


def shared_ids(found: list[Snippet]) -> set[str]:
    """The ids that more than one folder has."""
    return {i for i, n in Counter(s.id for s in found).items() if n > 1}
