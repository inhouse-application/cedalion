"""Checks for the color measures and view."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import color  # noqa: E402


class ColorChecks(unittest.TestCase):
    def test_luminance_end_points(self):
        self.assertAlmostEqual(float(color.luminance(color.rgb(["#ffffff"]))[0]), 1.0)
        self.assertAlmostEqual(float(color.luminance(color.rgb(["#000000"]))[0]), 0.0)

    def test_red_green_pair_under_each_vision(self):
        d = color.distances(color.rgb(["#2ca02c", "#d62728"]))  # tab10 green and red
        self.assertGreater(d[0, 0, 1], d[1:, 0, 1].max())

    def test_names_resolve(self):
        self.assertEqual(color.colors("tol.high-contrast"), ["#004488", "#ddaa33", "#bb5566"])
        self.assertEqual(color.colors("okabe_ito")[1], "#e69f00")
        self.assertEqual(len(color.colors("cmc.batlowS")), 100)
        self.assertEqual(color.colors("#ABCDEF"), ["#abcdef"])
        with self.assertRaises(ValueError):
            color.colors("no-such-scheme")

    def test_view_reports_the_closest_pair_of_each_vision(self):
        # The closest pair differs by vision: blue/purple under protanopia, orange/yellow otherwise.
        lines = color.view(["#0072b2", "#e69f00", "#f0e442", "#cc79a7"], None).splitlines()
        self.assertEqual([line.split()[0] for line in lines], list(color.VISIONS))
        self.assertIn("#e69f00 / #f0e442", lines[0])
        self.assertIn("#0072b2 / #cc79a7", lines[2])

    def test_continuous_maps_are_only_drawn(self):
        self.assertTrue(color.sampled("viridis"))
        self.assertFalse(color.sampled("cmc.batlowS"))
        self.assertFalse(color.sampled("okabe_ito"))
        self.assertFalse(color.sampled("tab10_r"))
        self.assertEqual(color.view(color.colors("viridis"), None, pairs_too=False), "")


if __name__ == "__main__":
    unittest.main()
