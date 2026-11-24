"""tools/check.py and the palette sampling it uses: a file that does not parse is one error, not the end.

  python -m unittest tools.test_check
"""

import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import palettes  # noqa: E402


def whole_image_first(image: Image.Image, at, size: int) -> str:
    """The sample as it was computed before: the whole image converted to RGB, then the square cut."""
    x, y = at
    half = size // 2
    box = (max(x - half, 0), max(y - half, 0), min(x + half + 1, image.width), min(y + half + 1, image.height))
    data = image.convert("RGB").crop(box).tobytes()
    return "#" + "".join(f"{round(statistics.median(c)):02x}" for c in (data[0::3], data[1::3], data[2::3]))


class Sample(unittest.TestCase):
    def test_cutting_the_square_first_gives_the_same_hex_in_every_mode(self):
        base = Image.new("RGB", (9, 7))
        base.putdata([((x * 37) % 256, (y * 53) % 256, (x * y * 11) % 256) for y in range(7) for x in range(9)])
        for mode in ("RGB", "RGBA", "P", "L", "LA", "CMYK"):
            image = base.convert(mode)
            for at in ((0, 0), (4, 3), (8, 6)):
                for size in sorted(palettes.SIZES):
                    with self.subTest(mode=mode, at=at, size=size):
                        self.assertEqual(palettes.sample(image, at, size), whole_image_first(image, at, size))


# input -> {state: text (None removes it)}: check reports each, names the file, and checks the rest.
STATES = {
    "scraps/p1/fig-1/object.yaml": {"does not parse": "label: [\n", "length 0": "", "an empty mapping": "{}\n",
                                    "removed, its image left": None},
    "scraps/p1/fig-2/palette.yaml": {"does not parse": "palettes: [\n", "not UTF-8": b"\xff\xfe"},
    "vocab/domain.yaml": {"does not parse": "urban: [\n"},
    "papers/p2/item.yaml": {"does not parse": "title: [\n", "another citationKey": "citationKey: p3\n",
                            "removed, other files left": None},
}


class Unreadable(unittest.TestCase):
    def test_each_unreadable_file_is_reported_and_the_rest_is_checked(self):
        for rel, states in STATES.items():
            for state, text in states.items():
                with self.subTest(input=rel, state=state):
                    book = Path(tempfile.mkdtemp(prefix="cedalion-test-check-")).resolve()
                    self.addCleanup(shutil.rmtree, book, ignore_errors=True)
                    files = {"scraps/p1/fig-1/object.yaml": "label: Fig. 1\n", "scraps/p1/fig-1/figure.png": "png",
                             "scraps/p1/fig-2/object.yaml": "label: Fig. 2\n",
                             "papers/p2/item.yaml": "citationKey: p2\n", "papers/p2/context.yaml": "question: x\n",
                             "vocab/domain.yaml": "urban:\n  name: Urban\n  definition: Cities.\n"}
                    for name, body in files.items():
                        (book / name).parent.mkdir(parents=True, exist_ok=True)
                        (book / name).write_text(body)
                    if text is None:
                        (book / rel).unlink()
                    else:
                        (book / rel).write_bytes(text if isinstance(text, bytes) else text.encode())
                    env = {k: v for k, v in os.environ.items() if not k.startswith("CEDALION_")}
                    proc = subprocess.run([sys.executable, str(HERE / "check.py"), "--scrapbook", str(book)],
                                          capture_output=True, text=True, env=env)
                    self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                    folder = str(Path(rel).parent)
                    self.assertTrue(any(line.startswith(f"ERROR {folder}") and Path(rel).name in line
                                        for line in proc.stderr.splitlines()), proc.stderr)
                    self.assertIn("ERROR scraps/p1/fig-2/object.yaml: missing kind", proc.stderr)  # the rest is checked
                    self.assertIn("p1/fig-1", proc.stdout)
                    self.assertIn("p1/fig-2", proc.stdout)


if __name__ == "__main__":
    unittest.main()
