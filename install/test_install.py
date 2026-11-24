"""Both installers against the same scenarios, offline: local repositories, a stub pixi, a made-up home.

Each scenario sets up a starting state and writes down, literally, what the run must end with: its exit
code, which of the installer's places may change (the folder, orion beside it, each skill link), the
commit the folder must be at, and what .cedalion-scrapbook names. The rules, for install.sh and
install.ps1 alike:
  R1  A run changes only the places its scenario names (and folders made on the way to them); every
      other byte, link and git record is as it was: other clones, a scrapbook named elsewhere.
  R2  A run that stops exits 1 and changes nothing at all, .git folders and FETCH_HEAD included.
  R3  Running again changes nothing but git's own records in .git of the two clones, and exits 0.
  R4  .cedalion-scrapbook names orion, is kept as it was, or is not there, as the scenario says.
  R5  A skill link the scenario names becomes a link to the folder; the others stay as they were.
      Unregistering removes exactly those links.
  R6  pixi runs only as `pixi --version`, and as `pixi install` and `pixi run check --quiet` in the
      folder; a run that stops never runs the last two.
  R7  The piped form (options in CEDALION_INSTALL_DIR and CEDALION_INSTALL_SCRAPBOOK) ends as the file
      form does.
  R8  Nothing asks for administrator rights: no sudo, elevation, machine scope or symbolic link on Windows.
  R9  The folder ends at the scenario's commit: the release tag's commit (followed through an annotated
      tag, whatever branch has the same name), the commit of CEDALION_INSTALL_REF, or the commit it was
      at when that is ahead. Both installers carry the same release, v + the version in
      zotero-plugin/addon/manifest.json, which the release workflow checks against the tag.

Shells: sh (not on Windows), and powershell and pwsh where found; CEDALION_TEST_SHELLS=sh,pwsh picks.
Run: python install/test_install.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
import unittest.mock
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
SH, PS1 = HERE / "install.sh", HERE / "install.ps1"
MANIFEST = HERE.parent / "zotero-plugin" / "addon" / "manifest.json"


def carried_release(path: Path) -> str:
    pattern = r"^RELEASE=(\S+)$" if path.suffix == ".sh" else r"^\$CedalionRelease = '(\S+)'$"
    found = re.findall(pattern, path.read_text(), flags=re.M)
    assert len(found) == 1, f"{path.name} must set its release exactly once"
    return found[0]


RELEASE = carried_release(SH)
WINDOWS = os.name == "nt"
PS_SHELLS = ("powershell", "pwsh")
ID = ["-c", "user.name=t", "-c", "user.email=t@example.org"]


def shells() -> list[str]:
    if os.environ.get("CEDALION_TEST_SHELLS"):
        return os.environ["CEDALION_TEST_SHELLS"].split(",")
    found = [] if WINDOWS else ["sh"]
    return found + [s for s in PS_SHELLS if shutil.which(s)]


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def commit(path: Path, message: str) -> str:
    git("add", "-A", cwd=path)
    git(*ID, "commit", "-qm", message, cwd=path)
    return git("rev-parse", "HEAD", cwd=path).strip()


def make_repo(path: Path, files: dict[str, str], origin: str | None = None) -> Path:
    for name, text in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text, encoding="utf-8")
    git("init", "-q", "-b", "main", str(path))
    commit(path, "start")
    if origin:
        git("remote", "add", "origin", origin, cwd=path)
    return path


CEDALION = {"SKILL.md": "# Cedalion\n", "snippets/a/b/snippet.py": "print()\n"}
ORION = {"papers/.keep": "", "vocab/domain.yaml": "test:\n  name: Test\n  definition: A test.\n"}


def make_cedalion(path: Path, tag: str = "annotated", skill: bool = True) -> dict[str, str]:
    """Commits start, release (tagged RELEASE: annotated, as a GitHub release may make, or lightweight) and
    after (main). Returns their SHAs, read when they are made."""
    make_repo(path, CEDALION if skill else {"README": "not Cedalion\n"})
    commits = {"start": git("rev-parse", "HEAD", cwd=path).strip()}
    for name in ("release", "after"):
        (path / "NEWS").write_text(name + "\n")
        commits[name] = commit(path, name)
        if name == "release":
            git(*ID, "tag", *(["-a", "-m", RELEASE] if tag == "annotated" else []), RELEASE, cwd=path)
    return commits


def is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


def link_target(path: Path) -> Path:
    text = os.readlink(path)
    return Path(text[4:] if text.startswith("\\\\?\\") else text)


def snapshot(root: Path) -> dict[str, tuple]:
    """Every path under root, relative, with what it is; links are not followed. The root's own path
    reads as <root> in link targets and file contents, so that two boxes compare."""
    out: dict[str, tuple] = {}

    def walk(d: Path) -> None:
        for p in sorted(d.iterdir()):
            rel = p.relative_to(root).as_posix()
            if is_link(p):
                out[rel] = ("link", str(link_target(p)).replace(str(root), "<root>"))
            elif p.is_dir():
                out[rel] = ("dir",)
                walk(p)
            else:
                data = p.read_bytes().replace(str(root).encode(), b"<root>")
                out[rel] = ("file", hashlib.sha1(data).hexdigest())

    walk(root)
    return out


def physical(path: Path) -> Path:
    """Every component that is there followed through its links and named as the file system stores it; the
    rest appended as it is. Written here from os functions, not from the installers."""
    path = Path(os.path.realpath(path))
    out = Path(path.anchor)
    for n, part in enumerate(path.parts[1:], 1):
        if not out.is_dir():
            return out.joinpath(*path.parts[n:])
        try:
            entries = os.listdir(out)
        except OSError:
            if (out / part).exists():
                out = out / part
                continue
            return out.joinpath(*path.parts[n:])
        names = {unicodedata.normalize("NFC", name).casefold(): name for name in entries}
        key = unicodedata.normalize("NFC", part).casefold()
        if key not in names:
            return out.joinpath(*path.parts[n:])
        out = out / (part if part in entries else names[key])
    return out


def changed(a: dict, b: dict) -> set[str]:
    return {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}


@dataclass
class Box:
    """A made-up home with the repositories the installers see."""

    root: Path
    tag: str = "annotated"
    start: str = ""  # the folder the run starts in, under root
    folder: str | None = None  # the folder as given to the installer (None: the target's absolute path)
    target_name: str = "work/cedalion"
    via: str | None = None  # a symbolic link (a junction on Windows) to the target's parent, through which it is given
    log: Path = field(init=False)

    def __post_init__(self) -> None:
        r = self.root
        self.home, self.target = r / "home", r / self.target_name
        self.book = self.target.parent / "orion"
        self.cwd = r / self.start
        self.cwd.mkdir(parents=True, exist_ok=True)
        if self.via:
            self.target.parent.mkdir(parents=True, exist_ok=True)
            if WINDOWS:
                subprocess.run(["cmd", "/c", "mklink", "/J", str(r / self.via), str(self.target.parent)], check=True, capture_output=True)
            else:
                (r / self.via).symlink_to(self.target.parent, target_is_directory=True)
        text = self.folder if self.folder is not None else str(self.target)
        self.folder_text = text
        if text.startswith("~"):
            text = str(self.home) + text[1:]
        # The folder as the installer resolves it: absolute from the start folder, then physical.
        self.given = physical(Path(os.path.normpath(os.path.join(self.cwd, text))))
        self.links = [self.home / ".claude" / "skills" / "cedalion", self.home / ".agents" / "skills" / "cedalion"]
        self.pointer = self.target / ".cedalion-scrapbook"
        self.home.mkdir(parents=True)
        src = r / "src"
        self.commits = make_cedalion(src / "cedalion", self.tag)
        self.repo = str(src / "cedalion")
        self.book_repo = str(make_repo(src / "orion", ORION))
        self.other_repo = str(make_repo(src / "other", CEDALION))
        stub = r / "stub"
        stub.mkdir()
        self.log = r / "stub" / "pixi.log"
        if WINDOWS:
            (stub / "pixi.cmd").write_bytes(b'@echo off\r\n>>"%CEDALION_TEST_LOG%" echo %CD%^|%*\r\nexit /b 0\r\n')
        else:
            (stub / "pixi").write_text('#!/bin/sh\nprintf \'%s|%s\\n\' "$(pwd -P)" "$*" >> "$CEDALION_TEST_LOG"\n')
            (stub / "pixi").chmod(0o755)
        self.env = {
            **{k: v for k, v in os.environ.items() if not k.startswith("CEDALION_")},
            "HOME": str(self.home), "USERPROFILE": str(self.home), "PIXI_HOME": str(r / "no-pixi"),
            "CEDALION_INSTALL_REPO": self.repo, "CEDALION_INSTALL_SCRAPBOOK_REPO": self.book_repo,
            "CEDALION_TEST_LOG": str(self.log), "GIT_TERMINAL_PROMPT": "0",
            "PATH": str(stub) + os.pathsep + os.environ["PATH"],
            # pwsh on macOS and Linux keeps its own files under these; they are not the installer's.
            **{f"XDG_{d}_HOME": str(stub / d.lower()) for d in ("DATA", "CACHE", "CONFIG")},
        }

    def run(self, shell: str, scrapbook: bool = False, unregister: bool = False, piped: bool = False,
            folder: str | None = None, cwd: Path | None = None):
        env = dict(self.env)
        folder = self.folder_text if folder is None else folder
        if shell == "sh":
            if piped:
                env.update(CEDALION_INSTALL_DIR=folder, CEDALION_INSTALL_SCRAPBOOK="1" if scrapbook else "")
                cmd = ["sh", "-c", 'sh < "$0"', str(SH)]
            else:
                cmd = ["sh", str(SH), *(["--unregister"] if unregister else []), *(["--scrapbook"] if scrapbook else []), folder]
        else:
            base = [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"]
            if piped:
                env.update(CEDALION_INSTALL_DIR=folder, CEDALION_INSTALL_SCRAPBOOK="1" if scrapbook else "")
                cmd = base + ["-Command", f"Get-Content -Raw -LiteralPath '{PS1}' | Invoke-Expression"]
            else:
                cmd = base + ["-File", str(PS1), *(["-Unregister"] if unregister else []), *(["-Scrapbook"] if scrapbook else []), folder]
        p = subprocess.run(cmd, cwd=cwd or self.cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return p.returncode, p.stdout + p.stderr

    def snap(self) -> dict[str, tuple]:
        s = snapshot(self.root)
        return {k: v for k, v in s.items() if not k.startswith("stub/")}

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def head(self) -> str:
        if not (self.target / ".git").is_dir():
            return ""
        return subprocess.run(["git", "-C", str(self.target), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def places(self) -> dict[str, Path]:
        return {"folder": self.target, "orion": self.book, "link claude": self.links[0], "link agents": self.links[1]}


# Starting states.

def clone(repo: str, path: Path) -> None:
    git("clone", "-q", repo, str(path))


def with_scrapbook(part: str, tracked: bool = True, empty: bool = False):
    def setup(box: Box) -> None:
        clone(box.repo, box.target)
        (box.target / part / "x").mkdir(parents=True)
        if not empty:
            (box.target / part / "x" / "item.yaml").write_text("x: 1\n")
        if tracked:
            commit(box.target, part)
    return setup


def behind(box: Box) -> None:
    clone(box.repo, box.target)
    git("-C", str(box.target), "checkout", "-q", "--detach", box.commits["start"])


def link_elsewhere(box: Box) -> None:
    elsewhere = box.root / "elsewhere"
    elsewhere.mkdir()
    box.links[1].parent.mkdir(parents=True)
    if WINDOWS:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(box.links[1]), str(elsewhere)], check=True, capture_output=True)
    else:
        box.links[1].symlink_to(elsewhere)


def pointer_to(make: Callable[[Box, Path], None]):
    def setup(box: Box) -> None:
        clone(box.repo, box.target)
        make(box, box.root / "mybook")
        # With a byte order mark and CRLF, which both installers and tools/paths.py read past.
        box.pointer.write_bytes(("﻿" + str(box.root / "mybook") + "\r\n").encode("utf-8"))
    return setup


def another_clone_of_the_scrapbook(box: Box, path: Path) -> None:
    clone(box.book_repo, path)
    (Path(box.book_repo) / "papers" / "new.txt").write_text("upstream moved on\n")
    commit(Path(box.book_repo), "upstream")  # a pull of mybook would bring this


def fetched_before(box: Box) -> None:
    clone(box.repo, box.target)
    git("-C", str(box.target), "fetch", "-q", "origin", "main")  # FETCH_HEAD, which a stop must keep
    box.env.update(CEDALION_INSTALL_REF="v0.0.0-none")


def same_name_branch(box: Box) -> None:
    git("branch", RELEASE, box.commits["after"], cwd=Path(box.repo))


def without_skill(box: Box) -> None:
    shutil.rmtree(box.repo)
    make_cedalion(Path(box.repo), skill=False)


def relative_addresses(box: Box) -> None:
    """Both repositories given relative to the start folder, which is not the target's."""
    up = os.path.relpath(box.root, box.cwd)
    box.env.update(CEDALION_INSTALL_REPO=os.path.join(up, "src", "cedalion"),
                   CEDALION_INSTALL_SCRAPBOOK_REPO=os.path.join(up, "src", "orion"))
    if up == ".":
        box.env.update(CEDALION_INSTALL_REPO="./src/cedalion", CEDALION_INSTALL_SCRAPBOOK_REPO="./src/orion")


