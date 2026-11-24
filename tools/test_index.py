"""tools/index.py: the source set, for each kind of entry in each input state.

  python -m unittest tools.test_index

One table per kind: the state a test puts the entry in, and what the set must say: read (no problem),
absent (not listed, no problem), or a problem naming the path (unreadable, or a missing part).
tools/test_cards.py walks a whole source tree with every mutation; this file names the outcome of each.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import index  # noqa: E402

SNIPPET = "---\nid: demo\ncategory: plot\nabout: [bar, legend]\n---\n\n# Demo plot\n\nText.\n"
OBJECT = "label: Fig. 1\nfiles:\n- path: figure.png\npanels:\n- id: a\n  chart: [bar]\n"
ITEM = "citationKey: demo2024\ntitle: A Paper\nDOI: 10.1234/x\n"
PALETTE = "palettes:\n- title: Key\n  type: categorical\n  colors:\n  - {label: a, hex: '#000000', at: [0, 0]}\n"
VOCAB = "bar:\n  name: Bar chart\n  definition: Bars.\n"
TREE = {
    "root/snippets/plot/demo/snippet.md": SNIPPET, "root/snippets/plot/demo/snippet.py": "print()\n",
    "root/vocab/chart.yaml": VOCAB, "root/vocab/element.yaml": "legend:\n  name: Legend\n  definition: A key.\n",
    "root/vocab/kind.yaml": "fig: figure\n", "root/vocab/role.yaml": "main: main\n",
    "book/vocab/domain.yaml": "urban:\n  name: Urban\n  definition: Cities.\n",
    "book/papers/demo2024/item.yaml": ITEM, "book/papers/demo2024/context.yaml": "question: x\n",
    "book/scraps/demo2024/fig-1/object.yaml": OBJECT, "book/scraps/demo2024/fig-1/figure.png": "png",
    "book/scraps/demo2024/fig-1/palette.yaml": PALETTE, "book/scraps/demo2024/fig-1/caption.md": "Figure 1. A map.\n",
}

# file -> state -> (its new content, None to remove it), and the outcome: read, absent, or the path a problem names.
UNREADABLE = "unreadable"
STATES = {
    "root/snippets/plot/demo/snippet.md": {
        "length 0": (b"", UNREADABLE), "not UTF-8": (b"\xff\xfe", UNREADABLE), "no front matter": (b"# Demo\n", UNREADABLE),
        "a front matter that is not closed": (b"---\nid: demo\ncategory: plot\n# Demo\n", UNREADABLE),
        "front matter without fields": (b"---\n\n---\n", UNREADABLE), "without its id": (b"---\ncategory: plot\n---\n", UNREADABLE),
        "does not parse": (b"---\nabout: [\n---\n", UNREADABLE), "about not a list of terms": (b"---\nid: d\ncategory: p\nabout: [3]\n---\n", UNREADABLE),
        "removed, snippet.py left": (None, UNREADABLE)},
    "book/scraps/demo2024/fig-1/object.yaml": {
        "length 0": (b"", UNREADABLE), "an empty mapping": (b"{}\n", UNREADABLE), "a list": (b"- x\n", UNREADABLE),
        "does not parse": (b"label: [\n", UNREADABLE), "files not a list of paths": (b"files: figure.png\n", UNREADABLE),
        "archived not true or false": (b"label: x\narchived: maybe\n", UNREADABLE), "removed, its image left": (None, UNREADABLE)},
    "book/scraps/demo2024/fig-1/figure.png": {"removed, still listed": (None, "missing")},
    "book/scraps/demo2024/fig-1/palette.yaml": {
        "removed": (None, "read"), "length 0": (b"", UNREADABLE), "does not parse": (b"palettes: [\n", UNREADABLE),
        "a color without hex": (PALETTE.replace("hex: '#000000', ", "").encode(), UNREADABLE)},
    "book/scraps/demo2024/fig-1/caption.md": {"removed": (None, "read"), "length 0": (b"", "read"), "not UTF-8": (b"\xff", UNREADABLE)},
    "book/papers/demo2024/item.yaml": {
        "length 0": (b"", UNREADABLE), "an empty mapping": (b"{}\n", UNREADABLE), "another citationKey": (b"citationKey: x\n", UNREADABLE),
        "a DOI that is not one": (b"citationKey: demo2024\nDOI: doi\n", UNREADABLE), "removed, context.yaml left": (None, UNREADABLE)},
    "book/papers/demo2024/context.yaml": {"removed": (None, "read"), "a list": (b"- x\n", UNREADABLE)},
    "root/vocab/chart.yaml": {"removed": (None, UNREADABLE), "length 0": (b"", UNREADABLE), "a term without a name": (b"bar: {}\n", UNREADABLE)},
    "book/vocab/domain.yaml": {"removed": (None, "read"), "does not parse": (b"x: [\n", UNREADABLE)},
}
# folder -> state -> outcome
FOLDERS = {
    "book/papers/demo2024": {"removed, its scraps left": ("missing", "book/scraps/demo2024/fig-1")},
    "book/scraps/demo2024/fig-1": {"removed": ("absent", None), "only dot files and __pycache__ left": ("absent", None),
                                   "cannot be listed": (UNREADABLE, "book/scraps/demo2024/fig-1")},
    "book/scraps/demo2024": {"cannot be listed": (UNREADABLE, "book/scraps/demo2024")},
    "root/snippets/plot": {"cannot be listed": (UNREADABLE, "root/snippets/plot")},
}


class States(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cedalion-test-index-")).resolve()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for p in [self.tmp, *self.tmp.rglob("*")]:
            if p.is_dir():
                p.chmod(0o755)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def tree(self, name: str) -> Path:
        base = self.tmp / name
        for rel, text in TREE.items():
            (base / rel).parent.mkdir(parents=True, exist_ok=True)
            (base / rel).write_text(text)
        return base

    def read(self, base: Path) -> index.Sources:
        return index.sources(base / "root", base / "book")

    def test_the_whole_tree_reads(self):
        found = self.read(self.tree("whole"))
        self.assertEqual(found.problems, [])
        self.assertEqual(found.whole(), found)
        self.assertEqual(([s.key for s in found.snippets], [p.key for p in found.papers], [s.key for s in found.scraps]),
                         ([("plot", "demo")], ["demo2024"], [("demo2024", "fig-1")]))

    def test_every_file_in_every_state(self):
        n = 0
        for rel, states in STATES.items():
            for state, (data, outcome) in states.items():
                with self.subTest(file=rel, state=state):
                    n += 1
                    base = self.tree(f"f{n}")
                    if data is None:
                        (base / rel).unlink()
                    else:
                        (base / rel).write_bytes(data)
                    found = self.read(base)
                    if outcome == "read":
                        self.assertEqual(found.problems, [])
                    else:
                        self.assertEqual([(p.path, p.kind) for p in found.problems], [(base / rel, outcome)])
                        with self.assertRaises(index.Unreadable) as raised:
                            found.whole()
                        self.assertIn(str(base / rel), raised.exception.problems[0])

    def test_every_folder_in_every_state(self):
        n = 0
        for rel, states in FOLDERS.items():
            for state, (outcome, named) in states.items():
                with self.subTest(folder=rel, state=state):
                    n += 1
                    base = self.tree(f"d{n}")
                    folder = base / rel
                    if state.startswith("removed"):
                        shutil.rmtree(folder)
                    elif state.startswith("only dot"):
                        shutil.rmtree(folder)
                        for hidden in (".DS_Store", "__pycache__/x.pyc", ".claude/notes"):
                            (folder / hidden).parent.mkdir(parents=True, exist_ok=True)
                            (folder / hidden).write_text("x")
                    else:
                        folder.chmod(0o000)
                    found = self.read(base)
                    if outcome == "absent":
                        self.assertEqual(found.problems, [])
                        self.assertNotIn(folder, [s.folder for s in found.scraps])
                    else:
                        self.assertEqual([(p.path, p.kind) for p in found.problems], [(base / named, outcome)])


class Snippets(unittest.TestCase):
    def test_keyed_by_category_and_id(self):
        root = Path(tempfile.mkdtemp(prefix="cedalion-test-index-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for rel, text in {"plot/demo": SNIPPET, "map/demo": SNIPPET.replace("category: plot", "category: map"),
                          "plot/other": SNIPPET.replace("id: demo", "id: other")}.items():
            (root / "snippets" / rel).mkdir(parents=True)
            (root / "snippets" / rel / "snippet.md").write_text(text)
        found = index.sources(root, None).snippets
        self.assertEqual([s.key for s in found], [("map", "demo"), ("plot", "demo"), ("plot", "other")])
        self.assertEqual(index.shared_ids(found), {"demo"})
        self.assertEqual((found[1].about, found[1].title, found[1].error), (["bar", "legend"], "Demo plot", None))


if __name__ == "__main__":
    unittest.main()
