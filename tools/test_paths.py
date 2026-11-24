"""tools/paths.py: each way of naming the scrapbook, in each path form, from a start folder that is not the
tool root.

  python -m unittest tools.test_paths

A path on the command line or in CEDALION_SCRAPBOOK is read from the start folder; a relative path in
.cedalion-scrapbook from the tool root. A pointer that names nothing is an error, not "no pointer".
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402


class Forms(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cedalion-test-paths-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root, self.start, self.home = self.tmp / "tools", self.tmp / "start", self.tmp / "home"
        for d in (self.root, self.start, self.home):
            d.mkdir()
        self.books = {}
        for name in ("book", "내 책 2", "home-book"):
            folder = (self.home if name == "home-book" else self.tmp) / name
            (folder / "scraps").mkdir(parents=True)
            self.books[name] = folder
        (self.tmp / "linked").symlink_to(self.tmp / "book", target_is_directory=True)
        (self.start / "book").mkdir()  # the same relative path from the start folder holds no scrapbook

    def find(self, arg=None, env=None, pointer=None):
        if pointer is not None:
            (self.root / ".cedalion-scrapbook").write_bytes(pointer)
        here = os.getcwd()
        os.chdir(self.start)
        try:
            with mock.patch.object(paths, "TOOL_ROOT", self.root), \
                    mock.patch.object(paths, "POINTER", self.root / ".cedalion-scrapbook"), \
                    mock.patch.dict(os.environ, {"HOME": str(self.home), **({paths.ENV: env} if env else {})}, clear=False):
                if not env:
                    os.environ.pop(paths.ENV, None)
                return paths.scrapbook(arg, required=True)
        finally:
            os.chdir(here)

    def test_a_given_path_is_read_from_the_start_folder(self):
        forms = {
            "absolute": (str(self.tmp / "book"), "book"),
            "relative to the start folder": ("../book", "book"),
            "with a trailing slash": ("../book/", "book"),
            "with spaces and Korean": ("../내 책 2", "내 책 2"),
            "under ~": ("~/home-book", "home-book"),
            "through a symbolic link": ("../linked", "book"),
        }
        for name, (text, book) in forms.items():
            for how in ("--scrapbook", paths.ENV):
                with self.subTest(form=name, given=how):
                    got = self.find(arg=text) if how == "--scrapbook" else self.find(env=text)
                    self.assertEqual(got, self.books[book].resolve())

    def test_a_pointer_is_read_from_the_tool_root(self):
        forms = {
            "relative": (b"../book\n", "book"),
            "with a byte order mark and CRLF": (b"\xef\xbb\xbf../book\r\n", "book"),
            "absolute, then another line": (str(self.tmp / "book").encode() + b"\nignored\n", "book"),
            "under ~": (b"~/home-book\n", "home-book"),
            "spaces around it": (b"  ../book  \n", "book"),
        }
        for name, (data, book) in forms.items():
            with self.subTest(name):
                self.assertEqual(self.find(pointer=data), self.books[book].resolve())

    def test_a_pointer_that_names_nothing_or_does_not_read_is_an_error(self):
        for name, data in {"length 0": b"", "blank lines": b"\r\n  \n", "a byte order mark only": b"\xef\xbb\xbf",
                           "not UTF-8": b"\xff\xfe../book\n", "a folder that is no scrapbook": b"../start\n"}.items():
            with self.subTest(name):
                with self.assertRaises(paths.ScrapbookError):
                    self.find(pointer=data)


if __name__ == "__main__":
    unittest.main()
