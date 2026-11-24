# Sources and processing

How objects, captions and body citations get into the scrapbook, which routes are allowed, and which tools process them.

## Where each part comes from, in order of preference

| Part | 1st choice | 2nd choice | 3rd choice |
|---|---|---|---|
| Paper metadata | Zotero item (owner's library) | Crossref (`tools/add_scrap.py`) | — |
| Image | Publisher's full-size web image (Springer `full/`, Elsevier `_lrg`) | Native raster extracted from the PDF | Vector crop of the PDF region, rendered for review |
| Caption | JATS XML from PubMed Central | PDF, version of record | PDF, accepted manuscript or preprint (recorded as such) |

A caption from an accepted manuscript or preprint can differ from the published text; `version` records which one was used.

## Getting the files

Allowed:

- **PubMed Central JATS** through NCBI E-utilities (`efetch`, `db=pmc`). Full text is available only for articles PMC may redistribute; for others PMC returns front matter only.
- **Open-access copies**: the publisher's own open-access PDF, author or institutional repositories, and other copies of articles under an open license. Look them up with OpenAlex (`https://api.openalex.org/works/doi:<DOI>`, no key needed; see `open_access` and `locations`).
- **Institutional access by the owner**: the owner downloads the PDF through Zotero or a browser on the university network and places it in `.cache/pdf/`. Agents may use a Zotero plugin or a download helper the owner has set up.

Not allowed:

- Scripted downloads from publisher sites that pose as a browser, or any attempt to get past CAPTCHA or bot-protection pages.
- Shadow libraries (Sci-Hub, LibGen, Anna's Archive and similar).
- Credentials the owner has not given.

When a PDF cannot be obtained this way, the scrap stays without a caption; record the failure in the task report.

## Storing PDFs

- `.cache/pdf/<citationKey>.pdf`, git-ignored. PDFs are never committed.
- Next to it, `<citationKey>.yaml` with the provenance that `tools/captions_from_pdf.py` copies into each record:

  ```yaml
  version: vor            # vor | accepted-manuscript | preprint
  url: https://doi.org/…  # where the PDF was obtained
  ```

- Each record also stores the PDF's SHA-256, so a later copy can be checked against it.
- A supplement PDF is stored as `<citationKey>.supplement.pdf` with its own `<citationKey>.supplement.yaml`.
  `tools/captions_from_pdf.py` reads captions for labels numbered `S…` (Figure S16) from it, and all other labels from `<citationKey>.pdf`.

## Supplementary figures

- A figure from a supplement is a scrap of the same paper: `scraps/<citationKey>/fig-s<N>/`, `label` as printed (`Figure S16`), `label_source: pdf`.
- `url` and `contentUrl` are the supplement PDF's URL. The image is the figure's native raster extracted from that PDF (`files[].source_sha256` is the hash of the extracted bytes).
- `rights` comes from the supplement's own license statement, which can differ from the article's.
- Captions are read from the supplement PDF.

## Processing commands

Run from the repository root. PDF tools need PyMuPDF and the PDFFigures2 locator (see `README.md`, Requirements).

| Step | Command | Writes | Checked by |
|---|---|---|---|
| Capture | `python tools/add_scrap.py` | `papers/*/item.yaml`, image, `object.yaml` Level 0, JATS captions | `tools/check.py` |
| Captions from PDF | `python tools/captions_from_pdf.py` | `caption.md`, `caption_source` | visual check of each new caption |
| Validate | `python tools/check.py` | — | — |

What each PDF tool does:

- **Captions**: PDFFigures2 finds the caption region and PyMuPDF reads its characters from the PDF, so dashes and quotes stay as printed. PDFFigures2 misses supplementary labels such as "Figure S16:"; for those the extractor reads the one paragraph that opens with the label. Check every caption it prints against the printed page.
- **Figure boxes** are not used in production.

## Rights

Every object records its license in `object.yaml` (`rights`: an SPDX id, `LicenseRef-publisher` or `NOASSERTION`).
Objects that are not openly licensed are kept for private reference only; a scrapbook that holds them stays private.
