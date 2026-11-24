"""Validate an internal lab member's scrap contribution to the scrapbook (orion) against a base ref.

Lab contributions are strictly add-only, and every check runs strictly against committed Git trees
(resolved once as exact commit SHAs for BASE, HEAD, and their merge-base), never against uncommitted
working-tree edits:
  - Contributor permission boundaries are checked on `merge-base..HEAD`: only new files under
    `papers/<citationKey>/` and `scraps/<citationKey>/<slug>/`, and append-only new terms in
    `vocab/domain.yaml`, are allowed. Overwriting, modifying or deleting any existing paper, scrap,
    owner marker or configuration file is outside contribution permissions.
  - Forbidden files and fields: `notes.md` (owner-only Level 3), `.cache/` or PDF files, and `archived:`
    in any contributed scrap's `object.yaml`.
  - Data integrity (`tools/check.py`, DOI uniqueness, Better BibTeX `citationKey`, parent-paper
    existence, Level 1+) is checked on the actual 3-way merged tree of `BASE` and `HEAD` (built in a
    temporary bare repository without touching `orion`'s working tree or `.git`), so concurrent changes
    on `BASE` (such as a DOI correction or deleted paper) are caught before merge.
  - Every newly added paper's `citationKey` (and directory name) must follow the Better BibTeX default
    rule `auth.lower + shorttitle(3,3) + year` (tools/add_scrap.py:expected_citation_key), with a single
    lowercase suffix (`a`..`z`) allowed only when the base key is already held by another paper with a
    different DOI.

Usage: python tools/check_contribution.py [--scrapbook PATH] [--base REF] [--head REF]
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import yaml

import add_scrap
import check as checker
import index
from check_palettes import check_subset_evidence
from paths import TOOL_ROOT, for_command


def git(book: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(book), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def git_bytes(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or f"git {' '.join(args)} failed")
    return proc.stdout


def git_show_yaml(book: Path, rev: str, rel: str):
    proc = subprocess.run(["git", "-C", str(book), "show", f"{rev}:{rel}"], capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return yaml.safe_load(proc.stdout)


def extract_tree(repo: Path, tree_or_rev: str, dest: Path) -> None:
    """Extract the exact Git tree TREE_OR_REV into DEST via `git archive` (no working-tree files)."""
    raw = git_bytes(repo, "archive", "--format=tar", tree_or_rev)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        archive.extractall(dest, filter="data")


def diff_entries(book: Path, merge_base: str, head_sha: str) -> list[tuple[str, str]]:
    """Committed changes from MERGE_BASE to HEAD_SHA as `(status, posix_path)` without rename detection."""
    out = git(book, "-c", "core.quotePath=false", "diff", "--name-status", "--no-renames", merge_base, head_sha)
    entries = []
    for line in out.splitlines():
        if not line.strip():
            continue
        status, _, path = line.partition("\t")
        entries.append((status.strip(), path.strip()))
    return entries


def check_domain_append_only(book: Path, merge_base: str, base_sha: str, head_sha: str,
                             errors: list[str]) -> dict | None:
    """Verify `vocab/domain.yaml` in HEAD_SHA only appends terms relative to MERGE_BASE, and that none
    of the newly added terms conflict with terms added concurrently on BASE_SHA. Returns the merged
    domain mapping when valid, else None."""
    old = git_show_yaml(book, merge_base, "vocab/domain.yaml")
    new = git_show_yaml(book, head_sha, "vocab/domain.yaml")
    if not isinstance(new, dict):
        errors.append("vocab/domain.yaml: must be a YAML mapping of domain terms")
        return None
    old_map = old if isinstance(old, dict) else {}
    ok = True
    for term, val in old_map.items():
        if term not in new:
            errors.append(f"vocab/domain.yaml: deleting existing term {term!r} is not allowed")
            ok = False
        elif new[term] != val:
            errors.append(f"vocab/domain.yaml: modifying existing term {term!r} is not allowed")
            ok = False
    added_terms = {term: new[term] for term in new if term not in old_map}
    if base_sha == merge_base:
        return new if ok else None
    base_dom = git_show_yaml(book, base_sha, "vocab/domain.yaml")
    if base_dom is not None and not isinstance(base_dom, dict):
        errors.append("vocab/domain.yaml: base domain.yaml is not a YAML mapping")
        return None
    merged = dict(base_dom or {})
    for term, val in added_terms.items():
        if term in merged and merged[term] != val:
            errors.append(
                f"vocab/domain.yaml: added term {term!r} conflicts with a different definition on base"
            )
            ok = False
        else:
            merged[term] = val
    return merged if ok else None


def build_merged_tree(book: Path, base_sha: str, head_sha: str, merge_base: str,
                      merged_domain: dict | None, tmp: Path) -> tuple[Path | None, list[str]]:
    """Materialize the exact merged tree of BASE_SHA and HEAD_SHA into TMP/book without writing to BOOK."""
    tree_dir = tmp / "book"
    tree_dir.mkdir()
    if base_sha == merge_base:
        extract_tree(book, head_sha, tree_dir)
        return tree_dir, []

    # Compute the 3-way merge in a temporary bare repo sharing BOOK's object store (zero writes to BOOK).
    objects_raw = git(book, "rev-parse", "--git-path", "objects").strip()
    objects_dir = Path(objects_raw)
    if not objects_dir.is_absolute():
        objects_dir = (book / objects_dir).resolve()
    bare = tmp / "merge.git"
    git(tmp, "init", "-q", "--bare", str(bare))
    info_dir = bare / "objects" / "info"
    info_dir.mkdir(parents=True, exist_ok=True)
    (info_dir / "alternates").write_text(f"{objects_dir}\n", encoding="utf-8")

    proc = subprocess.run(
        ["git", "-C", str(bare), "-c", "core.quotePath=false",
         "merge-tree", "--write-tree", "--no-messages", "--name-only", base_sha, head_sha],
        capture_output=True, text=True,
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if proc.returncode not in (0, 1) or not lines:
        msg = proc.stderr.strip() or f"git merge-tree failed (exit {proc.returncode})"
        return None, [f"could not merge {head_sha[:7]} with base {base_sha[:7]}: {msg}"]
    tree_oid = lines[0].strip()
    conflicts = [line.strip() for line in lines[1:]]
    if proc.returncode == 1:
        # Non-overlapping EOF appends to vocab/domain.yaml are allowed when already verified as disjoint YAML additions.
        if conflicts != ["vocab/domain.yaml"] or merged_domain is None:
            return None, [
                f"merge conflict between base ({base_sha[:7]}) and head ({head_sha[:7]}) in: "
                f"{', '.join(conflicts)}; rebase onto base and re-run"
            ]
        extract_tree(bare, tree_oid, tree_dir)
        (tree_dir / "vocab/domain.yaml").write_text(
            yaml.safe_dump(merged_domain, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        return tree_dir, []

    extract_tree(bare, tree_oid, tree_dir)
    return tree_dir, []


def validate_contribution_with_shas(root: Path, book: Path, base: str,
                                    head: str = "HEAD") -> tuple[list[str], str, str]:
    errors: list[str] = []
    try:
        base_sha = git(book, "rev-parse", "--verify", f"{base}^{{commit}}").strip()
        head_sha = git(book, "rev-parse", "--verify", f"{head}^{{commit}}").strip()
        merge_base = git(book, "merge-base", base_sha, head_sha).strip()
        changes = diff_entries(book, merge_base, head_sha)
    except RuntimeError as exc:
        return [f"git diff against {base} failed: {exc}"], "", ""
    if not changes:
        return [f"no committed changes between {base} ({merge_base[:7]}) and {head} ({head_sha[:7]})"], base_sha, head_sha

    new_papers: set[str] = set()
    new_scraps: set[tuple[str, str]] = set()
    domain_changed = False

    for status, rel in changes:
        parts = rel.split("/")
        if rel == "vocab/domain.yaml":
            if status not in ("A", "M"):
                errors.append(f"{rel}: status {status} is not allowed (only adding new domain terms)")
            else:
                domain_changed = True
            continue
        if status != "A":
            errors.append(f"{rel}: {status} is outside contribution permissions (overwriting or deleting existing files is forbidden)")
            continue
        if rel.startswith(".cache/") or rel.lower().endswith(".pdf"):
            errors.append(f"{rel}: PDF binaries and .cache/ files must not be committed")
            continue
        if parts[-1] == "notes.md":
            errors.append(f"{rel}: notes.md is owner-only (Level 3) and must not be included in contributions")
            continue
        if parts[0] == "papers" and len(parts) == 3 and parts[2] in ("item.yaml", "context.yaml"):
            new_papers.add(parts[1])
        elif parts[0] == "scraps" and len(parts) == 4:
            new_scraps.add((parts[1], parts[2]))
        else:
            errors.append(f"{rel}: path is outside the allowed contribution paths (papers/<key>/, scraps/<key>/<slug>/, vocab/domain.yaml)")

    merged_domain: dict | None = None
    if domain_changed:
        merged_domain = check_domain_append_only(book, merge_base, base_sha, head_sha, errors)

    # Check against both merge_base and current base_sha trees so existing or newly landed items are never overwritten.
    mb_files = set(git(book, "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", merge_base).splitlines())
    base_only_files = (
        mb_files if base_sha == merge_base
        else set(git(book, "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", base_sha).splitlines())
    )
    all_base_files = mb_files | base_only_files
    base_scraps = {(p.split("/")[1], p.split("/")[2]) for p in all_base_files if p.startswith("scraps/") and len(p.split("/")) >= 4}
    base_paper_keys = {p.split("/")[1] for p in all_base_files if p.startswith("papers/") and len(p.split("/")) >= 3}

    for paper, slug in sorted(new_scraps):
        if (paper, slug) in base_scraps:
            errors.append(f"scraps/{paper}/{slug}: modifying an existing scrap is outside contribution permissions")
    for paper_key in sorted(new_papers):
        if paper_key in base_paper_keys:
            errors.append(f"papers/{paper_key}: paper already exists on {base} (overwriting existing papers is forbidden)")

    # Validate the exact merged tree of BASE_SHA + HEAD_SHA (never the working tree).
    with tempfile.TemporaryDirectory(prefix="cedalion-contrib-") as tmp_raw:
        try:
            tree_dir, merge_errors = build_merged_tree(
                book, base_sha, head_sha, merge_base, merged_domain, Path(tmp_raw),
            )
        except (RuntimeError, tarfile.TarError, OSError) as exc:
            return errors + [f"could not build merged tree of {base_sha[:7]} and {head_sha[:7]}: {exc}"], base_sha, head_sha
        if merge_errors or tree_dir is None:
            return errors + merge_errors, base_sha, head_sha

        r = checker.Report(tree_dir)
        found = index.sources(root, tree_dir, images=True)
        for problem in found.unreadable():
            r.err(problem.path, problem.why)
        v = {name: set(terms) for name, terms in found.vocab.items()}
        papers = {paper.key: paper for paper in found.papers if not paper.error}
        for paper in papers.values():
            checker.check_paper(paper, r, v["domain"])
        by_paper: dict[str, dict] = {}
        for scrap in found.scraps:
            if scrap.palette is not None:
                by_paper.setdefault(scrap.paper, {})[scrap.folder / "palette.yaml"] = scrap.palette
        for paper_key in sorted(by_paper):
            check_subset_evidence(by_paper[paper_key], r)
        levels: dict[tuple[str, str], str] = {}
        for scrap in found.scraps:
            levels[scrap.key] = "-" if scrap.error else checker.check_scrap(scrap, papers, r, v)
        errors += r.errors

        # Enforce DOI uniqueness across every paper in the merged tree.
        dois: dict[str, set[str]] = {}
        for paper in papers.values():
            doi = str(paper.item.get("DOI") or "").strip().lower()
            if doi:
                dois.setdefault(doi, set()).add(paper.key)
        for doi, key_set in sorted(dois.items()):
            keys = sorted(key_set)
            if len(keys) > 1:
                existing = [k for k in keys if k in base_paper_keys]
                added = [k for k in keys if k not in base_paper_keys]
                if existing and added:
                    errors.append(
                        f"duplicate DOI {doi}: paper already exists as papers/{existing[0]}; "
                        f"remove papers/{', '.join(added)} and put scraps under scraps/{existing[0]}/<slug>/"
                    )
                else:
                    errors.append(f"duplicate DOI {doi} across papers: {', '.join(keys)}")

        # Enforce Better BibTeX default citationKey (`auth.lower + shorttitle(3,3) + year`) on new papers.
        all_known_keys = set(papers) | base_paper_keys
        for key in sorted(new_papers):
            paper = papers.get(key)
            if paper is None:
                continue
            expected = add_scrap.expected_citation_key(paper.item)
            if not expected:
                errors.append(f"papers/{key}/item.yaml: cannot compute expected Better BibTeX citationKey")
                continue
            if key == expected:
                continue
            # Allow a single lowercase letter suffix only when the base key is already taken by another paper.
            if re.fullmatch(rf"{re.escape(expected)}[a-z]", key) and expected in all_known_keys:
                continue
            errors.append(
                f"papers/{key}/item.yaml: citationKey {key!r} does not follow Better BibTeX default rule "
                f"`auth.lower + shorttitle(3,3) + year` (expected {expected!r})"
            )

        # Check every newly added scrap in the merged tree: no `archived:` field, and at least Level 1.
        scrap_by_key = {s.key: s for s in found.scraps}
        for skey in sorted(new_scraps):
            scrap = scrap_by_key.get(skey)
            if scrap is None:
                errors.append(f"scraps/{skey[0]}/{skey[1]}: scrap was not read")
                continue
            if "archived" in scrap.obj:
                errors.append(f"scraps/{skey[0]}/{skey[1]}/object.yaml: `archived:` is owner-only and must not be set in contributions")
            lvl = levels.get(skey, "-")
            if lvl not in ("1", "2"):
                errors.append(f"scraps/{skey[0]}/{skey[1]}: level is {lvl!r}, must be at least Level 1 (described)")

    return errors, base_sha, head_sha


def validate_contribution(root: Path, book: Path, base: str, head: str = "HEAD") -> list[str]:
    errors, _, _ = validate_contribution_with_shas(root, book, base, head)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scrapbook", type=Path, help="scrapbook git repository (default: see tools/paths.py)")
    parser.add_argument("--base", default="origin/main", help="base git ref to diff against (default: origin/main)")
    parser.add_argument("--head", default="HEAD", help="submitted git ref to validate (default: HEAD)")
    args = parser.parse_args(argv)
    book = for_command(args.scrapbook, part="papers")
    if book is None:
        print("no scrapbook found; pass --scrapbook PATH or set CEDALION_SCRAPBOOK.", file=sys.stderr)
        return 2
    errors, base_sha, head_sha = validate_contribution_with_shas(TOOL_ROOT, book, args.base, args.head)
    for err in errors:
        print("ERROR", err, file=sys.stderr)
    if base_sha and head_sha:
        print(f"checked merged tree of base={base_sha[:12]} head={head_sha[:12]}")
    print(f"contribution check: {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
