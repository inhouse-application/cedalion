# Cedalion for Zotero 10

Use **Send to Cedalion** to save a paper's metadata and a local PDF attachment in your Cedalion scrapbook. If you already have `cedalion.xpi`, start with installation.

## Build the plugin

With Pixi installed, run these commands from the repository root. Run the first command once to install the locked dependencies. The second builds the plugin offline and can be repeated for updates.

```sh
pixi run -e plugin npm --prefix zotero-plugin ci
pixi run -e plugin npm --prefix zotero-plugin run build
```

The installable file is `zotero-plugin/dist/cedalion.xpi`.

## Install and choose a scrapbook

1. In Zotero 10, open **Tools → Plugins**. Open the gear menu, choose **Install Plugin From File…** and select `cedalion.xpi`.
2. Open **Settings → Cedalion → Choose folder…** and select your scrapbook: the folder named in `.cedalion-scrapbook` in your Cedalion folder (the `orion` clone when the installer set it up), or the Cedalion folder itself when it holds `scraps/`. It must contain the file `AGENTS.md`, the directory `papers/` and the file `vocab/domain.yaml`. If a check fails, the summary identifies the problem and the command writes nothing.

Once installed, Zotero checks `https://github.com/inhouse-application/cedalion/releases/latest/download/updates.json` for newer releases and installs updates with SHA-256 verification. You can also install updates from file at any time.

## Send papers

Select one or more parent paper items in your Zotero library, right-click the selection and choose **Send to Cedalion**. Notes and attachments selected alongside the papers are counted as skipped. For each paper, the plugin uses Zotero's preferred attachment when it is a local PDF. Otherwise it chooses the earliest-added local PDF.

Metadata goes in `papers/<key>/item.yaml`. The PDF goes in `.cache/pdf/<key>.pdf`. Beside it, `<key>.yaml` records the attachment's source URL and, when recognized, its version. If the attachment has no URL, or its URL has a query string (signed download links such as ScienceDirect's expire and carry session tokens; others carry tracking parameters), the plugin uses a DOI link. If a skipped Zotero item also lacks a DOI, it looks up the DOI in the existing repository record.

A PDF attachment whose title or file name contains "supplement" is never used as the paper's PDF. The earliest-added local one goes in `.cache/pdf/<key>.supplement.pdf`, under the same rules as the paper's PDF, with its own `<key>.supplement.yaml`. That file records the attachment's URL only when it has one without a query string, because the DOI identifies the article, not the supplement. Otherwise the summary asks you to **set supplement URL by hand**; likewise **set supplement version by hand** when the title does not identify the version. The summary's **Supplement** result is **copied**, **already present**, **conflict**, **supplement PDF not downloaded** or **none**.

## Filling PDFs for papers already in the repository

Select those papers in Zotero and choose **Send to Cedalion**. The summary reports `item.yaml` as **duplicate** or **skipped**. The plugin copies each available PDF under the existing repository key. If a PDF is still on WebDAV, download it through Zotero and send the paper again.

## Read the summary

Each selected item has a row with its key, metadata result, PDF result and any warnings. The `cedalion` tag means the paper's metadata is in the repository. A missing PDF or a PDF conflict still allows the tag. A metadata, PDF I/O or provenance-file error prevents the plugin from adding the tag on that attempt.

| Metadata result | Meaning |
|---|---|
| **written** | The plugin created a new `item.yaml`. |
| **skipped** | A record already occupies that citation key. For a selected note or attachment, the row instead identifies it as skipped. |
| **duplicate (already in repository as …)** | The DOI matches an existing record, ignoring case. The key in parentheses is the one used for the PDF. |
| **error** | The plugin could not process the metadata. Read the reason on the row, correct it and send the item again. |

| PDF result or warning | Meaning |
|---|---|
| **copied** | The plugin created the cached PDF. |
| **already present** | The cached and selected files have the same SHA-256 hash. The plugin fills in a missing provenance file. |
| **conflict (different SHA-256)** | The cached PDF differs from the selected attachment. The plugin keeps the cached PDF and its provenance as they are, even if the provenance file is absent. |
| **no local PDF** | The paper has no eligible PDF attachment. A web link or HTML snapshot does not qualify. |
| **PDF not downloaded** | Zotero lists a PDF attachment whose file is missing locally. Download it in Zotero and send the paper again. This can also appear as a warning when another local PDF was used. |
| **set version by hand** | The attachment title did not identify the version. Check the source and, if needed, set `version` in the provenance file to `vor` (version of record), `accepted-manuscript` or `preprint`. |
| **skipped** or **not attempted** | The selection was a note or attachment, or an earlier error prevented PDF processing. |
| **PDF error**, **Sidecar error** or **Tag error** | The row identifies which step failed. Correct the issue and send again. A retry can use files already written successfully. |

An **Unparsed date** warning means the metadata retains the original Zotero date text.

## Local operation

The installed plugin runs only when you choose the menu command. Its own code makes no network requests (only Zotero's built-in add-on updater fetches `updates.json`), runs no external programs (including Git or Python), and never edits `inbox.yaml`. Its repository writes are limited to `papers/` and `.cache/pdf/`. It never overwrites an existing metadata file, PDF or provenance file.