def relative_pointer(box: Box) -> None:
    """A pointer whose relative path is read from the tool root, not from the start folder."""
    clone(box.repo, box.target)
    (box.target.parent / "mybook" / "papers").mkdir(parents=True)
    (box.cwd / "mybook").mkdir(exist_ok=True)  # the same relative path from the start folder: not this one
    box.pointer.write_text("../mybook\n")


def pointer_folder(box: Box) -> None:
    clone(box.repo, box.target)
    box.pointer.mkdir()


def empty_pointer(box: Box) -> None:
    clone(box.repo, box.target)
    box.pointer.write_bytes(b"\xef\xbb\xbf  \r\n")


@dataclass
class Scenario:
    setup: Callable[[Box], None]
    scrapbook: bool = True
    rc: int = 0
    places: tuple[str, ...] = ("folder", "orion", "link claude", "link agents")  # what may change
    head: str = "release"  # the commit the folder ends at (commits of make_cedalion), or "kept"
    pointer: str | None = "orion"  # what .cedalion-scrapbook names after: "orion", "kept" (as before), None
    tag: str = "annotated"
    start: str = ""  # path forms: see Box
    folder: str | None = None
    target_name: str = "work/cedalion"
    via: str | None = None

    def box(self, root: Path) -> Box:
        return Box(root, self.tag, self.start, self.folder, self.target_name, self.via)


