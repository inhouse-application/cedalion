"""Tests for tools/check_contribution.py (internal lab scrapbook contributions).

  .pixi/envs/default/bin/python -m unittest -v tools.test_contribution
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import add_scrap  # noqa: E402
import check_contribution  # noqa: E402

QUIET = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Lab Member",
    "GIT_AUTHOR_EMAIL": "member@example.org",
    "GIT_COMMITTER_NAME": "Lab Member",
    "GIT_COMMITTER_EMAIL": "member@example.org",
}


def write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def make_scrap(book: Path, paper: str, slug: str, *, level1: bool = True, archived: bool = False) -> None:
    folder = book / "scraps" / paper / slug
    folder.mkdir(parents=True, exist_ok=True)
    img_path = folder / f"{slug}.jpg"
    Image.new("RGB", (40, 30), "white").save(img_path, "JPEG")
    digest = hashlib.sha256(img_path.read_bytes()).hexdigest()
    obj = (
        f"kind: fig\nlabel: Fig. {slug[-1]}\nlabel_source: jats\npaper: {paper}\n"
        f"url: https://example.org/{paper}\ncontentUrl: https://example.org/{paper}/{slug}.jpg\n"
        f"accessDate: '2026-11-24'\nrights: CC-BY-4.0\n"
        f"files:\n- {{path: {slug}.jpg, sha256: {digest}, width: 40, height: 30}}\n"
    )
    if level1:
        obj += (
            "caption_source: {type: jats, id: PMC123456, element: Fig1}\n"
            "layout: {panels: 1, grid: 1x1}\n"
            "panels:\n- id: '-'\n  chart: [scatter]\n"
        )
        write(folder / "caption.md", "**Fig. 1** Scatter plot of x against y across 20 sites.\n")
        write(folder / "description.md", "## alt-text\n\nScatter plot.\n\n## long-desc\n\nPoints from 0 to 10.\n")
    else:
        obj += "caption_source: null\n"
    if archived:
        obj += "archived: true\n"
    write(folder / "object.yaml", obj)


class ContributionChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cedalion-test-contrib-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.book = self.tmp / "orion"
        self.book.mkdir()
        write(self.book / "vocab/domain.yaml", "urban:\n  name: Urban\n  definition: Cities.\n")
        write(self.book / "papers/kimUrbanHeatIslands2025/item.yaml",
              "itemType: journalArticle\ncitationKey: kimUrbanHeatIslands2025\n"
              "title: The Urban Heat Islands of Seoul\n"
              "creators:\n- {creatorType: author, firstName: Min, lastName: Kim}\n"
              "date: '2025-05-01'\nDOI: 10.1000/kim.2025\ntags:\n- {tag: urban}\n")
        make_scrap(self.book, "kimUrbanHeatIslands2025", "fig-1")
        self.git("init", "-q", "-b", "main")
        self.commit("base")
        self.git("checkout", "-q", "-b", "contrib")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.book), *args], check=True, capture_output=True,
                              text=True, env={**os.environ, **QUIET}).stdout.strip()

    def commit(self, msg: str = "contrib") -> str:
        self.git("add", "-A")
        self.git("commit", "-qm", msg)
        return self.git("rev-parse", "HEAD")

    def validate(self) -> list[str]:
        return check_contribution.validate_contribution(check_contribution.TOOL_ROOT, self.book, "main")

    def test_expected_citation_key_matches_add_scrap_rule(self):
        item = {
            "title": "A Global Assessment of River Flood Risk",
            "creators": [{"creatorType": "author", "firstName": "Ana", "lastName": "Muñoz-Castro"}],
            "date": "2026-03-14",
        }
        self.assertEqual(add_scrap.expected_citation_key(item), "munozcastroGlobalAssessmentRiver2026")

    def test_valid_new_paper_scrap_and_domain_addition_passes(self):
        write(self.book / "vocab/domain.yaml",
              (self.book / "vocab/domain.yaml").read_text() + "hydrology:\n  name: Hydrology\n  definition: Water.\n")
        write(self.book / "papers/leeRiverFlowPatterns2026/item.yaml",
              "itemType: journalArticle\ncitationKey: leeRiverFlowPatterns2026\n"
              "title: River Flow Patterns in Monsoon Basins\n"
              "creators:\n- {creatorType: author, firstName: Ji, lastName: Lee}\n"
              "date: '2026-01-10'\nDOI: 10.1000/lee.2026\ntags:\n- {tag: hydrology}\n")
        make_scrap(self.book, "leeRiverFlowPatterns2026", "fig-1")
        self.commit("Add Lee 2026 Fig 1")
        self.assertEqual(self.validate(), [])

    def test_adding_new_scrap_under_existing_paper_passes(self):
        make_scrap(self.book, "kimUrbanHeatIslands2025", "fig-2")
        self.commit("Add Fig 2 to existing paper")
        self.assertEqual(self.validate(), [])

    def test_non_standard_citation_key_is_rejected(self):
        write(self.book / "papers/lee_custom_2026/item.yaml",
              "itemType: journalArticle\ncitationKey: lee_custom_2026\n"
              "title: River Flow Patterns in Monsoon Basins\n"
              "creators:\n- {creatorType: author, firstName: Ji, lastName: Lee}\n"
              "date: '2026-01-10'\nDOI: 10.1000/lee.2026\n")
        make_scrap(self.book, "lee_custom_2026", "fig-1")
        self.commit("Custom key")
        errors = self.validate()
        self.assertTrue(any("Better BibTeX default rule" in e and "leeRiverFlowPatterns2026" in e for e in errors), errors)

    def test_duplicate_doi_is_rejected_naming_existing_paper(self):
        write(self.book / "papers/kimUrbanHeatIslands2025a/item.yaml",
              "itemType: journalArticle\ncitationKey: kimUrbanHeatIslands2025a\n"
              "title: The Urban Heat Islands of Seoul\n"
              "creators:\n- {creatorType: author, firstName: Min, lastName: Kim}\n"
              "date: '2025-05-01'\nDOI: 10.1000/KIM.2025\n")
        make_scrap(self.book, "kimUrbanHeatIslands2025a", "fig-2")
        self.commit("Dup DOI")
        errors = self.validate()
        self.assertTrue(any("duplicate DOI" in e and "papers/kimUrbanHeatIslands2025" in e for e in errors), errors)

    def test_overwriting_existing_paper_or_scrap_or_domain_term_is_rejected(self):
        write(self.book / "papers/kimUrbanHeatIslands2025/item.yaml",
              (self.book / "papers/kimUrbanHeatIslands2025/item.yaml").read_text() + "volume: '12'\n")
        write(self.book / "scraps/kimUrbanHeatIslands2025/fig-1/caption.md", "**Fig. 1** Overwritten.\n")
        write(self.book / "vocab/domain.yaml", "urban:\n  name: Urban\n  definition: Changed.\n")
        self.commit("Overwrite existing")
        errors = self.validate()
        self.assertTrue(any("outside contribution permissions" in e and "item.yaml" in e for e in errors), errors)
        self.assertTrue(any("outside contribution permissions" in e and "caption.md" in e for e in errors), errors)
        self.assertTrue(any("modifying existing term 'urban'" in e for e in errors), errors)

    def test_forbidden_notes_archived_pdf_and_level0_are_rejected(self):
        write(self.book / "papers/leeRiverFlowPatterns2026/item.yaml",
              "itemType: journalArticle\ncitationKey: leeRiverFlowPatterns2026\n"
              "title: River Flow Patterns in Monsoon Basins\n"
              "creators:\n- {creatorType: author, firstName: Ji, lastName: Lee}\n"
              "date: '2026-01-10'\nDOI: 10.1000/lee.2026\n")
        make_scrap(self.book, "leeRiverFlowPatterns2026", "fig-1", level1=False, archived=True)
        write(self.book / "scraps/leeRiverFlowPatterns2026/fig-1/notes.md", "My personal opinion.\n")
        write(self.book / "scraps/leeRiverFlowPatterns2026/fig-1/paper.pdf", b"%PDF-1.4\n")
        self.commit("Forbidden items")
        errors = self.validate()
        self.assertTrue(any("notes.md is owner-only" in e for e in errors), errors)
        self.assertTrue(any("PDF binaries" in e for e in errors), errors)
        self.assertTrue(any("`archived:` is owner-only" in e for e in errors), errors)
        self.assertTrue(any("must be at least Level 1" in e for e in errors), errors)

    def test_validates_committed_head_tree_not_uncommitted_working_tree(self):
        # Commit an invalid citationKey/title mismatch.
        write(self.book / "papers/leeCustomTitle2026/item.yaml",
              "itemType: journalArticle\ncitationKey: leeCustomTitle2026\n"
              "title: River Flow Patterns in Monsoon Basins\n"
              "creators:\n- {creatorType: author, firstName: Ji, lastName: Lee}\n"
              "date: '2026-01-10'\nDOI: 10.1000/lee.2026\n")
        make_scrap(self.book, "leeCustomTitle2026", "fig-1")
        self.commit("Bad key committed")
        errors_before = self.validate()
        self.assertTrue(any("Better BibTeX default rule" in e for e in errors_before), errors_before)
        # Fixing the title ONLY in the working tree (uncommitted) must NOT turn HEAD into a false pass.
        write(self.book / "papers/leeCustomTitle2026/item.yaml",
              "itemType: journalArticle\ncitationKey: leeCustomTitle2026\n"
              "title: Custom Title Study\n"
              "creators:\n- {creatorType: author, firstName: Ji, lastName: Lee}\n"
              "date: '2026-01-10'\nDOI: 10.1000/lee.2026\n")
        self.assertEqual(self.validate(), errors_before)

    def test_concurrent_domain_addition_on_base_is_not_reported_as_deletion(self):
        # Contributor appends 'hydrology' on contrib branch.
        write(self.book / "vocab/domain.yaml",
              (self.book / "vocab/domain.yaml").read_text() + "hydrology:\n  name: Hydrology\n  definition: Water.\n")
        make_scrap(self.book, "kimUrbanHeatIslands2025", "fig-2")
        self.commit("Add hydrology and fig-2")
        # Meanwhile main advances with a different domain term 'climate'.
        self.git("checkout", "-q", "main")
        write(self.book / "vocab/domain.yaml",
              (self.book / "vocab/domain.yaml").read_text() + "climate:\n  name: Climate\n  definition: Weather.\n")
        self.commit("Main adds climate")
        self.git("checkout", "-q", "contrib")
        self.assertEqual(self.validate(), [])

    def test_base_doi_correction_colliding_with_contributed_paper_is_rejected(self):
        # Contributor adds Lee 2026 with DOI 10.1000/lee.2026 on contrib branch.
        write(self.book / "papers/leeRiverFlowPatterns2026/item.yaml",
              "itemType: journalArticle\ncitationKey: leeRiverFlowPatterns2026\n"
              "title: River Flow Patterns in Monsoon Basins\n"
              "creators:\n- {creatorType: author, firstName: Ji, lastName: Lee}\n"
              "date: '2026-01-10'\nDOI: 10.1000/lee.2026\n")
        make_scrap(self.book, "leeRiverFlowPatterns2026", "fig-1")
        self.commit("Add Lee 2026")
        # Meanwhile owner corrects Kim's DOI on main to 10.1000/lee.2026 (clean Git merge, duplicate DOI after merge!).
        self.git("checkout", "-q", "main")
        write(self.book / "papers/kimUrbanHeatIslands2025/item.yaml",
              (self.book / "papers/kimUrbanHeatIslands2025/item.yaml").read_text().replace("10.1000/kim.2025", "10.1000/lee.2026"))
        self.commit("Fix Kim DOI on main")
        self.git("checkout", "-q", "contrib")
        errors = self.validate()
        self.assertTrue(any("duplicate DOI 10.1000/lee.2026" in e for e in errors), errors)

    def test_base_paper_deletion_orphaning_contributed_scrap_is_rejected(self):
        # Contributor adds fig-2 under existing Kim paper on contrib branch.
        make_scrap(self.book, "kimUrbanHeatIslands2025", "fig-2")
        self.commit("Add fig-2 to Kim")
        # Meanwhile owner removes Kim paper and its old scrap on main (clean Git merge, orphaned scrap after merge!).
        self.git("checkout", "-q", "main")
        shutil.rmtree(self.book / "papers/kimUrbanHeatIslands2025")
        shutil.rmtree(self.book / "scraps/kimUrbanHeatIslands2025")
        self.commit("Remove Kim paper on main")
        self.git("checkout", "-q", "contrib")
        errors = self.validate()
        self.assertTrue(any("item.yaml" in e and "missing" in e for e in errors), errors)
        self.assertTrue(any("must be at least Level 1" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
