"""helios on a small made-up repository: what it prints and how it exits. No network, no matplotlib."""

import contextlib
import io
import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helios

PNG = "from PIL import Image\nImage.new('RGB', (2, 2)).save('snippet.png')\n"
SCRIPTS = {
    "good": PNG,
    "crash": "raise ValueError('boom')\n",
    "syntax": "def broken(:\n",
    "silent": "print('nothing saved')\n",
    "needs-env": "import os\nopen(os.environ['CEDALION_SNIPPET_PNG'], 'wb')\n",
    "text": "open('snippet.png', 'w').write('text')\n",
    "gif": "from PIL import Image\nImage.new('RGB', (2, 2)).save('snippet.png', format='GIF')\n",
}
ABOUT = {"good": ["bar", "legend"], "gif": ["rug"]}


def repo(tmp: str, scripts=SCRIPTS) -> Path:
    root = Path(tmp)
    for name, code in scripts.items():
        folder = root / "snippets" / (name if "/" in name else f"plot/{name}")
        folder.mkdir(parents=True)
        (folder / "snippet.py").write_text(code)
        meta = {"id": folder.name, "category": folder.parent.name, "about": ABOUT.get(folder.name, [])}
        (folder / "snippet.md").write_text(f"---\n{yaml.safe_dump(meta)}---\n")
    (root / "vocab").mkdir()
    term = lambda t: {"name": t.capitalize(), "definition": f"A {t}."}  # noqa: E731
    (root / "vocab/chart.yaml").write_text(yaml.safe_dump({t: term(t) for t in ("bar", "map", "pie", "tree")}))
    (root / "vocab/element.yaml").write_text(yaml.safe_dump({t: term(t) for t in ("legend", "rug")}))
    (root / "vocab/kind.yaml").write_text("fig: figure\n")
    (root / "vocab/role.yaml").write_text("main: main\n")
    return root


def scrap(book: Path, name: str, panels: dict, **extra) -> None:
    folder = book / "scraps/key" / name
    folder.mkdir(parents=True)
    paper = book / "papers/key/item.yaml"
    if not paper.exists():
        paper.parent.mkdir(parents=True)
        paper.write_text("citationKey: key\n")
    for f in extra.get("files", [{"path": "x.jpg"}]):
        (folder / f["path"]).write_bytes(b"image")
    obj = {"files": [{"path": "x.jpg"}], "panels": [{"id": i, "chart": c} for i, c in panels.items()], **extra}
    (folder / "object.yaml").write_text(yaml.safe_dump(obj))


def run(root: Path, *argv: str, scrapbook: str | None = None) -> tuple[int, list[str]]:
    """helios.main on `root`. The caller's own CEDALION_SCRAPBOOK never reaches the test."""
    out = io.StringIO()
    env = {k: v for k, v in os.environ.items() if k != "CEDALION_SCRAPBOOK"}
    if scrapbook:
        env["CEDALION_SCRAPBOOK"] = scrapbook
    with mock.patch.object(helios, "ROOT", root), mock.patch.object(helios.paths, "TOOL_ROOT", root), \
            mock.patch.object(helios.paths, "POINTER", root / ".cedalion-scrapbook"), \
            mock.patch.dict(os.environ, env, clear=True), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = helios.main(list(argv))
        except SystemExit as stop:
            code = stop.code
    return code, out.getvalue().splitlines()


def kinds(lines: list[str]) -> dict[str, str]:
    """term or snippet folder -> what, from `file | what | where | measured` lines."""
    found = {}
    for text in lines:
        file, what, where, _ = text.split(" | ")
        found[file.split("/")[2] if file.startswith("snippets/") else where] = what
    return found


class Snippets(unittest.TestCase):
    def test_each_failure_is_one_line_and_the_rest_still_runs(self):
        with TemporaryDirectory() as tmp:
            code, lines = run(repo(tmp))
        self.assertEqual(code, 1)
        self.assertEqual(kinds(lines), {
            "crash": "does-not-run", "syntax": "does-not-run", "needs-env": "does-not-run",
            "silent": "png-not-written", "text": "png-not-written", "gif": "png-not-written"})
        self.assertTrue(any("ValueError: boom" in text for text in lines))

    def test_a_syntax_error_keeps_the_other_results_in_json(self):
        with TemporaryDirectory() as tmp:
            code, lines = run(repo(tmp), "syntax", "crash", "--json")
        records = [json.loads(text) for text in lines]
        self.assertEqual(code, 1)
        self.assertEqual({r["file"].split("/")[2]: r["what"] for r in records},
                         {"syntax": "does-not-run", "crash": "does-not-run"})
        self.assertTrue(all(set(r) == {"file", "what", "where", "measured"} for r in records))
        self.assertIn("SyntaxError", next(r["measured"] for r in records if "syntax" in r["file"]))

    def test_a_working_snippet_is_silent_and_named_ids_are_checked(self):
        with TemporaryDirectory() as tmp:
            root = repo(tmp)
            self.assertEqual(run(root, "good"), (0, []))
            self.assertEqual(run(root, "no-such-id")[0], 2)

    def test_the_callers_cedalion_variables_are_not_passed_on(self):
        with TemporaryDirectory() as tmp, mock.patch.dict(os.environ, CEDALION_SNIPPET_PNG=f"{tmp}/elsewhere.png"):
            code, lines = run(repo(tmp), "needs-env")
            self.assertEqual((code, len(lines)), (1, 1))
            self.assertFalse(Path(tmp, "elsewhere.png").exists())

    def test_an_id_in_two_folders_runs_and_reports_both(self):
        with TemporaryDirectory() as tmp:
            code, lines = run(repo(tmp, {"map/twin": "raise ValueError('first')\n", "plot/twin": PNG}), "twin")
        self.assertEqual(code, 1)  # the failing one is not hidden by the working one
        whats = sorted(text.split(" | ")[1] for text in lines)
        self.assertEqual(whats, ["does-not-run", "id-in-two-folders", "id-in-two-folders"])
        self.assertTrue(any(text.startswith("snippets/map/twin/snippet.py | does-not-run") for text in lines))


