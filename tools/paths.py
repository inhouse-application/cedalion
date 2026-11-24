"""Find the tool root and the scrapbook.

The tool root holds snippets/, styles/, templates/, vocab/chart.yaml and vocab/element.yaml.
The scrapbook holds papers/, scraps/, vocab/domain.yaml and inbox.yaml; a folder is a scrapbook when it
holds papers/ or scraps/ (is_scrapbook, the one definition every tool uses). It is, in order:
--scrapbook PATH, $CEDALION_SCRAPBOOK, the path written in .cedalion-scrapbook in the tool root
(git-ignored; the installer writes it; its first line, a relative path read from the tool root), or
the tool root itself when it is a scrapbook. A path given on the command line or in the environment is
read from the folder the command starts in, once. A tool that needs one part (cards and helios read
scraps/, the export reads papers/) asks for it with `part`.
A scrapbook that cannot be found raises ScrapbookError; each command chooses its exit, and those that
exit 2 with the message use `for_command`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[1]
POINTER = TOOL_ROOT / ".cedalion-scrapbook"
ENV = "CEDALION_SCRAPBOOK"
PARTS = ("papers", "scraps")


def is_scrapbook(path: Path) -> bool:
    return any((path / part).is_dir() for part in PARTS)


class ScrapbookError(Exception):
    """No scrapbook where one is needed, or a path given for one that is not one."""


def scrapbook(arg: str | Path | None = None, *, required: bool = False, part: str | None = None) -> Path | None:
    """The scrapbook folder, or None when none is set up. A path that is given but is not a scrapbook is
    an error, and so is a missing scrapbook when `required`, or a scrapbook without `part`."""
    if arg:
        path, origin = Path(arg), "--scrapbook"
    elif os.environ.get(ENV):
        path, origin = Path(os.environ[ENV]), ENV
    elif POINTER.is_file():
        # The first line; a relative path in it is read from the tool root; a BOM and CRLF are ignored.
        try:
            lines = POINTER.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeDecodeError):
            raise ScrapbookError(f"{POINTER} does not read as UTF-8")
        pointer = lines[0].strip() if lines else ""
        if not pointer:
            raise ScrapbookError(f"{POINTER} names no folder: write the scrapbook's path in it, or remove it")
        path, origin = TOOL_ROOT / Path(pointer).expanduser(), POINTER.name
    elif is_scrapbook(TOOL_ROOT):
        path, origin = TOOL_ROOT, "the tool root"
    elif required:
        raise ScrapbookError(f"no scrapbook found: pass --scrapbook PATH, set {ENV}, or write its path in {POINTER}")
    else:
        return None
    path = path.expanduser().resolve()
    if not is_scrapbook(path):
        raise ScrapbookError(f"scrapbook {path} (from {origin}) has no papers/ or scraps/ folder")
    if part and not (path / part).is_dir():
        raise ScrapbookError(f"scrapbook {path} (from {origin}) has no {part}/ folder")
    return path


def for_command(*args, **kwargs) -> Path | None:
    """scrapbook() for a command whose answer to a missing scrapbook is the message and exit 2."""
    try:
        return scrapbook(*args, **kwargs)
    except ScrapbookError as error:
        print(error, file=sys.stderr)
        raise SystemExit(2)


def shown(path: Path, *roots: Path | None) -> str:
    """The path relative to the first root holding it, else as given."""
    for root in roots:
        if root and path.is_relative_to(root):
            return path.relative_to(root).as_posix()
    return str(path)
