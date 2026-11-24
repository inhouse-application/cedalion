"""Checks for the token file reader and the sheet writer."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tokens  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def color(hex_):
    return {"colorSpace": "srgb", "components": [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)], "hex": hex_}


class TokenChecks(unittest.TestCase):
    def setUp(self):
        self.tree = tokens.load()

    def test_repository_tokens_are_valid_and_sheets_current(self):
        self.assertEqual(tokens.problems(self.tree), [])
        for path, text in tokens.sheets(self.tree).items():
            self.assertEqual(path.read_text(encoding="utf-8"), text, path.name)

    def test_report_broken_aliases_and_colors(self):
        tree = copy.deepcopy(self.tree)
        bright = tree["palette"]["tol"]["bright"]
        bright["blue"]["$value"] = "{palette.nowhere.blue}"
        bright["red"]["$value"] = {"colorSpace": "srgb", "components": [1, 0, 0], "hex": "#00ff00"}
        found = "\n".join(tokens.problems(tree))
        self.assertIn("names no token", found)
        self.assertIn("does not match", found)

    def test_cycle_follows_its_aliases(self):
        tree = copy.deepcopy(self.tree)
        tree["sheet"]["default"]["axes"]["prop_cycle"] = {"$type": "color", "1": {"$value": "{palette.tol.bright.red}"}}
        text = tokens.sheets(tree)[tokens.ROOT / "styles/default.mplstyle"]
        self.assertIn("axes.prop_cycle: cycler('color', ['ee6677'])", text)

    def test_palettes_are_keyed_by_path(self):
        self.assertEqual(tokens.palettes(self.tree)["tol.high-contrast"],
                         [("blue", "#004488"), ("yellow", "#ddaa33"), ("red", "#bb5566")])

    def test_dimensions_become_points(self):
        from tools.units import convert, parse

        self.assertAlmostEqual(convert(*parse("9.3333px"), "pt"), 7, places=3)
        self.assertAlmostEqual(convert(183, "mm", "in"), 7.2047, places=4)
        self.assertEqual(convert(1, "rem", "pt"), 12)
        self.assertEqual(tokens.rc_value({"value": 0.3333, "unit": "px"}), "0.25")
        tree = copy.deepcopy(self.tree)
        tree["sheet"]["default"]["font"]["size"]["$value"] = {"value": 8, "unit": "pt"}
        self.assertIn("a dimension is", "\n".join(tokens.problems(tree)))


if __name__ == "__main__":
    unittest.main()
