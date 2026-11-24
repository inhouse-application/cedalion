"""Capture keeps papers and images it cannot vouch for; no network and no .cache needed."""

import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import fitz
import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import add_scrap
from check import label_only


def png(color):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, "PNG")
    return buffer.getvalue()


class Capture(unittest.TestCase):
    ENTRY = {"doi": "10.1/b", "kind": "fig", "label": "Fig. 2", "label_source": "filename",
             "url": "https://example.org/b", "contentUrl": "https://example.org/b-fig2.png"}

    def run_capture(self, root, entry, responses):
        """capture() in a scratch repository; `responses` maps URL to downloaded bytes."""
        item = {"citationKey": "keyb", "DOI": entry["doi"], "title": "B"}
        with mock.patch.multiple(add_scrap, ROOT=root, CACHE=root / ".cache"), \
                mock.patch.object(add_scrap, "crossref_work", return_value={}), \
                mock.patch.object(add_scrap, "zotero_item", return_value=item), \
                mock.patch.object(add_scrap, "spdx_rights", return_value="CC-BY-4.0"), \
                mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = lambda request, timeout: io.BytesIO(responses[request.full_url])
            with mock.patch("time.sleep"):
                return add_scrap.capture(entry)

    def test_key_holding_another_doi_stops_the_entry(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "papers/keyb").mkdir(parents=True)
            (root / "papers/keyb/item.yaml").write_text(yaml.safe_dump({"DOI": "10.1/A"}))
            with self.assertRaisesRegex(ValueError, "already holds another paper"):
                self.run_capture(root, self.ENTRY, {self.ENTRY["contentUrl"]: png("red")})
            self.assertFalse((root / "scraps").exists())

    def test_captured_image_is_kept_and_a_changed_url_stops(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_capture(root, self.ENTRY, {self.ENTRY["contentUrl"]: png("red")})
            image = root / "scraps/keyb/fig-2/fig-2.jpg"
            before = image.read_bytes()
            self.run_capture(root, self.ENTRY, {})  # no download needed the second time
            self.assertEqual(image.read_bytes(), before)
            moved = {**self.ENTRY, "contentUrl": "https://example.org/b-fig2-corrected.png"}
            with self.assertRaisesRegex(ValueError, "contentUrl differs"):
                self.run_capture(root, moved, {moved["contentUrl"]: png("blue")})
            self.assertEqual(image.read_bytes(), before)
            obj = yaml.safe_load((root / "scraps/keyb/fig-2/object.yaml").read_text())
            self.assertEqual(obj["contentUrl"], self.ENTRY["contentUrl"])

    def test_error_page_is_not_cached(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(Exception):
                self.run_capture(root, self.ENTRY, {self.ENTRY["contentUrl"]: b"<html>consent</html>"})
            self.assertEqual(list((root / ".cache").rglob("*.png")), [])
            self.run_capture(root, self.ENTRY, {self.ENTRY["contentUrl"]: png("red")})
            self.assertTrue((root / "scraps/keyb/fig-2/fig-2.jpg").exists())

    def test_label_without_caption_text_is_no_caption(self):
        xml = b'<article><fig id="F2"><label>Fig. 2</label><caption/></fig></article>'
        with mock.patch.object(add_scrap, "fetch", return_value=xml):
            self.assertIsNone(add_scrap.jats_caption("PMC1", "F2"))


class Validation(unittest.TestCase):
    def test_label_only_captions(self):
        for text in ["", "Fig. 2", "**Fig. 2**", "**Figure S3:**", "Table 1."]:
            self.assertTrue(label_only(text), text)
        for text in ["**Fig. 2** Maps.", "**Fig. 2 Global maps.**"]:
            self.assertFalse(label_only(text), text)


class Slugs(unittest.TestCase):
    def test_labels_with_and_without_numbers(self):
        self.assertEqual(add_scrap.slug_for("fig", "Fig. 3"), "fig-3")
        self.assertEqual(add_scrap.slug_for("fig", "Fig. S1"), "fig-s1")
        self.assertEqual(add_scrap.slug_for("graphical-abstract", "Graphical abstract"), "ga")
        self.assertEqual(add_scrap.slug_for("media", "Video"), "media")


if __name__ == "__main__":
    unittest.main()