TOOLS = ("folder", "link claude", "link agents")
STOP = dict(rc=1, places=(), head="kept", pointer="kept")
SCENARIOS = {
    "fresh": Scenario(lambda b: None),
    "fresh, tools only": Scenario(lambda b: None, scrapbook=False, places=TOOLS, pointer=None),
    "empty folder": Scenario(lambda b: b.target.mkdir(parents=True)),
    "clone already, ahead of the release": Scenario(lambda b: clone(b.repo, b.target), head="after"),
    "clone behind the release": Scenario(behind),
    "main asked for": Scenario(lambda b: b.env.update(CEDALION_INSTALL_REF="main"), head="after"),
    "a branch named like the release": Scenario(same_name_branch),
    "a lightweight release tag": Scenario(lambda b: None, tag="lightweight"),
    # Path forms: the folder and the addresses as a user may give them, from a start folder that is not the target's.
    "relative addresses from the box": Scenario(relative_addresses),
    "relative folder and addresses from another start folder": Scenario(relative_addresses, start="elsewhere/deep",
                                                                        folder="../../work/cedalion"),
    "a folder with spaces and Korean": Scenario(lambda b: None, target_name="work/내 폴더 2/cedalion"),
    "a folder with a trailing slash": Scenario(lambda b: None, folder="work/cedalion/"),
    "a folder under ~": Scenario(lambda b: None, folder="~/apps/cedalion", target_name="home/apps/cedalion"),
    "a folder through a symbolic link": Scenario(lambda b: None, via="linked", folder="linked/cedalion"),
    "a pointer with a relative path, from another start folder": Scenario(relative_pointer, start="elsewhere",
                                                                          places=TOOLS, head="after", pointer="kept"),
    "a pointer that names nothing": Scenario(empty_pointer, **STOP),
    "a folder where the pointer goes": Scenario(pointer_folder, **STOP),
    "other files": Scenario(lambda b: (b.target.mkdir(parents=True), (b.target / "notes.txt").write_text("mine\n")), **STOP),
    "file in its place": Scenario(lambda b: (b.target.parent.mkdir(parents=True), b.target.write_text("mine\n")), **STOP),
    "other origin": Scenario(lambda b: clone(b.other_repo, b.target), **STOP),
    "not Cedalion": Scenario(lambda b: make_repo(b.target, {"README": "x\n"}, origin=b.repo), **STOP),
    "earlier clone with scraps": Scenario(with_scrapbook("scraps"), **STOP),
    "earlier clone with papers": Scenario(with_scrapbook("papers"), **STOP),
    "clone with untracked papers": Scenario(with_scrapbook("papers", tracked=False), **STOP),
    "clone with an empty scraps folder": Scenario(with_scrapbook("scraps", tracked=False, empty=True), **STOP),
    "release that does not exist": Scenario(lambda b: b.env.update(CEDALION_INSTALL_REF="v0.0.0-none"), **STOP),
    "a ref that does not exist, clone already": Scenario(fetched_before, **STOP),
    "a source without SKILL.md": Scenario(without_skill, **STOP),
    "orion other repository": Scenario(lambda b: clone(b.other_repo, b.book), places=TOOLS, pointer=None),
    "orion other files": Scenario(lambda b: (b.book.mkdir(parents=True), (b.book / "mine.txt").write_text("mine\n")),
                                  places=TOOLS, pointer=None),
    "orion clone already": Scenario(lambda b: clone(b.book_repo, b.book)),
    "pointer names a scrapbook": Scenario(pointer_to(lambda b, p: (p / "papers").mkdir(parents=True)),
                                          places=TOOLS, head="after", pointer="kept"),
    "pointer names another clone of the scrapbook": Scenario(pointer_to(another_clone_of_the_scrapbook),
                                                             places=TOOLS, head="after", pointer="kept"),
    "scrapbook out of reach": Scenario(lambda b: b.env.update(CEDALION_INSTALL_SCRAPBOOK_REPO=str(b.root / "missing")),
                                       places=TOOLS, pointer=None),
    "skill path is a folder": Scenario(lambda b: (b.links[0].mkdir(parents=True), (b.links[0] / "SKILL.md").write_text("other\n")),
                                       places=("folder", "orion", "link agents")),
    "skill link elsewhere": Scenario(link_elsewhere, places=("folder", "orion", "link claude")),
}