class Gaps(unittest.TestCase):
    def book(self, tmp):
        root = repo(tmp)
        scrap(root, "fig-1", {"a": ["bar"], "b": ["bar", "map"]})
        scrap(root, "fig-2", {"-": ["pie"]}, archived=True)
        scrap(root, "fig-3", {"-": ["tree"]}, files=[])  # lists no image: not an example
        return root

    def test_default_lists_terms_recorded_on_one_side(self):
        with TemporaryDirectory() as tmp:
            root = self.book(tmp)
            code, lines = run(root, "gaps")
            with_unused = run(root, "gaps", "--unused")[1]
        self.assertEqual(code, 0)
        self.assertEqual(kinds(lines), {"map": "term-without-snippet", "pie": "term-only-in-archived",
                                        "legend": "term-without-example", "rug": "term-without-example"})
        self.assertEqual(kinds(with_unused), {**kinds(lines), "tree": "term-unused"})
        text = {t.split(" | ")[2]: t.split(" | ")[3] for t in lines}
        self.assertEqual(text["map"], "snippets: none. scraps: key/fig-1 (b)")
        self.assertEqual(text["pie"], "snippets: none. scraps: none. archived: key/fig-2 (-)")
        self.assertEqual(text["legend"], "snippets: good. scraps: none")

    def test_a_named_term_is_listed_whatever_its_state(self):
        with TemporaryDirectory() as tmp:
            root = self.book(tmp)
            code, lines = run(root, "gaps", "bar", "tree")
            self.assertEqual((code, kinds(lines)), (0, {"bar": "term-linked", "tree": "term-unused"}))
            self.assertIn("snippets: good. scraps: key/fig-1 (a, b)", lines[0])
            self.assertEqual(run(root, "gaps", "no-such-term")[0], 2)

    def test_a_shared_id_is_named_with_its_category(self):
        with TemporaryDirectory() as tmp:
            root = repo(tmp, {"map/good": PNG, "plot/good": PNG})
            scrap(root, "fig-1", {"-": ["bar"]})
            self.assertIn("snippets: map/good, plot/good.", run(root, "gaps", "bar")[1][0])

    def test_a_file_that_does_not_read_stops_gaps_and_a_removed_folder_does_not(self):
        """What a missing link is cannot be told from a part: each unreadable input stops gaps (exit 1, no
        rows); a scrap whose folder is gone is simply not there."""
        states = {
            "object.yaml that does not parse": ("scraps/key/fig-1/object.yaml", "files: [\n"),
            "object.yaml removed, its image left": ("scraps/key/fig-1/object.yaml", None),
            "object.yaml of length 0": ("scraps/key/fig-1/object.yaml", ""),
            "snippet.md without its id": ("snippets/plot/good/snippet.md", "---\nabout: [bar]\n---\n"),
            "snippet.md that does not parse": ("snippets/plot/good/snippet.md", "---\nabout: [\n---\n"),
            "a vocabulary that does not parse": ("vocab/chart.yaml", "bar: [\n"),
        }
        for name, (rel, text) in states.items():
            with self.subTest(name), TemporaryDirectory() as tmp:
                root = self.book(tmp)
                (root / "scraps/key/fig-1/x.jpg").write_bytes(b"image")
                if text is None:
                    (root / rel).unlink()
                else:
                    (root / rel).write_text(text)
                code, lines = run(root, "gaps")
                self.assertEqual((code, lines), (1, []))
        with TemporaryDirectory() as tmp:
            root = self.book(tmp)
            shutil.rmtree(root / "scraps/key/fig-1")
            code, lines = run(root, "gaps")
            self.assertEqual(code, 0)
            self.assertEqual(kinds(lines)["legend"], "term-without-example")
            self.assertNotIn("map", kinds(lines))

    def test_the_scrapbook_can_live_elsewhere_and_must_hold_scraps(self):
        with TemporaryDirectory() as tmp, TemporaryDirectory() as other:
            root = repo(tmp)
            self.assertEqual(run(root, "gaps")[0], 2)  # no scrapbook anywhere
            (Path(other) / "papers").mkdir()
            self.assertEqual(run(root, "gaps", "bar", "--scrapbook", other)[0], 2)  # papers/ only
            (Path(other) / "scraps").mkdir()
            code, lines = run(root, "gaps", "--scrapbook", other)  # an empty scraps/ is a scrapbook
            self.assertEqual((code, kinds(lines)), (0, dict.fromkeys(("bar", "legend", "rug"), "term-without-example")))
            scrap(Path(other), "fig-9", {"-": ["tree"]})
            self.assertEqual(kinds(run(root, "gaps", "--scrapbook", other)[1])["tree"], "term-without-snippet")
            self.assertEqual(kinds(run(root, "gaps", "tree", scrapbook=other)[1]), {"tree": "term-without-snippet"})
            (root / ".cedalion-scrapbook").write_text(os.path.relpath(other, root))  # read from the tool root
            self.assertEqual(kinds(run(root, "gaps", "tree")[1]), {"tree": "term-without-snippet"})
            self.assertEqual(run(root, "gaps", "--scrapbook", f"{other}/missing")[0], 2)


if __name__ == "__main__":
    unittest.main()
