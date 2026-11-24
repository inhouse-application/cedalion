"""Capture the objects listed in inbox.yaml as Level 0 scraps.

For each inbox entry this writes, when missing:
  papers/<citationKey>/item.yaml          Zotero-schema fields from Crossref
  scraps/<citationKey>/<slug>/<slug>.jpg   downloaded file, resized to MAX_SIDE px on the long side
  scraps/<citationKey>/<slug>/object.yaml  Level 0 fields
  scraps/<citationKey>/<slug>/caption.md   verbatim caption, only when the article's JATS XML is available

Existing files are kept: a captured image is never replaced (a changed contentUrl stops that entry),
and a key that already holds a paper with another DOI stops the entry. Level 0 fields in an existing
object.yaml are refreshed; Level 1 fields are left alone.
All of these, inbox.yaml and the download cache .cache/ (git-ignored) are in the scrapbook
(tools/paths.py).

Usage: python tools/add_scrap.py [--only <doi>] [--scrapbook PATH]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from PIL import Image

import vault as vaults
from paths import for_command

# The scrapbook and its download cache, set by use_scrapbook() once the arguments are read.
ROOT: Path | None = None
CACHE: Path | None = None
USER_AGENT = "cedalion/0.1 (figure scrapbook)"
MAX_SIDE = 2000  # px, long side of the stored image
JPEG_QUALITY = 90

# Better BibTeX default citation key: [auth:lower][shorttitle3_3][year]
BBT_STOPWORDS = set(
    "a an the some from on in to of do with der die das ein eine einer eines einem einen un une la le "
    "les el las los al uno una unos unas de des del d and or for by at as is are".split()
)

LICENSE_TO_SPDX = {
    "creativecommons.org/licenses/by/4.0": "CC-BY-4.0",
    "creativecommons.org/licenses/by-nc/4.0": "CC-BY-NC-4.0",
    "creativecommons.org/licenses/by-nc-nd/4.0": "CC-BY-NC-ND-4.0",
    "creativecommons.org/licenses/by-nc-sa/4.0": "CC-BY-NC-SA-4.0",
    "creativecommons.org/licenses/by-sa/4.0": "CC-BY-SA-4.0",
}


def use_scrapbook(arg: Path | None) -> None:
    """Point ROOT and CACHE at the scrapbook; exit 2 when there is none."""
    global ROOT, CACHE
    ROOT = for_command(arg, required=True)
    CACHE = ROOT / ".cache"


def fetch(url: str, cache_name: str, check=None) -> bytes:
    """Return the cached response, or download, `check` (raising on a bad response) and cache it."""
    path = CACHE / cache_name
    if path.exists():
        return path.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    if check:
        check(data)  # e.g. an HTML error page served with status 200 must not be cached
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(data)
    partial.replace(path)
    time.sleep(0.5)
    return data


def ascii_fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def citation_key(work: dict) -> str:
    authors = work.get("author") or [{}]
    first = authors[0]
    auth = re.sub(r"[^a-z]", "", ascii_fold(first.get("family") or first.get("name") or "anon").lower())
    words = re.findall(r"[A-Za-z0-9]+", ascii_fold(work["title"][0]))
    short = "".join(w.capitalize() if w.islower() else w[0].upper() + w[1:]
                    for w in [w for w in words if w.lower() not in BBT_STOPWORDS][:3])
    return f"{auth}{short}{work['issued']['date-parts'][0][0]}"


def expected_citation_key(item: dict) -> str:
    """Better BibTeX default citation key (`auth.lower + shorttitle(3,3) + year`) computed from a
    Zotero-schema item.yaml record."""
    authors = [c for c in item.get("creators") or [] if isinstance(c, dict) and c.get("creatorType") == "author"]
    first = authors[0] if authors else {}
    raw_auth = first.get("lastName") or first.get("name") or "anon"
    auth = re.sub(r"[^a-z]", "", ascii_fold(str(raw_auth)).lower())
    words = re.findall(r"[A-Za-z0-9]+", ascii_fold(str(item.get("title") or "")))
    short = "".join(w.capitalize() if w.islower() else w[0].upper() + w[1:]
                    for w in [w for w in words if w.lower() not in BBT_STOPWORDS][:3])
    year_match = re.search(r"\d{4}", str(item.get("date") or ""))
    year = year_match.group(0) if year_match else ""
    return f"{auth}{short}{year}"


def iso_date(parts: list[int]) -> str:
    return "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts))


def crossref_work(doi: str) -> dict:
    data = fetch(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}",
                 f"crossref/{doi.replace('/', '_')}.json")
    return json.loads(data)["message"]


def vor_license(work: dict) -> str | None:
    licenses = work.get("license") or []
    for lic in licenses:
        if lic.get("content-version") == "vor":
            return lic["URL"]
    return licenses[0]["URL"] if licenses else None


def spdx_rights(license_url: str | None) -> str:
    if not license_url:
        return "NOASSERTION"
    for key, spdx in LICENSE_TO_SPDX.items():
        if key in license_url:
            return spdx
    return "LicenseRef-publisher"


def zotero_item(work: dict, pmcid: str | None) -> dict:
    parts = work["issued"]["date-parts"][0]
    item = {
        "itemType": "journalArticle",
        "citationKey": citation_key(work),
        "title": work["title"][0],
        "creators": [
            {"creatorType": "author", "firstName": a.get("given", ""), "lastName": a["family"]}
            if "family" in a else {"creatorType": "author", "name": a.get("name", "")}
            for a in work.get("author", [])
        ],
        "publicationTitle": (work.get("container-title") or [None])[0],
        "journalAbbreviation": (work.get("short-container-title") or [None])[0],
        "volume": work.get("volume"),
        "issue": work.get("issue"),
        "pages": work.get("page") or work.get("article-number"),
        "date": iso_date(parts),
        "DOI": work["DOI"],
        "ISSN": (work.get("ISSN") or [None])[0],
        "PMID": None,
        "PMCID": pmcid,
        "url": f"https://doi.org/{work['DOI']}",
        "language": work.get("language"),
        "rights": vor_license(work),
        "accessDate": dt.date.today().isoformat(),
        "libraryCatalog": "Crossref",
        "tags": [],
    }
    return {k: v for k, v in item.items() if v is not None}


def slug_for(kind: str, label: str) -> str:
    prefix = {"fig": "fig", "fig-group": "fig", "table-wrap": "table", "media": "media",
              "supplementary-material": "suppl", "disp-formula": "eq", "boxed-text": "box",
              "graphical-abstract": "ga"}[kind]
    number = re.search(r"[A-Z]?\d+[a-z]?", label)
    return f"{prefix}-{number.group(0).lower()}" if number else prefix  # "Graphical abstract" -> ga


def store_image(raw: bytes, dest: Path) -> dict:
    img = Image.open(io.BytesIO(raw))
    img = img.convert("RGB")
    scale = min(1.0, MAX_SIDE / max(img.size))
    if scale < 1.0:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
    dest.write_bytes(buf.getvalue())
    return {
        "path": dest.name,
        "sha256": hashlib.sha256(buf.getvalue()).hexdigest(),
        "width": img.width,
        "height": img.height,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    }


def text_of(el: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def jats_caption(pmcid: str, element_id: str) -> str | None:
    xml = fetch(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
        f"db=pmc&id={pmcid.removeprefix('PMC')}&rettype=xml&tool=cedalion",
        f"jats/{pmcid}.xml",
    )
    root = ET.fromstring(xml)
    for el in root.iter():
        if el.get("id") == element_id:
            label = el.find("label")
            caption = el.find("caption")
            if caption is None:
                return None
            title = caption.find("title")
            heading = " ".join(t for t in [text_of(label) if label is not None else "",
                                           text_of(title) if title is not None else ""] if t)
            paras = [text_of(p) for p in caption.findall("p")]
            if not (title is not None and text_of(title)) and not any(paras):
                return None  # a label without caption text is no caption
            out = [f"**{heading}**"] if heading else []
            out += paras
            return "\n\n".join(out) + "\n"
    return None


def write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))


def capture(entry: dict) -> str:
    work = crossref_work(entry["doi"])
    item = zotero_item(work, entry.get("pmcid"))
    key = item["citationKey"]

    paper_dir = ROOT / "papers" / key
    paper_dir.mkdir(parents=True, exist_ok=True)
    item_path = paper_dir / "item.yaml"
    if not item_path.exists():
        write_yaml(item_path, item)
    else:
        held = str((yaml.safe_load(item_path.read_text()) or {}).get("DOI") or "").strip().lower()
        if held and held != entry["doi"].strip().lower():
            raise ValueError(f"papers/{key} already holds another paper (DOI {held}); give this entry its own key")

    slug = slug_for(entry["kind"], entry["label"])
    scrap_dir = ROOT / "scraps" / key / slug
    scrap_dir.mkdir(parents=True, exist_ok=True)

    obj_path = scrap_dir / "object.yaml"
    existing = yaml.safe_load(obj_path.read_text()) if obj_path.exists() else {}
    image = scrap_dir / f"{slug}.jpg"
    if image.exists() and existing.get("files"):
        # Never replace a captured image: descriptions and palettes were read from it.
        if existing.get("contentUrl") != entry["contentUrl"]:
            raise ValueError(f"{key}/{slug}: contentUrl differs from the captured image's; "
                             f"delete {image.relative_to(ROOT)} to capture the new one")
        file_info = existing["files"][0]
    else:
        url = entry["contentUrl"]
        suffix = Path(urllib.parse.urlparse(url).path).suffix
        # Cached by URL, so a corrected contentUrl is downloaded rather than served the old image.
        name = f"assets/{key}/{slug}-{hashlib.sha256(url.encode()).hexdigest()[:12]}{suffix}"
        raw = fetch(url, name, check=lambda data: Image.open(io.BytesIO(data)).verify())
        file_info = store_image(raw, image)

    caption_source = None
    caption_path = scrap_dir / "caption.md"
    if entry.get("pmcid") and entry.get("jats_id"):
        caption = jats_caption(entry["pmcid"], entry["jats_id"])
        if caption:
            caption_source = {"type": "jats", "id": entry["pmcid"], "element": entry["jats_id"]}
            if not caption_path.exists():
                caption_path.write_text(caption)

    # Re-read object.yaml under the scrapbook lock so concurrent writers (e.g. archive-import)
    # cannot have their fields overwritten by a stale pre-network snapshot.
    lock = vaults.Lock(ROOT, "another run is writing this scrapbook")
    try:
        latest = yaml.safe_load(obj_path.read_text()) if obj_path.exists() else {}
        if not isinstance(latest, dict):
            latest = {}
        level0 = {
            "kind": entry["kind"],
            "label": entry["label"],
            "label_source": entry["label_source"],
            "paper": key,
            "url": entry["url"],
            "contentUrl": entry["contentUrl"],
            "accessDate": latest.get("accessDate") or dt.date.today().isoformat(),
            "rights": spdx_rights(vor_license(work)),
            "files": [file_info],
            "caption_source": latest.get("caption_source") or caption_source,
        }
        level1 = {k: v for k, v in latest.items() if k not in level0}
        text = yaml.safe_dump({**level0, **level1}, sort_keys=False, allow_unicode=True, width=120)
        vaults.replace(obj_path, text.encode("utf-8"))
    finally:
        lock.close()
    return f"{key}/{slug}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="capture only entries with this DOI")
    parser.add_argument("--scrapbook", type=Path, help="scrapbook folder (default: see tools/paths.py)")
    args = parser.parse_args()
    use_scrapbook(args.scrapbook)
    entries = yaml.safe_load((ROOT / "inbox.yaml").read_text())
    failures = 0
    for entry in entries:
        if args.only and entry["doi"] != args.only:
            continue
        try:
            print("ok  ", capture(entry))
        except Exception as exc:  # report and continue with the rest of the queue
            failures += 1
            print("FAIL", entry["doi"], entry["label"], f"{type(exc).__name__}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