if WINDOWS:
    SCENARIOS.update({
        # C:book is relative to the current folder of drive C:, which the start folder does not decide.
        "a drive-relative folder": Scenario(lambda b: None, folder=f"{Path.cwd().drive}work\\cedalion", **STOP),
        "a folder through a junction": Scenario(lambda b: None, via="linked", folder="linked\\cedalion"),
    })


@dataclass
class Record:
    scenario: Scenario
    box: Box
    before: dict
    after: dict
    head_before: str
    rc: int
    out: str
    pixi_calls: list
    rerun: tuple = ()
    unregistered: tuple = ()
    piped: tuple = ()


class Installers(unittest.TestCase):
    records: dict[tuple[str, str], Record] = {}

    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("git") is None:
            raise unittest.SkipTest("git is not on PATH")
        cls.tmp = Path(tempfile.mkdtemp(prefix="cedalion-install-")).resolve()
        # No global or system git settings (signing, hooks, default branch) in the test repositories.
        (cls.tmp / "gitconfig").write_text("")
        os.environ.update(GIT_CONFIG_GLOBAL=str(cls.tmp / "gitconfig"), GIT_CONFIG_NOSYSTEM="1")
        for shell in shells():
            for name, scenario in SCENARIOS.items():
                cls.records[shell, name] = cls.record(shell, name, scenario)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def record(cls, shell: str, name: str, scenario: Scenario) -> Record:
        slug = re.sub(r"\W+", "-", f"{shell}-{name}")
        box = scenario.box(cls.tmp / slug)
        scenario.setup(box)
        head_before, before = box.head(), box.snap()
        rc, out = box.run(shell, scrapbook=scenario.scrapbook)
        calls = box.log.read_text().splitlines() if box.log.exists() else []
        rec = Record(scenario, box, before, box.snap(), head_before, rc, out, calls)
        if rc == 0:
            rc2, out2 = box.run(shell, scrapbook=scenario.scrapbook)
            rec.rerun = (rc2, out2, box.snap())
            rc3, out3 = box.run(shell, unregister=True)
            rec.unregistered = (rc3, out3, box.snap())
        # The same start in a second box, run in the piped form.
        twin = scenario.box(cls.tmp / (slug + "-piped"))
        scenario.setup(twin)
        prc, pout = twin.run(shell, scrapbook=scenario.scrapbook, piped=True)
        rec.piped = (prc, pout, twin)
        return rec

    def each(self, rule) -> None:
        """Check one rule on every shell and scenario."""
        for (shell, name), rec in self.records.items():
            with self.subTest(shell=shell, scenario=name):
                rule(rec)

    def test_r1_only_the_named_places_change(self):
        def rule(rec: Record) -> None:
            b = rec.box
            allowed = [b.rel(b.places()[p]) for p in rec.scenario.places]
            for key in changed(rec.before, rec.after):
                inside = any(key == a or key.startswith(a + "/") for a in allowed)
                # A folder made on the way to one of them, as git clone and mkdir -p make it.
                on_the_way = key not in rec.before and any(a.startswith(key + "/") for a in allowed)
                self.assertTrue(inside or on_the_way, f"{key} changed\n{rec.out}")

        self.each(rule)

    def test_r2_a_stop_changes_nothing(self):
        def rule(rec: Record) -> None:
            self.assertEqual(rec.rc, rec.scenario.rc, rec.out)
            if rec.rc:
                self.assertIn("Cedalion install stopped", rec.out)
                self.assertEqual(changed(rec.before, rec.after), set(), rec.out)

        self.each(rule)

    def test_r3_rerun_changes_nothing(self):
        def rule(rec: Record) -> None:
            if rec.rerun:
                rc, out, snap = rec.rerun
                self.assertEqual(rc, 0, out)
                b = rec.box
                own = [b.rel(b.target) + "/.git/", b.rel(b.book) + "/.git/"]
                self.assertEqual({k for k in changed(rec.after, snap) if not any(k.startswith(o) for o in own)}, set(), out)

        self.each(rule)

    def test_r4_pointer(self):
        def rule(rec: Record) -> None:
            b, want = rec.box, rec.scenario.pointer
            key = b.rel(b.pointer)
            if want == "kept":
                self.assertEqual(rec.after.get(key), rec.before.get(key), rec.out)
            elif want == "orion":
                self.assertEqual(b.pointer.read_text(encoding="utf-8"), f"{b.given.parent / 'orion'}\n", rec.out)
            else:
                self.assertNotIn(key, rec.after, rec.out)

        self.each(rule)

    def test_r5_links(self):
        def rule(rec: Record) -> None:
            b = rec.box
            named = [link for name, link in zip(("link claude", "link agents"), b.links) if name in rec.scenario.places]
            for link in b.links:
                if link in named:
                    self.assertEqual(rec.after.get(b.rel(link)), ("link", str(b.given).replace(str(b.root), "<root>")), rec.out)
                else:
                    self.assertEqual(rec.after.get(b.rel(link)), rec.before.get(b.rel(link)), rec.out)
            if rec.unregistered:
                rc, out, snap = rec.unregistered
                self.assertEqual(rc, 0, out)
                self.assertEqual(changed(rec.rerun[2], snap), {b.rel(link) for link in named}, out)

        self.each(rule)

    def test_r6_pixi_calls(self):
        def rule(rec: Record) -> None:
            target = str(rec.box.target)
            calls = [c.partition("|")[2].strip() for c in rec.pixi_calls]
            for line in rec.pixi_calls:
                cwd, _, args = line.partition("|")
                self.assertIn(args.strip(), ("--version", "install --locked", "run check --quiet"), line)
                if args.strip() != "--version":
                    self.assertEqual(os.path.normcase(cwd.strip()), os.path.normcase(target), line)
            if rec.rc == 0:
                self.assertEqual(calls[-2:], ["install --locked", "run check --quiet"])
            else:
                self.assertNotIn("install --locked", calls, rec.out)

        self.each(rule)

    def test_r7_piped_form(self):
        def rule(rec: Record) -> None:
            rc, out, twin = rec.piped
            self.assertEqual(rc, rec.rc, out)
            # The source repositories and every .git folder differ between boxes by commit times.
            same = lambda s: {k: v for k, v in s.items() if not k.startswith("src/") and "/.git/" not in k}
            self.assertEqual(same(rec.after), same(twin.snap()), out)

        self.each(rule)

    def test_r9_commit(self):
        def rule(rec: Record) -> None:
            want = rec.head_before if rec.scenario.head == "kept" else rec.box.commits[rec.scenario.head]
            self.assertEqual(rec.box.head(), want, rec.out)

        self.each(rule)


