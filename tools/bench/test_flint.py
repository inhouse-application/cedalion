"""Run with pixi run python -m unittest tools.bench.test_flint."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from matplotlib.figure import Figure

from tools import flint
from tools.flint import build_context, measure


class Measure(unittest.TestCase):
    def setUp(self):
        self.fig = Figure(figsize=(4, 3))
        self.ax = self.fig.subplots()
        self.ax.set_axis_off()

    def of(self, what, **kwargs):
        return [r for r in measure(self.fig, more=True, **kwargs) if r[0] == what]

    def test_outside_canvas_by_default(self):
        self.fig.text(0.99, 0.5, "Outside")
        self.ax.text(0.5, 0.5, "Small", fontsize=5)
        [row] = measure(self.fig)
        self.assertEqual(row[0], "outside-canvas")
        self.assertRegex(row[2], r"^\d+\.\d\d pt$")

    def test_tight_saved_area(self):
        self.fig.text(0.99, 0.5, "Visible when saved tight")
        self.assertTrue(self.of("outside-canvas"))
        self.assertEqual(self.of("outside-canvas", bbox_inches="tight"), [])
        self.assertTrue(self.of("outside-canvas", bbox_inches="tight", pad_inches=-0.2))

    def test_box_intersection_only_with_measure(self):
        for label in ("Alpha", "Beta"):
            self.ax.text(0.5, 0.5, label)
        self.assertEqual(measure(self.fig), [])
        [row] = self.of("box-intersection")
        self.assertIn("'Alpha' / ", row[1])

    def test_sizes_and_contrast(self):
        self.ax.imshow([[0]], cmap="gray", vmin=0, vmax=1)
        self.ax.text(0, 0, "Dark on black", color="#333333", ha="center", fontsize=5)
        self.assertEqual(self.of("smallest-text")[0][2], "5 pt")
        self.assertRegex(self.of("lowest-contrast")[0][2], r"^1\.\d\d:1$")

    def test_pair_closest_in_any_vision(self):
        self.ax.bar([0], [1], color="#006600", label="A")
        self.ax.bar([1], [1], color="#990000", label="B")
        self.ax.legend()
        [row] = self.of("pair-closest-in-any-vision")
        self.assertIn("'A' / 'B'", row[1])
        normal, deutan = (float(part.split()[1]) for part in row[2].split(", ")[:2])
        self.assertGreater(normal, deutan)

    def test_redundant_encodings_are_not_compared_by_color(self):
        for label, marker in [("A", "o"), ("B", "s")]:
            self.ax.plot([0, 1], color="red", marker=marker, label=label)
        self.ax.legend()
        self.assertEqual(self.of("pair-closest-in-any-vision"), [])

    def test_label_colors_across_legends_only(self):
        self.ax.plot([0, 1], color="#0072B2", label="X")
        self.ax.plot([1, 0], color="#E69F00", label="X")
        self.ax.legend()
        self.assertEqual(self.of("label-colors"), [])  # one legend: not compared
        self.fig = Figure(figsize=(5, 2.5))
        left, right = self.fig.subplots(1, 2)
        left.plot([0, 1], color="#0072B2", label="Model B")
        right.plot([0, 1], color="#E69F00", label="Model B")
        for ax in (left, right):
            ax.legend(loc="upper left")
        [row] = self.of("label-colors")
        self.assertEqual(row[1], "'Model B'")
        self.fig = Figure(figsize=(4, 3))  # two legends on one axes
        ax = self.fig.subplots()
        first = ax.legend(handles=ax.plot([0, 1], color="red", label="X"), loc="upper left")
        ax.add_artist(first)
        ax.legend(handles=ax.plot([1, 0], color="blue", label="X"), loc="lower right")
        self.assertEqual(len(self.of("label-colors")), 1)

    def test_saved_background_and_dpi(self):
        self.fig.text(0.5, 0.5, "White", color="white")
        self.assertRegex(self.of("lowest-contrast")[0][2], r"^1\.00:1$")
        self.assertRegex(self.of("lowest-contrast", facecolor="black")[0][2], r"^21\.00:1$")

    def test_text_records(self):
        self.ax.scatter([0], [0], color="red", s=4, label="Small")
        self.ax.scatter([1], [1], color="red", s=25, label="Large")
        self.ax.legend(loc="upper right")
        self.ax.text(.2, .2, "Point", color="black", size=12)
        ctx = build_context(self.fig)
        small, large = ctx.legends[0].entries
        self.assertEqual((small.label, small.marker, small.color), ("Small", large.marker, (1, 0, 0)))
        self.assertNotEqual(small.size, large.size)
        text, = [t for t in ctx.texts if t.kind == "data"]
        self.assertEqual((text.text, text.size, text.axes_index), ("Point", 12, 0))
        self.assertEqual((text.color, text.background), ((0, 0, 0, 1), (1, 1, 1)))

    def test_invisible_text_and_legend(self):
        self.ax.text(0.2, 0.2, "Hidden", fontsize=1, alpha=0)
        self.ax.legend([], [], title="Hidden", title_fontsize=1).set_visible(False)
        self.assertEqual(measure(self.fig, more=True), [])


class Cli(unittest.TestCase):
    def run_flint(self, tmp, *args):
        return subprocess.run([sys.executable, str(flint.ROOT / "tools/flint.py"), *args],
                              cwd=tmp, capture_output=True, text=True)

    def test_saves_figures_reports_json_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.py"
            good.write_text("from matplotlib import pyplot as plt\nfig, ax = plt.subplots()\n"
                            "fig.text(.99, .5, 'A|B')\nfig.savefig('out.png', dpi=100)\n")
            stop = Path(tmp) / "stop.py"
            stop.write_text("import argparse, os, sys\nargparse.ArgumentParser().parse_args()\n"
                            "os.chdir('/')\nsys.exit(0)\n")
            bad = Path(tmp) / "bad.py"
            bad.write_text("import sys\nsys.exit(7)\n")

            proc = self.run_flint(tmp, str(good), "--json")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((Path(tmp) / "out.png").is_file())  # the script's own output is written
            rows = [json.loads(line) for line in proc.stdout.splitlines()]
            self.assertEqual([r["what"] for r in rows], ["outside-canvas"])
            self.assertEqual(rows[0].keys(), {"file", "what", "where", "measured"})

            proc = self.run_flint(tmp, str(stop), str(bad), str(good))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("exited with 7", proc.stderr)
            self.assertIn("good.py | outside-canvas", proc.stdout)  # later scripts still run
            self.assertEqual(self.run_flint(tmp).returncode, 2)


if __name__ == "__main__":
    unittest.main()
