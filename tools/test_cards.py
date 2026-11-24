"""tools/cards.py with tools/vault.py and tools/index.py: what a run writes, and what it never loses.

  python -m unittest tools.test_cards

The cases are generated, not listed: every node of a made-up scrapbook with every mutation, every kind of
vault file in every state, every manifest state. One judgement holds for all of them: a run either
stops (exit not 0) leaving the vault, its manifest and the scrapbook byte for byte as they were, or
succeeds keeping every value of the user (the view keys of the user, files of the user) and a second run
writes nothing. Each command also has its own expected result: a source that cannot be read never
succeeds, a file of the user in the way never does, helios gaps never lists from a part.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import archive_import  # noqa: E402
import cards  # noqa: E402
import helios  # noqa: E402
import vault  # noqa: E402

ITEM = "citationKey: p1\ntitle: A Paper\ndate: '2024'\ncreators:\n- {creatorType: author, lastName: Kim}\n"
PALETTE = "palettes:\n- title: Key\n  type: categorical\n  panels: [a]\n  colors:\n  - {label: x, hex: '#ffffff', at: [2, 2]}\n"
WIDTH = "_width: 300\n"  # a view key Tolaria writes
ARCHIVED = "_archived: true\n"
MINE = "---\ntitle: My own note\n---\n\nNot a card.\n"  # a note of the user's, beside the cards


def write(path: Path, text: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text if isinstance(text, bytes) else text.encode())


def scrap(book: Path, slug: str, term: str = "choropleth") -> None:
    folder = book / "scraps/p1" / slug
    folder.mkdir(parents=True)
    Image.new("RGB", (40, 30), "white").save(folder / "figure.png")
    write(folder / "object.yaml", f"label: Fig. {slug[-1]}\nfiles:\n- path: figure.png\n"
                                  f"panels:\n- id: a\n  chart: [{term}, schematic]\n  xywh: [1, 1, 5, 5]\n")


def make_book(book: Path) -> None:
    write(book / "papers/p1/item.yaml", ITEM)
    write(book / "papers/p1/context.yaml", "question: x\n")
    write(book / "vocab/domain.yaml", "urban:\n  name: Urban\n  definition: Cities.\n")
    scrap(book, "fig-1")
    scrap(book, "fig-2")
    scrap(book, "fig-3")  # one with no value of the user's in its card
    write(book / "scraps/p1/fig-1/palette.yaml", PALETTE)
    write(book / "scraps/p1/fig-1/description.md", "## alt-text\n\nA map.\n")
    write(book / "scraps/p1/fig-1/caption.md", "Figure 1. A map.\n")


def put_view(path: Path, line: str) -> None:
    text = path.read_text()
    end = text.find("\n---\n", 3)
    path.write_text(text[:end + 1] + line + text[end + 1:])


def files(*folders: Path) -> dict[str, tuple]:
    """Every file and link under FOLDERS: bytes (or a link's target), mode; a folder that cannot be read as such."""
    out = {}
    for folder in folders:
        for p in sorted(folder.rglob("*")) if folder.exists() else []:
            if p.is_symlink():
                out[str(p)] = ("link", os.readlink(p))
            elif p.is_file():
                try:
                    out[str(p)] = (p.read_bytes(), p.stat().st_mode)
                except OSError:
                    out[str(p)] = ("unreadable", p.stat().st_size, p.stat().st_mtime_ns)
            else:
                out[str(p)] = ("folder", p.stat().st_mode)
    return out


def run_cards(book: Path, vault_dir: Path, *args, cwd=None, owner_file: Path | None = None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CEDALION_")}
    if owner_file is not None:
        env["CEDALION_ARCHIVE_OWNER"] = str(owner_file)
    proc = subprocess.run([sys.executable, str(HERE / "cards.py"), "--vault", str(vault_dir), "--scrapbook", str(book), *args],
                          capture_output=True, text=True, env={**env, "MPLBACKEND": "Agg"}, cwd=cwd)
    return proc.returncode, proc.stdout + proc.stderr


def run_archive_import(book: Path, vault_dir: Path, *args, cwd=None, owner_file: Path | None = None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CEDALION_")}
    if owner_file is not None:
        env["CEDALION_ARCHIVE_OWNER"] = str(owner_file)
    proc = subprocess.run([sys.executable, str(HERE / "archive_import.py"), "--vault", str(vault_dir),
                           "--scrapbook", str(book), *args],
                          capture_output=True, text=True, env=env, cwd=cwd)
    return proc.returncode, proc.stdout + proc.stderr


def run_gaps(book: Path):
    out, err = io.StringIO(), io.StringIO()
    env = {k: v for k, v in os.environ.items() if not k.startswith("CEDALION_")}
    with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = helios.main(["gaps", "--scrapbook", str(book)])
        except SystemExit as stop:
            code = stop.code
    return code, out.getvalue().splitlines()


class Case(unittest.TestCase):
    """A made-up scrapbook, a vault made from it, the user's view keys in two cards, and a note of the user's."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cedalion-test-cards-")).resolve()
        self.addCleanup(self.cleanup)
        self.n = 0
        self.owner_file = self.tmp / "archive-owners.json"

    def set_owner(self, book: Path, vault_dir: Path) -> None:
        code, out = run_archive_import(book, vault_dir, "--set-owner", owner_file=self.owner_file)
        self.assertEqual(code, 0, out)

    def cleanup(self):
        for p in [self.tmp, *self.tmp.rglob("*")]:
            if not p.is_symlink():
                p.chmod(0o755 if p.is_dir() else 0o644)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def made(self) -> tuple[Path, Path]:
        self.n += 1
        base = self.tmp / f"case{self.n}"
        book, vault_dir = base / "book", base / "vault"
        make_book(book)
        code, out = run_cards(book, vault_dir)
        self.assertEqual(code, 0, out)
        put_view(vault_dir / "p1-fig-1.md", WIDTH)
        put_view(vault_dir / "p1-fig-2.md", ARCHIVED)
        write(vault_dir / "mine.md", MINE)
        code, out = run_cards(book, vault_dir)  # Tolaria's keys are now the tool's to carry
        self.assertEqual(code, 0, out)
        return book, vault_dir

    def judge(self, book: Path, vault_dir: Path, before: dict, code: int, out: str) -> None:
        """Stopped with nothing changed, or done keeping every value of the user, and done for good."""
        if code != 0:
            self.assertEqual(files(book, vault_dir), before, out)
            return
        self.assertEqual((vault_dir / "mine.md").read_text(), MINE, out)
        for name, line in (("p1-fig-1.md", WIDTH), ("p1-fig-2.md", ARCHIVED)):
            had = before.get(str(vault_dir / name), (b"",))[0]
            if isinstance(had, bytes) and line.encode() in had:  # a value the user had stays
                self.assertIn(line, (vault_dir / name).read_text(), out)
        again = files(book, vault_dir)
        code2, out2 = run_cards(book, vault_dir)
        self.assertEqual(code2, 0, out2)
        self.assertIn("(0 notes written, 0 removed)", out2)
        self.assertEqual(files(book, vault_dir), again, out2)


def mutations(path: Path) -> dict:
    """Each way the node at PATH can be wrong, as a function that makes it so."""
    def removed():
        shutil.rmtree(path) if path.is_dir() else path.unlink()

    def closed():
        path.chmod(0o000)

    def swapped():
        if path.is_dir():
            shutil.rmtree(path)
            path.write_text("not a folder\n")
        else:
            path.unlink()
            path.mkdir()
            (path / "inside").write_text("x\n")

    found = {"removed": removed, "cannot be read" if path.is_file() else "cannot be listed": closed, "file and folder swapped": swapped}
    if path.is_file():
        found["length 0"] = lambda: path.write_bytes(b"")
    return found


class Sources(Case):
    """Every node of the scrapbook (folders and files) with every mutation."""

    def test_every_node_with_every_mutation(self):
        template = self.tmp / "template"
        make_book(template)
        nodes = [p.relative_to(template) for p in sorted(template.rglob("*"))]
        for rel in nodes:
            for kind in mutations(template / rel):
                with self.subTest(node=str(rel), mutation=kind):
                    book, vault_dir = self.made()
                    mutations(book / rel)[kind]()
                    before = files(book, vault_dir)
                    code, out = run_cards(book, vault_dir)
                    self.judge(book, vault_dir, before, code, out)
                    if kind in ("cannot be read", "cannot be listed"):
                        self.assertNotEqual(code, 0, out)  # what cannot be read is never taken for absent
                        if rel.suffix != ".png":  # gaps reads no image
                            self.assertEqual(run_gaps(book), (1, []))  # and lists nothing from a part


# vault file -> state -> how to put it in that state; the expected outcome when the run makes the file.
EDITS = {
    "absent": (lambda p: p.unlink(), "remade"),
    "as written": (lambda p: None, "kept"),
    "a view key of the user added": (lambda p: put_view(p, "_order_seen: 2\n"), "kept"),
    "body edited": (lambda p: p.write_text(p.read_text() + "My note.\n"), "stop"),
    "a YAML comment added": (lambda p: put_view(p, "# my comment\n"), "stop"),
    "tags added": (lambda p: put_view(p, "tags: [mine]\n"), "stop"),
    "a link rewritten after a rename": (lambda p: p.write_text(p.read_text().replace("[[", "[[renamed ", 1) if "[[" in p.read_text()
                                                               else p.read_text() + "[[renamed]]\n"), "stop"),
    "the closing --- removed": (lambda p: p.write_text(p.read_text().replace("\n---\n", "\n", 1)), "stop"),
    "not UTF-8": (lambda p: p.write_bytes(b"\xff\xfe" + p.read_bytes()), "stop"),
    "a folder in its place": (lambda p: (p.unlink(), p.mkdir()), "stop"),
    "a link in its place": (lambda p: (p.unlink(), p.symlink_to(p.with_name("mine.md"))), "stop"),
    "cannot be read": (lambda p: p.chmod(0o000), "stop"),
}
ASSET_EDITS = {k: EDITS[k] for k in ("absent", "as written", "a folder in its place", "a link in its place", "cannot be read")}
ASSET_EDITS["other bytes"] = (lambda p: p.write_bytes(p.read_bytes() + b"x"), "stop")
KINDS = {  # vault file -> (the edits it can have, a node of the scrapbook whose removal means its card is no longer made)
    "p1-fig-1.md": (EDITS, "scraps/p1/fig-1"),   # a scrap card with the user's _width
    "p1-fig-2.md": (EDITS, "scraps/p1/fig-2"),   # a scrap card with the user's _archived
    "p1-fig-3.md": (EDITS, "scraps/p1/fig-3"),   # a scrap card as the tool wrote it
    "p1.md": (EDITS, None),                      # a paper card (its body links [[p1-fig-1|...]])
    "paper.md": (EDITS, None),                   # a type note, with the tool's own `_` keys
    "chart-choropleth.md": (EDITS, None),        # a term card
    "assets/p1-fig-3.png": (ASSET_EDITS, "scraps/p1/fig-3"),
}


class VaultFiles(Case):
    """Every kind of vault file in every state, with its card made and (where it can be) no longer made."""

    def test_every_kind_in_every_state(self):
        for name, (edits, source) in KINDS.items():
            for state, (edit, outcome) in edits.items():
                for made in (True, False) if source else (True,):
                    with self.subTest(file=name, state=state, made=made):
                        book, vault_dir = self.made()
                        path = vault_dir / name
                        written = path.read_bytes()
                        edit(path)
                        if not made:
                            shutil.rmtree(book / source)
                        before = files(book, vault_dir)
                        code, out = run_cards(book, vault_dir)
                        self.judge(book, vault_dir, before, code, out)
                        user = state == "a view key of the user added" or name in ("p1-fig-1.md", "p1-fig-2.md")
                        if outcome == "stop" or (not made and user and state != "absent"):
                            self.assertEqual(code, 2, out)
                            self.assertIn(name, out)
                        elif not made:
                            self.assertEqual(code, 0, out)
                            self.assertFalse(path.exists() or path.is_symlink(), out)
                        else:
                            self.assertEqual(code, 0, out)
                            now = path.read_bytes()
                            if state == "absent":
                                continue  # made again, as a fresh card
                            self.assertTrue(now == written or (state == "a view key of the user added" and b"_order_seen: 2" in now), out)


class Manifest(Case):
    def test_every_state_of_the_manifest(self):
        states = {
            "removed": (lambda p: p.unlink(), 2),                       # no ownership: every card is someone's
            "length 0": (lambda p: p.write_text(""), 1),
            "does not parse": (lambda p: p.write_text("{\n"), 1),
            "of an unknown version": (lambda p: p.write_text(p.read_text().replace('"version": 4', '"version": 9')), 1),
            "a record that is not hashes": (lambda p: p.write_text(json.dumps({**json.loads(p.read_text()), "files": {"p1.md": "x"}})), 1),
            "a folder": (lambda p: (p.unlink(), p.mkdir()), 1),
        }
        for name, (edit, code_wanted) in states.items():
            with self.subTest(name):
                book, vault_dir = self.made()
                edit(vault_dir / vault.MANIFEST)
                before = files(book, vault_dir)
                code, out = run_cards(book, vault_dir, owner_file=self.owner_file)
                self.assertEqual(code, code_wanted, out)
                self.assertEqual(files(book, vault_dir), before, out)
        for old_ver, extra in ((2, {"archived": ["p1-fig-2.md"]}), (3, {})):
            with self.subTest(f"version {old_ver} manifest is read and upgraded to v{vault.VERSION}"):
                book, vault_dir = self.made()
                data = json.loads((vault_dir / vault.MANIFEST).read_text())
                old_doc = {"version": old_ver, "scrapbook": data["scrapbook"], "files": data["files"], **extra}
                (vault_dir / vault.MANIFEST).write_text(json.dumps(old_doc))
                code, out = run_cards(book, vault_dir, owner_file=self.owner_file)
                self.assertEqual(code, 0, out)
                upgraded = json.loads((vault_dir / vault.MANIFEST).read_text())
                self.assertEqual(upgraded["version"], vault.VERSION)
                self.assertTrue(upgraded["vault_id"])

    def older(self, vault_dir: Path, form: str) -> None:
        names = sorted(json.loads((vault_dir / vault.MANIFEST).read_text())["files"])
        text = "".join(n + "\n" for n in names) if form == "a list of names" else \
            json.dumps({"scrapbook": None, "files": names, "archived": []})
        (vault_dir / vault.MANIFEST).write_text(text)

    def test_an_older_manifest_stops_and_from_migrates_only_user_values_and_personal_files(self):
        for form in ("a list of names", "JSON without hashes"):
            with self.subTest(form):
                book, vault_dir = self.made()
                write(vault_dir / "mine.md", "---\ntitle: My own note\n---\n\nSee [[p1-fig-1]] and [[p1]].\n")
                write(vault_dir / "assets/personal.png", b"my-asset")
                # Even if an old card's body was edited in the old vault, --from carries over only `_` lines.
                (vault_dir / "p1.md").write_text((vault_dir / "p1.md").read_text() + "\nOld body edit.\n")
                self.older(vault_dir, form)
                before_old = files(book, vault_dir)
                code, out = run_cards(book, vault_dir)
                self.assertEqual(code, 2, out)
                self.assertEqual(files(book, vault_dir), before_old, out)
                self.assertIn("p1-fig-1.md (_width)", out)
                self.assertIn("p1-fig-2.md (_archived)", out)
                self.assertIn("mine.md", out)
                self.assertIn("assets/personal.png", out)
                self.assertIn("--from", out)

                new_vault = vault_dir.with_name(vault_dir.name + "-new")
                code, out = run_cards(book, new_vault, "--from", str(vault_dir))
                self.assertEqual(code, 0, out)
                self.assertEqual(files(book, vault_dir), before_old, out)  # old vault untouched
                self.assertIn(WIDTH, (new_vault / "p1-fig-1.md").read_text())
                self.assertIn(ARCHIVED, (new_vault / "p1-fig-2.md").read_text())
                self.assertNotIn("Old body edit.", (new_vault / "p1.md").read_text())
                self.assertEqual((new_vault / "mine.md").read_text(),
                                 "---\ntitle: My own note\n---\n\nSee [[p1-fig-1]] and [[p1]].\n")
                self.assertEqual((new_vault / "assets/personal.png").read_bytes(), b"my-asset")
                code2, out2 = run_cards(book, new_vault)
                self.assertEqual(code2, 0, out2)
                self.assertIn("(0 notes written, 0 removed)", out2)

        with self.subTest("a card with user values no longer made stops migration"):
            book, vault_dir = self.made()
            self.older(vault_dir, "a list of names")
            shutil.rmtree(book / "scraps/p1/fig-1")
            new_vault = vault_dir.with_name("gone-new")
            before_old = files(book, vault_dir)
            code, out = run_cards(book, new_vault, "--from", str(vault_dir))
            self.assertEqual(code, 2, out)
            self.assertIn("p1-fig-1.md", out)
            self.assertFalse(new_vault.exists())
            self.assertEqual(files(book, vault_dir), before_old)

        with self.subTest("non-empty destination stops migration"):
            book, vault_dir = self.made()
            self.older(vault_dir, "a list of names")
            new_vault = vault_dir.with_name("nonempty-new")
            write(new_vault / "existing.txt", "keep\n")
            before = files(book, vault_dir, new_vault)
            code, out = run_cards(book, new_vault, "--from", str(vault_dir))
            self.assertEqual(code, 2, out)
            self.assertEqual(files(book, vault_dir, new_vault), before)

        with self.subTest("I/O error during personal copy cleans staging and allows clean retry"):
            book, vault_dir = self.made()
            self.older(vault_dir, "a list of names")
            new_vault = vault_dir.with_name("retry-new")
            with mock.patch.object(cards.vaults, "copy_personal", side_effect=OSError("disk full")):
                rc = cards.migrate(cards.TOOL_ROOT, book, vault_dir, new_vault, False)
            self.assertEqual(rc, 1)
            self.assertFalse(new_vault.exists())
            self.assertEqual([p for p in new_vault.parent.iterdir() if p.name.startswith(".cedalion-migrate-")], [])
            code, out = run_cards(book, new_vault, "--from", str(vault_dir), owner_file=self.owner_file)
            self.assertEqual(code, 0, out)
            self.assertEqual((new_vault / "mine.md").read_text(), MINE)


class Writing(Case):
    def test_a_run_stopped_half_way_is_finished_by_the_next(self):
        """The manifest holds both hashes while writing: whichever bytes a file has, it is the tool's."""
        book, vault_dir = self.made()
        write(book / "scraps/p1/fig-1/caption.md", "Figure 1. A map, recaptioned.\n")
        found = cards.index.sources(cards.TOOL_ROOT, book, images=True).whole()
        made_cards, assets = cards.build(found)
        manifest = vault.read_manifest(vault_dir)
        made = {**{n: t.encode() for n, t in made_cards.items()}, **{f"assets/{a}": d for a, d in assets.items()}}
        planned = vault.plan(book, manifest, vault.classify(vault_dir, manifest, made), made, cards.initial_marks(found.scraps))
        self.assertIn("p1-fig-1.md", planned.writes)
        (vault_dir / vault.MANIFEST).write_text(
            vault.manifest_text(book, planned.pending, planned.vault_id, planned.pending_agreed))
        (vault_dir / "p1-fig-1.md").write_bytes(planned.writes["p1-fig-1.md"])  # then the run stops
        code, out = run_cards(book, vault_dir, owner_file=self.owner_file)
        self.assertEqual(code, 0, out)
        self.assertIn(WIDTH, (vault_dir / "p1-fig-1.md").read_text())
        self.assertIn("recaptioned", (vault_dir / "p1-fig-1.md").read_text())

    def test_a_file_edited_after_the_plan_stops_the_writing_and_rerun_finishes(self):
        book, vault_dir = self.made()
        write(book / "scraps/p1/fig-1/caption.md", "Figure 1. Changed.\n")
        write(book / "scraps/p1/fig-2/caption.md", "Figure 2. Changed too.\n")
        found = cards.index.sources(cards.TOOL_ROOT, book, images=True).whole()
        made_cards, assets = cards.build(found)
        manifest = vault.read_manifest(vault_dir)
        made = {**{n: t.encode() for n, t in made_cards.items()}, **{f"assets/{a}": d for a, d in assets.items()}}
        planned = vault.plan(book, manifest, vault.classify(vault_dir, manifest, made), made, cards.initial_marks(found.scraps))
        put_view(vault_dir / "p1-fig-2.md", "_height: 9\n")  # Tolaria, between the plan and the write of fig-2
        with self.assertRaises(vault.Partial) as ctx:
            vault.write(vault_dir, planned)
        self.assertEqual(ctx.exception.done, 1)  # p1-fig-1.md was written before p1-fig-2.md stopped it
        self.assertIn("_height: 9", (vault_dir / "p1-fig-2.md").read_text())
        code, out = run_cards(book, vault_dir)
        self.assertEqual(code, 0, out)
        self.assertIn("_height: 9", (vault_dir / "p1-fig-2.md").read_text())
        self.assertIn("Changed too.", (vault_dir / "p1-fig-2.md").read_text())

    def test_a_user_file_named_like_a_temp_file_is_preserved(self):
        book, vault_dir = self.made()
        user_tmp = vault_dir / ".cedalion-cards.tmp"
        write(user_tmp, "user's own file\n")
        write(book / "scraps/p1/fig-1/caption.md", "Figure 1. Updated caption.\n")
        code, out = run_cards(book, vault_dir)
        self.assertEqual(code, 0, out)
        self.assertEqual(user_tmp.read_text(), "user's own file\n")

    def test_relative_vault_and_scrapbook_are_read_from_the_start_folder(self):
        base = self.tmp / "relative"
        make_book(base / "book")
        (base / "start").mkdir()
        code, out = run_cards(Path("../book"), Path("../vault/"), cwd=base / "start")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads((base / "vault" / vault.MANIFEST).read_text())["scrapbook"], str(base / "book"))

    def test_another_scrapbook_is_refused_and_force_updates_scrapbook_and_keeps_user_files(self):
        book, vault_dir = self.made()
        other = self.tmp / "other"
        shutil.copytree(book, other)
        before = files(book, vault_dir)
        self.assertEqual(run_cards(other, vault_dir)[0], 2)
        self.assertEqual(files(book, vault_dir), before)
        # Same content in the new scrapbook with --force updates the manifest's scrapbook path,
        # so the next run without --force against the new scrapbook succeeds.
        code, out = run_cards(other, vault_dir, "--force")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads((vault_dir / vault.MANIFEST).read_text())["scrapbook"], str(other))
        code2, out2 = run_cards(other, vault_dir)
        self.assertEqual(code2, 0, out2)
        scrap(other, "fig-4")
        write(vault_dir / "p1-fig-4.md", "mine\n")
        code, out = run_cards(other, vault_dir, "--force")
        self.assertEqual(code, 2, out)
        self.assertEqual((vault_dir / "p1-fig-4.md").read_text(), "mine\n")

    def test_output_name_collisions_stop_before_writing(self):
        with self.subTest("paper and scrap with the same card name"):
            book = self.tmp / "clash-exact-book"
            vault_dir = self.tmp / "clash-exact-vault"
            make_book(book)
            write(book / "papers/p1-fig-1/item.yaml",
                  "citationKey: p1-fig-1\ntitle: Colliding Paper\ndate: '2024'\n")
            code, out = run_cards(book, vault_dir)
            self.assertEqual(code, 2, out)
            self.assertIn("paper p1-fig-1 (p1-fig-1.md) and scrap p1/fig-1 (p1-fig-1.md)", out)
            self.assertFalse(vault_dir.exists())

        with self.subTest("case and Unicode normalization collisions"):
            for a, b in (("fig-a", "Fig-A"), ("caf\u00e9", "cafe\u0301")):
                origins = [(f"p1-{a}.md", f"scrap p1/{a}"), (f"p1-{b}.md", f"scrap p1/{b}")]
                self.assertEqual(len(vault.collisions(origins)), 1, (a, b))

    def test_initial_archive_mark_and_difference_hint(self):
        book = self.tmp / "init-arch-book"
        vault_dir = self.tmp / "init-arch-vault"
        make_book(book)
        obj = (book / "scraps/p1/fig-2/object.yaml").read_text() + "archived: true\n"
        write(book / "scraps/p1/fig-2/object.yaml", obj)
        code, out = run_cards(book, vault_dir, owner_file=self.owner_file)
        self.assertEqual(code, 0, out)
        self.assertIn(ARCHIVED, (vault_dir / "p1-fig-2.md").read_text())
        self.assertNotIn("archive-import", out)
        # Register owner vault so local differences suggest archive-import.
        self.set_owner(book, vault_dir)
        put_view(vault_dir / "p1-fig-1.md", ARCHIVED)
        code, out = run_cards(book, vault_dir, owner_file=self.owner_file)
        self.assertEqual(code, 0, out)
        self.assertIn("1 scrap card differs from object.yaml in archive mark", out)
        self.assertNotIn("archived:", (book / "scraps/p1/fig-1/object.yaml").read_text())


class ArchiveImport(Case):
    """tools/archive_import.py: owner-bound Tolaria `_archived` -> object.yaml, verified on both sides."""

    @staticmethod
    def extract_token(output: str) -> str:
        import re
        m = re.search(r"--confirm-unarchive\s+([0-9a-f]{12})", output)
        assert m, output
        return m.group(1)

    def test_archive_and_unarchive_round_trip_with_token(self):
        book, vault_dir = self.made()
        self.set_owner(book, vault_dir)
        # Archive fig-1 and fig-3 in Tolaria, then import all three (fig-1, fig-2, fig-3).
        put_view(vault_dir / "p1-fig-1.md", ARCHIVED)
        put_view(vault_dir / "p1-fig-3.md", ARCHIVED)
        self.assertEqual(run_cards(book, vault_dir, owner_file=self.owner_file)[0], 0)
        code, out = run_archive_import(book, vault_dir, owner_file=self.owner_file)
        self.assertEqual(code, 0, out)
        for slug in ("fig-1", "fig-2", "fig-3"):
            self.assertIn("archived: true", (book / f"scraps/p1/{slug}/object.yaml").read_text())

        # Tolaria unarchives fig-1 (keeping _width) and fig-3 (no other `_` key) by deleting _archived.
        (vault_dir / "p1-fig-1.md").write_text((vault_dir / "p1-fig-1.md").read_text().replace(ARCHIVED, ""))
        (vault_dir / "p1-fig-3.md").write_text((vault_dir / "p1-fig-3.md").read_text().replace(ARCHIVED, ""))
        self.assertIn(WIDTH, (vault_dir / "p1-fig-1.md").read_text())
        self.assertEqual(run_cards(book, vault_dir, owner_file=self.owner_file)[0], 0)

        # Unarchive without token must stop (exit 2) and write nothing.
        before_book = files(book)
        code, out = run_archive_import(book, vault_dir, owner_file=self.owner_file)
        self.assertEqual(code, 2, out)
        self.assertEqual(files(book), before_book)
        self.assertIn("unarchived: scraps/p1/fig-1", out)
        self.assertIn("unarchived: scraps/p1/fig-3", out)
        token = self.extract_token(out)

        # Wrong token stops with nothing written.
        code, out = run_archive_import(book, vault_dir, "--confirm-unarchive", "000000000000", owner_file=self.owner_file)
        self.assertEqual(code, 2, out)
        self.assertEqual(files(book), before_book)

        # Editing a card invalidates the previous token.
        put_view(vault_dir / "p1-fig-1.md", "_height: 12\n")
        code, out = run_archive_import(book, vault_dir, "--confirm-unarchive", token, owner_file=self.owner_file)
        self.assertEqual(code, 2, out)
        self.assertEqual(files(book), before_book)
        token2 = self.extract_token(out)
        self.assertNotEqual(token2, token)

        # Applying with the fresh token unarchives fig-1 and fig-3 and leaves fig-2 archived.
        code, out = run_archive_import(book, vault_dir, "--confirm-unarchive", token2, owner_file=self.owner_file)
        self.assertEqual(code, 0, out)
        self.assertNotIn("archived:", (book / "scraps/p1/fig-1/object.yaml").read_text())
        self.assertIn("archived: true", (book / "scraps/p1/fig-2/object.yaml").read_text())
        self.assertNotIn("archived:", (book / "scraps/p1/fig-3/object.yaml").read_text())

        # Rerunning archive-import is a no-op; cards reports 0 differences.
        before_book2 = files(book)
        code2, out2 = run_archive_import(book, vault_dir, owner_file=self.owner_file)
        self.assertEqual((code2, out2), (0, ""))
        self.assertEqual(files(book), before_book2)
        code3, out3 = run_cards(book, vault_dir, owner_file=self.owner_file)
        self.assertEqual(code3, 0, out3)
        self.assertNotIn("archive-import", out3)

    def test_v2_and_old_v3_upgrade_never_unarchives_existing_marks(self):
        for old_ver in (2, 3):
            with self.subTest(old_version=old_ver):
                book = self.tmp / f"upv{old_ver}-book"
                vault_dir = self.tmp / f"upv{old_ver}-vault"
                make_book(book)
                # Build cards BEFORE object.yaml has archived: true (matches old 4020e35 v2 vault where cards lacked _archived).
                self.assertEqual(run_cards(book, vault_dir, owner_file=self.owner_file)[0], 0)
                put_view(vault_dir / "p1-fig-1.md", WIDTH)
                self.assertEqual(run_cards(book, vault_dir, owner_file=self.owner_file)[0], 0)
                data = json.loads((vault_dir / vault.MANIFEST).read_text())
                old_manifest = {"version": old_ver, "scrapbook": data["scrapbook"], "files": data["files"]}
                if old_ver == 2:
                    old_manifest["archived"] = []
                (vault_dir / vault.MANIFEST).write_text(json.dumps(old_manifest))
                # Scrapbook has fig-1 and fig-2 archived: true.
                write(book / "scraps/p1/fig-1/object.yaml",
                      (book / "scraps/p1/fig-1/object.yaml").read_text() + "archived: true\n")
                write(book / "scraps/p1/fig-2/object.yaml",
                      (book / "scraps/p1/fig-2/object.yaml").read_text() + "archived: true\n")

                # Order 1: archive-import BEFORE cards must stop without unarchiving.
                before_book = files(book)
                code, out = run_archive_import(book, vault_dir, owner_file=self.owner_file)
                self.assertEqual(code, 2, out)
                self.assertEqual(files(book), before_book)

                # Order 2: cards upgrades manifest to v4, preserves book archived marks, does NOT tell user to archive-import.
                code, out = run_cards(book, vault_dir, owner_file=self.owner_file)
                self.assertEqual(code, 0, out)
                self.assertIn("archived in the scrapbook without a vault mark", out)
                self.assertNotIn("archive-import", out)
                # Even after registering owner, archive-import must NOT implicitly unarchive fig-1 or fig-2.
                self.set_owner(book, vault_dir)
                code, out = run_archive_import(book, vault_dir, owner_file=self.owner_file)
                self.assertEqual(code, 2, out)
                self.assertIn("unreconciled", out)
                self.assertIn("archived: true", (book / "scraps/p1/fig-1/object.yaml").read_text())
                self.assertIn("archived: true", (book / "scraps/p1/fig-2/object.yaml").read_text())

                # Explicit --sync-from-book copies archived: true into the vault cards while keeping _width.
                code, out = run_cards(book, vault_dir, "--sync-from-book", owner_file=self.owner_file)
                self.assertEqual(code, 0, out)
                self.assertIn(ARCHIVED, (vault_dir / "p1-fig-1.md").read_text())
                self.assertIn(WIDTH, (vault_dir / "p1-fig-1.md").read_text())
                self.assertIn(ARCHIVED, (vault_dir / "p1-fig-2.md").read_text())
                code, out = run_archive_import(book, vault_dir, owner_file=self.owner_file)
                self.assertEqual((code, out), (0, ""))

    def test_owner_binding_copied_vault_and_shared_book_separation(self):
        book = self.tmp / "shared-book"
        vault_a = self.tmp / "vault-a"
        vault_b = self.tmp / "vault-b"
        make_book(book)
        self.assertEqual(run_cards(book, vault_a, owner_file=self.owner_file)[0], 0)
        self.assertEqual(run_cards(book, vault_b, owner_file=self.owner_file)[0], 0)
        self.set_owner(book, vault_a)

        # A copy of owner vault A must NOT inherit write permission.
        vault_a_copy = self.tmp / "vault-a-copy"
        shutil.copytree(vault_a, vault_a_copy)
        put_view(vault_a_copy / "p1-fig-1.md", ARCHIVED)
        code, out = run_archive_import(book, vault_a_copy, owner_file=self.owner_file)
        self.assertEqual(code, 2, out)
        self.assertIn("reader", out)
        self.assertNotIn("archived:", (book / "scraps/p1/fig-1/object.yaml").read_text())

        # Owner A archives fig-1 in book.
        put_view(vault_a / "p1-fig-1.md", ARCHIVED)
        code, out = run_archive_import(book, vault_a, owner_file=self.owner_file)
        self.assertEqual(code, 0, out)
        self.assertIn("archived: true", (book / "scraps/p1/fig-1/object.yaml").read_text())

        # Reader B runs cards: sees fig-1 as newly archived in scrapbook (not local diff), and cannot import.
        code, out = run_cards(book, vault_b, owner_file=self.owner_file)
        self.assertEqual(code, 0, out)
        self.assertIn("changed in the scrapbook since this vault last agreed", out)
        put_view(vault_b / "p1-fig-2.md", ARCHIVED)
        code, out = run_cards(book, vault_b, owner_file=self.owner_file)
        self.assertEqual(code, 0, out)
        self.assertIn("personal archive marks in this vault (reader", out)
        before_book = files(book)
        code, out = run_archive_import(book, vault_b, owner_file=self.owner_file)
        self.assertEqual(code, 2, out)
        self.assertEqual(files(book), before_book)

        # Even on owner vault A, an upstream book archive on fig-3 (book_changed) is deferred, never unarchived.
        write(book / "scraps/p1/fig-3/object.yaml",
              (book / "scraps/p1/fig-3/object.yaml").read_text() + "archived: true\n")
        put_view(vault_a / "p1-fig-2.md", ARCHIVED)
        code, out = run_archive_import(book, vault_a, owner_file=self.owner_file)
        self.assertEqual(code, 0, out)
        self.assertIn("archived: scraps/p1/fig-2", out)
        self.assertIn("deferred 1 scrap(s) that changed in", out)
        self.assertIn("archived: true", (book / "scraps/p1/fig-3/object.yaml").read_text())

    def test_mid_write_tolaria_change_fails_post_write_verification(self):
        book, vault_dir = self.made()
        self.set_owner(book, vault_dir)
        real_replace = vault.replace
        toggled = {"done": False}

        def racing_replace(path: Path, data: bytes) -> None:
            real_replace(path, data)
            if path.name == "object.yaml" and not toggled["done"]:
                toggled["done"] = True
                # Simulate Tolaria unarchiving p1-fig-2.md right after object.yaml was written!
                card = vault_dir / "p1-fig-2.md"
                card.write_text(card.read_text().replace(ARCHIVED, ""))

        with mock.patch.dict(os.environ, {"CEDALION_ARCHIVE_OWNER": str(self.owner_file)}), \
                mock.patch.object(vault, "replace", side_effect=racing_replace):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                rc = archive_import.run(cards.TOOL_ROOT, book, vault_dir)
        self.assertEqual(rc, 1, buf.getvalue())
        self.assertIn("final book/vault state disagrees", buf.getvalue())

    def test_wrong_vault_or_forged_card_stops_before_writing(self):
        book, vault_dir = self.made()
        other_book, other_vault = self.tmp / "other-book", self.tmp / "other-vault"
        make_book(other_book)
        write(other_book / "papers/p1/item.yaml",
              ITEM.replace("title: A Paper", "title: Another Scrapbook's Paper"))
        self.assertEqual(run_cards(other_book, other_vault, owner_file=self.owner_file)[0], 0)
        put_view(other_vault / "p1-fig-1.md", ARCHIVED)
        self.assertEqual(run_cards(other_book, other_vault, owner_file=self.owner_file)[0], 0)

        before_book = files(book)
        # 1. Manifest names another scrapbook.
        code, out = run_archive_import(book, other_vault, owner_file=self.owner_file)
        self.assertEqual(code, 2, out)
        self.assertEqual(files(book), before_book)
        # 2. Even if the manifest's scrapbook path were copied, the card's paper_title does not match book.
        data = json.loads((other_vault / vault.MANIFEST).read_text())
        (other_vault / vault.MANIFEST).write_text(json.dumps({**data, "scrapbook": str(book)}))
        code, out = run_archive_import(book, other_vault, owner_file=self.owner_file)
        self.assertEqual(code, 1, out)
        self.assertIn("is not the card of scraps/p1/fig-1", out)
        self.assertEqual(files(book), before_book)

    def test_missing_or_broken_card_is_never_taken_for_unarchived(self):
        book, vault_dir = self.made()
        self.set_owner(book, vault_dir)
        write(book / "scraps/p1/fig-1/object.yaml",
              (book / "scraps/p1/fig-1/object.yaml").read_text() + "archived: true\n")
        put_view(vault_dir / "p1-fig-1.md", ARCHIVED)
        self.assertEqual(run_cards(book, vault_dir, owner_file=self.owner_file)[0], 0)

        for kind, break_card in (
            ("missing card", lambda p: p.unlink()),
            ("unclosed front matter", lambda p: p.write_text(p.read_text().replace("\n---\n", "\n", 1))),
            ("edited body", lambda p: p.write_text(p.read_text() + "\nEdited.\n")),
            ("non-boolean _archived", lambda p: p.write_text(p.read_text().replace("_archived: true", "_archived: 1"))),
        ):
            with self.subTest(kind):
                saved = (vault_dir / "p1-fig-1.md").read_bytes()
                break_card(vault_dir / "p1-fig-1.md")
                before_book = files(book)
                code, out = run_archive_import(book, vault_dir, owner_file=self.owner_file)
                self.assertEqual(code, 1, out)
                self.assertIn("p1-fig-1.md", out)
                self.assertEqual(files(book), before_book)
                (vault_dir / "p1-fig-1.md").write_bytes(saved)

    def test_older_v1_manifest_cannot_write_without_migration_and_owner(self):
        book, vault_dir = self.made()
        names = sorted(json.loads((vault_dir / vault.MANIFEST).read_text())["files"])
        (vault_dir / vault.MANIFEST).write_text("".join(n + "\n" for n in names))
        before_book = files(book)
        # 1. Book with no registered owner: legacy v1 manifest writes 0 files and exits 2.
        code, out = run_archive_import(book, vault_dir, owner_file=self.owner_file)
        self.assertEqual(code, 2, out)
        self.assertIn("--from", out)
        self.assertIn("--set-owner", out)
        self.assertEqual(files(book), before_book)

        # 2. Book that already has a registered v4 owner: legacy v1 manifest still writes 0 files.
        owner_vault = vault_dir.parent / "owner-vault"
        self.assertEqual(run_cards(book, owner_vault, owner_file=self.owner_file)[0], 0)
        self.set_owner(book, owner_vault)
        before_book = files(book)
        code, out = run_archive_import(book, vault_dir, owner_file=self.owner_file)
        self.assertEqual(code, 2, out)
        self.assertEqual(files(book), before_book)

        # 3. After migrating via --from and registering as owner, import succeeds cleanly.
        migrated = vault_dir.parent / "migrated-vault"
        self.assertEqual(run_cards(book, migrated, "--from", str(vault_dir), owner_file=self.owner_file)[0], 0)
        self.set_owner(book, migrated)
        code, out = run_archive_import(book, migrated, owner_file=self.owner_file)
        self.assertEqual(code, 0, out)
        self.assertIn("archived: scraps/p1/fig-2", out)
        self.assertIn("archived: true", (book / "scraps/p1/fig-2/object.yaml").read_text())


class SharedIds(unittest.TestCase):
    """Two snippets with one id in two categories: each gets a card, and scraps link to both."""

    def test_each_snippet_has_its_card(self):
        tmp = Path(tempfile.mkdtemp(prefix="cedalion-test-cards-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root, book = tmp / "root", tmp / "book"
        write(root / "vocab/chart.yaml", "demo:\n  name: Demo\n  definition: A demo.\n"
                                         "other:\n  name: Other\n  definition: Another.\n"
                                         "schematic:\n  name: Schematic\n  definition: A drawing.\n")
        write(root / "vocab/element.yaml", "legend:\n  name: Legend\n  definition: A key.\n")
        write(root / "vocab/kind.yaml", "fig: figure\n")
        write(root / "vocab/role.yaml", "main: main\n")
        for category, term in (("plot", "demo"), ("map", "demo"), ("plot", "other")):
            folder = root / "snippets" / category / term
            write(folder / "snippet.md", f"---\nid: {term}\ncategory: {category}\nabout: [{term}]\n---\n\n# {category} {term}\n")
            write(folder / "snippet.py", "print()\n")
        write(book / "papers/p1/item.yaml", ITEM)
        scrap(book, "fig-1", term="demo")
        made, _ = cards.build(cards.index.sources(root, book, images=True).whole())
        self.assertTrue({"snippet-plot-demo.md", "snippet-map-demo.md", "snippet-other.md"} <= set(made))
        self.assertNotIn("snippet-demo.md", made)
        for link in ("[[snippet-plot-demo]]", "[[snippet-map-demo]]"):
            self.assertIn(link, made["p1-fig-1.md"])
            self.assertIn(link.replace("]]", "|"), made["chart-demo.md"])
        # A snippet or vocabulary of the tool root that does not read stops, naming it.
        for rel, text in (("snippets/plot/other/snippet.md", "---\nabout: [\n---\n"), ("vocab/chart.yaml", "")):
            with self.subTest(rel):
                kept = (root / rel).read_text()
                (root / rel).write_text(text)
                with self.assertRaises(cards.index.Unreadable) as raised:
                    cards.build(cards.index.sources(root, book, images=True).whole())
                self.assertIn(str(root / rel), " ".join(raised.exception.problems))
                (root / rel).write_text(kept)


if __name__ == "__main__":
    unittest.main()