def case_insensitive(folder: Path) -> bool:
    probe = folder / "Case-Probe"
    probe.mkdir(exist_ok=True)
    found = (folder / "case-probe").exists()
    probe.rmdir()
    return found


def unicode_insensitive(folder: Path) -> bool:
    nfc = folder / unicodedata.normalize("NFC", "Caf\u00e9-Probe")
    nfd = folder / unicodedata.normalize("NFD", "Caf\u00e9-Probe")
    nfc.mkdir(exist_ok=True)
    found = nfd.exists()
    nfc.rmdir()
    return found


class PathPairs(unittest.TestCase):
    """Two commands that take the folder (install, then unregister or install again), each given the folder
    in every path form: they name the same clone, so unregister leaves no link of it and a second install
    changes nothing but git's records."""

    def forms(self, box: Box) -> dict[str, tuple[str, Path]]:
        """form -> (the folder as given, the start folder)."""
        box.target.parent.mkdir(parents=True, exist_ok=True)  # the parent a link can lead to
        (box.root / "alias").symlink_to(box.target.parent, target_is_directory=True) if not WINDOWS else \
            subprocess.run(["cmd", "/c", "mklink", "/J", str(box.root / "alias"), str(box.target.parent)], check=True, capture_output=True)
        (box.root / "elsewhere" / "deep").mkdir(parents=True)
        parent_name = box.target.parent.name
        found = {"the physical path": (str(box.target), box.root),
                 "through a link to its parent": (str(box.root / "alias" / box.target.name), box.root),
                 "relative, from another start folder": (os.path.join("..", "..", parent_name, box.target.name), box.root / "elsewhere" / "deep")}
        if case_insensitive(box.root):
            found["in another case"] = (str(box.target.parent / box.target.name.upper()), box.root)
        if unicode_insensitive(box.root):
            nfd_parent = unicodedata.normalize("NFD", parent_name)
            if nfd_parent != parent_name:
                found["in NFD Unicode normalization"] = (str(box.target.parent.parent / nfd_parent / box.target.name), box.root)
        return found

    def test_install_then_unregister_or_install_again_in_every_pair_of_forms(self):
        tmp = Path(tempfile.mkdtemp(prefix="cedalion-install-pairs-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "gitconfig").write_text("")
        env = {"GIT_CONFIG_GLOBAL": str(tmp / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
        n = 0
        target_name = unicodedata.normalize("NFC", "Caf\u00e9/cedalion") if unicode_insensitive(tmp) else "work/cedalion"
        with unittest.mock.patch.dict(os.environ, env):
            for shell in shells():
                forms = self.forms(Box(tmp / f"forms-{shell}", target_name=target_name))
                for first in forms:
                    for second in forms:
                        for command in ("unregister", "install again"):
                            with self.subTest(shell=shell, first=first, second=second, command=command):
                                n += 1
                                box = Box(tmp / f"pair{n}", target_name=target_name)
                                given = self.forms(box)
                                rc, out = box.run(shell, folder=given[first][0], cwd=given[first][1])
                                self.assertEqual(rc, 0, out)
                                for link in box.links:
                                    self.assertEqual(link_target(link), physical(box.target), out)
                                before = box.snap()
                                rc, out = box.run(shell, unregister=command == "unregister",
                                                  folder=given[second][0], cwd=given[second][1])
                                self.assertEqual(rc, 0, out)
                                after = box.snap()
                                if command == "unregister":
                                    self.assertFalse(any(is_link(link) or link.exists() for link in box.links), out)
                                    self.assertEqual(changed(before, after), {box.rel(link) for link in box.links}, out)
                                else:
                                    own = box.rel(box.target) + "/.git/"
                                    self.assertEqual({k for k in changed(before, after) if not k.startswith(own)}, set(), out)


class UpgradeAndSafety(unittest.TestCase):
    """Upgrade from an earlier release, recovery after a failed pixi install, preservation of colliding user
    files, and a script cut short at any point."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cedalion-install-upgrade-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "gitconfig").write_text("")

    def test_a_script_cut_at_any_point_changes_nothing(self):
        env = {"GIT_CONFIG_GLOBAL": str(self.tmp / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
        with unittest.mock.patch.dict(os.environ, env):
            for shell in shells():
                script = (SH if shell == "sh" else PS1).read_text(encoding="utf-8")
                lines = script.splitlines(keepends=True)
                box = Box(self.tmp / f"cut-{shell}")
                before = box.snap()
                # Every prefix up to (and excluding) the final line that invokes the installer.
                cuts = sorted({1, 2, 5, 10, len(lines) // 4, len(lines) // 2, (3 * len(lines)) // 4,
                               len(lines) - 3, len(lines) - 2, len(lines) - 1})
                for cut in cuts:
                    if not (0 < cut < len(lines)):
                        continue
                    with self.subTest(shell=shell, lines=cut):
                        prefix = "".join(lines[:cut])
                        run_env = {**box.env, "CEDALION_INSTALL_DIR": str(box.target), "CEDALION_INSTALL_SCRAPBOOK": "1"}
                        if shell == "sh":
                            cmd = ["sh", "-c", prefix]
                        else:
                            part = self.tmp / f"part-{shell}-{cut}.ps1"
                            part.write_text(prefix, encoding="utf-8")
                            cmd = [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                   "-Command", f"Get-Content -Raw -LiteralPath '{part}' | Invoke-Expression"]
                        subprocess.run(cmd, cwd=box.cwd, env=run_env, capture_output=True, text=True)
                        self.assertEqual(box.snap(), before)

    def test_upgrade_from_previous_release_and_recovery(self):
        env = {"GIT_CONFIG_GLOBAL": str(self.tmp / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
        with unittest.mock.patch.dict(os.environ, env):
            for shell in shells():
                with self.subTest(shell=shell):
                    box = Box(self.tmp / f"up-{shell}")
                    # Tag start as v0.0.9 (N-1); release is RELEASE (N), which adds NEWS.
                    git(*ID, "tag", "-a", "-m", "v0.0.9", "v0.0.9", box.commits["start"], cwd=Path(box.repo))
                    box.env["CEDALION_INSTALL_REF"] = "v0.0.9"
                    rc, out = box.run(shell, scrapbook=True)
                    self.assertEqual(rc, 0, out)
                    self.assertEqual(box.head(), box.commits["start"])

                    # Set up a scrapbook (with an archived scrap) and a genuine v2 vault (where the card has no
                    # `_archived` key yet) plus user `_width`, a personal note, and an untracked file in the clone.
                    book_src = Path(box.book_repo)
                    (book_src / "papers/p1").mkdir(parents=True, exist_ok=True)
                    (book_src / "papers/p1/item.yaml").write_text(
                        "citationKey: p1\nitemType: journalArticle\ntitle: A Paper\ndate: '2024'\nDOI: 10.1234/p1\n"
                        "creators:\n- {creatorType: author, lastName: Kim}\n")
                    (book_src / "scraps/p1/fig-1").mkdir(parents=True, exist_ok=True)
                    from PIL import Image
                    Image.new("RGB", (40, 30), "white").save(book_src / "scraps/p1/fig-1/figure.png")
                    (book_src / "scraps/p1/fig-1/object.yaml").write_text(
                        "kind: fig\nlabel: Fig. 1\nlabel_source: jats\npaper: p1\nurl: https://example.org\n"
                        "contentUrl: https://example.org/fig1.png\naccessDate: '2026-01-01'\nrights: CC-BY-4.0\n"
                        "archived: true\nfiles:\n- {path: figure.png, sha256: "
                        + hashlib.sha256((book_src / "scraps/p1/fig-1/figure.png").read_bytes()).hexdigest()
                        + ", width: 40, height: 30}\ncaption_source: null\n")
                    commit(book_src, "add p1")
                    git("-C", str(box.book), "pull", "-q", "--ff-only")

                    vault_dir = box.root / "vault"
                    owner_file = box.root / "owners.json"
                    tool_env = {**os.environ, "MPLBACKEND": "Agg", "CEDALION_ARCHIVE_OWNER": str(owner_file)}
                    proc = subprocess.run([sys.executable, str(HERE.parent / "tools/cards.py"),
                                           "--vault", str(vault_dir), "--scrapbook", str(box.book)],
                                          capture_output=True, text=True, env=tool_env)
                    self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                    # Downgrade the vault to a genuine v2 vault: strip `_archived: true` from the card and write
                    # a v2 manifest matching the stripped card bytes (as pre-one-way Cedalion v2 produced).
                    note_path = vault_dir / "p1-fig-1.md"
                    base_without_archived = re.sub(r"^_archived: true\n", "", note_path.read_text(), flags=re.M)
                    end = base_without_archived.find("\n---\n", 3)
                    note_path.write_text(base_without_archived[:end + 1] + "_width: 300\n" + base_without_archived[end + 1:])
                    v2_manifest = json.loads((vault_dir / ".cedalion-cards").read_text())
                    v2_manifest["version"] = 2
                    v2_manifest.pop("vault_id", None)
                    v2_manifest.pop("agreed", None)
                    h_v2 = hashlib.sha256(base_without_archived.encode()).hexdigest()
                    v2_manifest["files"]["p1-fig-1.md"] = [[h_v2, h_v2]]
                    (vault_dir / ".cedalion-cards").write_text(json.dumps(v2_manifest))
                    (vault_dir / "personal.md").write_text("My personal note.\n")
                    (box.target / "untracked.txt").write_text("user file in clone\n")

                    # 1. A user file at a path the new release adds (NEWS) is kept and stops the update before any change.
                    box.env.pop("CEDALION_INSTALL_REF", None)  # now targets RELEASE (N)
                    (box.target / "NEWS").write_text("my own NEWS file\n")
                    before_clash = box.snap()
                    rc, out = box.run(shell, scrapbook=True)
                    self.assertEqual(rc, 1, out)
                    self.assertEqual((box.target / "NEWS").read_text(), "my own NEWS file\n")
                    self.assertEqual(box.head(), box.commits["start"])
                    self.assertEqual(box.snap(), before_clash, out)
                    (box.target / "NEWS").unlink()

                    # 1b. A git-ignored user file (notes.md in .git/info/exclude) in sibling orion colliding with an
                    # incoming upstream orion file stops the update before ANY change and preserves notes.md.
                    exclude_file = box.book / ".git/info/exclude"
                    exclude_file.write_text(exclude_file.read_text() + "\nnotes.md\n")
                    local_notes = box.book / "scraps/p1/fig-1/notes.md"
                    local_notes.write_text("my private notes\n")
                    upstream_notes = Path(box.book_repo) / "scraps/p1/fig-1/notes.md"
                    upstream_notes.parent.mkdir(parents=True, exist_ok=True)
                    upstream_notes.write_text("upstream notes\n")
                    upstream_book_head = commit(Path(box.book_repo), "upstream adds notes.md")
                    before_book_clash = box.snap()
                    rc, out = box.run(shell, scrapbook=True)
                    self.assertEqual(rc, 1, out)
                    self.assertEqual(local_notes.read_text(), "my private notes\n")
                    self.assertEqual(box.snap(), before_book_clash, out)
                    # Clean up the colliding upstream commit so the normal upgrade proceeds.
                    git("-C", str(box.book_repo), "reset", "--hard", "HEAD~1")
                    local_notes.unlink()

                    # 2. Local edit to a tracked file stops the update before any change.
                    (box.target / "SKILL.md").write_text("# Edited locally\n")
                    before_dirty = box.snap()
                    rc, out = box.run(shell, scrapbook=True)
                    self.assertEqual(rc, 1, out)
                    self.assertEqual(box.snap(), before_dirty, out)
                    (box.target / "SKILL.md").write_text("# Cedalion\n")

                    # 3. If pixi install --locked fails after the clone was updated to N, a rerun recovers the environment.
                    pixi_bin = box.root / "stub" / ("pixi.cmd" if WINDOWS else "pixi")
                    good_pixi = pixi_bin.read_bytes()
                    if WINDOWS:
                        pixi_bin.write_bytes(b'@echo off\r\nif "%1"=="install" exit /b 1\r\nexit /b 0\r\n')
                    else:
                        pixi_bin.write_text('#!/bin/sh\nprintf \'%s|%s\\n\' "$(pwd -P)" "$*" >> "$CEDALION_TEST_LOG"\n'
                                            '[ "$1" = install ] && exit 1\nexit 0\n')
                    rc, out = box.run(shell, scrapbook=True)
                    self.assertEqual(rc, 1, out)
                    self.assertEqual(box.head(), box.commits["release"])  # clone updated to N
                    self.assertIn(f"v0.0.9 -> {RELEASE}", out)
                    pixi_bin.write_bytes(good_pixi)
                    box.log.unlink(missing_ok=True)
                    rc, out = box.run(shell, scrapbook=True)
                    self.assertEqual(rc, 0, out)
                    calls = [c.partition("|")[2].strip() for c in box.log.read_text().splitlines()]
                    self.assertEqual(calls[-2:], ["install --locked", "run check --quiet"])

                    # 4. Verify all user state after the upgrade, including preserving archived: true from a v2 vault.
                    self.assertEqual(box.head(), box.commits["release"])
                    self.assertEqual((box.target / "untracked.txt").read_text(), "user file in clone\n")
                    self.assertEqual(box.pointer.read_text().strip(), str(box.book))
                    for link in box.links:
                        self.assertEqual(link_target(link), physical(box.target))
                    check_proc = subprocess.run([sys.executable, str(HERE.parent / "tools/check.py"),
                                                 "--scrapbook", str(box.book), "--quiet"],
                                                capture_output=True, text=True)
                    self.assertEqual(check_proc.returncode, 0, check_proc.stdout + check_proc.stderr)
                    cards_proc = subprocess.run([sys.executable, str(HERE.parent / "tools/cards.py"),
                                                 "--vault", str(vault_dir), "--scrapbook", str(box.book)],
                                                capture_output=True, text=True, env=tool_env)
                    self.assertEqual(cards_proc.returncode, 0, cards_proc.stdout + cards_proc.stderr)
                    self.assertIn("_width: 300\n", (vault_dir / "p1-fig-1.md").read_text())
                    self.assertEqual((vault_dir / "personal.md").read_text(), "My personal note.\n")
                    # Even after designating this vault as owner, archive-import never silently unarchives a v2 scrap.
                    owner_proc = subprocess.run([sys.executable, str(HERE.parent / "tools/archive_import.py"),
                                                 "--vault", str(vault_dir), "--scrapbook", str(box.book), "--set-owner"],
                                                capture_output=True, text=True, env=tool_env)
                    self.assertEqual(owner_proc.returncode, 0, owner_proc.stdout + owner_proc.stderr)
                    imp_proc = subprocess.run([sys.executable, str(HERE.parent / "tools/archive_import.py"),
                                               "--vault", str(vault_dir), "--scrapbook", str(box.book)],
                                              capture_output=True, text=True, env=tool_env)
                    self.assertEqual(imp_proc.returncode, 2, imp_proc.stdout + imp_proc.stderr)
                    self.assertIn("--confirm-unarchive", imp_proc.stderr)
                    self.assertIn("archived: true", (box.book / "scraps/p1/fig-1/object.yaml").read_text())
                    # Syncing from the scrapbook reconciles the vault card while preserving user _width.
                    sync_proc = subprocess.run([sys.executable, str(HERE.parent / "tools/cards.py"),
                                                "--vault", str(vault_dir), "--scrapbook", str(box.book), "--sync-from-book"],
                                               capture_output=True, text=True, env=tool_env)
                    self.assertEqual(sync_proc.returncode, 0, sync_proc.stdout + sync_proc.stderr)
                    self.assertIn("_archived: true\n", (vault_dir / "p1-fig-1.md").read_text())
                    self.assertIn("_width: 300\n", (vault_dir / "p1-fig-1.md").read_text())
                    imp2 = subprocess.run([sys.executable, str(HERE.parent / "tools/archive_import.py"),
                                           "--vault", str(vault_dir), "--scrapbook", str(box.book)],
                                          capture_output=True, text=True, env=tool_env)
                    self.assertEqual(imp2.returncode, 0, imp2.stdout + imp2.stderr)
                    self.assertIn("archived: true", (box.book / "scraps/p1/fig-1/object.yaml").read_text())

    def test_outdated_installer_stops_when_newer_release_exists(self):
        env = {"GIT_CONFIG_GLOBAL": str(self.tmp / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
        with unittest.mock.patch.dict(os.environ, env):
            for shell in shells():
                with self.subTest(shell=shell):
                    box = Box(self.tmp / f"newer-{shell}")
                    git(*ID, "tag", "-a", "-m", "v9.9.9", "v9.9.9", box.commits["after"], cwd=Path(box.repo))
                    before = box.snap()
                    rc, out = box.run(shell, scrapbook=False)
                    self.assertEqual(rc, 1, out)
                    self.assertIn("v9.9.9", out)
                    self.assertIn("releases/latest/download/", out)
                    self.assertEqual(box.snap(), before, out)
                    # Explicitly pinning CEDALION_INSTALL_REF still works.
                    box.env["CEDALION_INSTALL_REF"] = RELEASE
                    rc, out = box.run(shell, scrapbook=False)
                    self.assertEqual(rc, 0, out)
                    self.assertEqual(box.head(), box.commits["release"])


class NoElevation(unittest.TestCase):
    """R8, read from the scripts: what would need administrator rights is absent."""

    def test_r8(self):
        for path, banned in (
            (SH, [r"\bsudo\b", r"\bdoas\b", r"\bsu\b"]),
            (PS1, [r"RunAs", r"Start-Process", r"--scope\s+machine", r"HKLM:", r"'Machine'", r"Set-ExecutionPolicy", r"\bmklink\b"]),
        ):
            code = "\n".join(line for line in path.read_text().splitlines() if not line.lstrip().startswith("#"))
            for pattern in banned:
                with self.subTest(file=path.name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, code))
        # Windows gets junctions; a symbolic link only where PowerShell has no junctions.
        self.assertIn("if ([Environment]::OSVersion.Platform -eq 'Win32NT') { 'Junction' } else { 'SymbolicLink' }", PS1.read_text())
        self.assertTrue(PS1.read_bytes().isascii(), "install.ps1 must stay ASCII for Windows PowerShell 5.1")


class Release(unittest.TestCase):
    """R9, read from the files: both installers carry the release that the plugin version names."""

    def test_r9_carried(self):
        version = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
        self.assertEqual(carried_release(SH), f"v{version}")
        self.assertEqual(carried_release(PS1), f"v{version}")

    def test_the_option_names_are_the_installers_own(self):
        """Install options start with CEDALION_INSTALL_; CEDALION_SCRAPBOOK stays the tools' path (tools/paths.py)."""
        for path in (SH, PS1):
            names = set(re.findall(r"CEDALION_[A-Z_]+", path.read_text()))
            with self.subTest(path.name):
                self.assertTrue(names, path)
                self.assertEqual({n for n in names if not n.startswith("CEDALION_INSTALL_")}, set())


if __name__ == "__main__":
    print("shells:", ", ".join(shells()), file=sys.stderr)
    unittest.main()
