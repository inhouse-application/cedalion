# Integrations

How Cedalion connects to Zotero and to Tolaria.

## Zotero

### Citation keys

`papers/<citationKey>/` uses Better BibTeX keys. Better BibTeX documents its default as
"`auth.lower + shorttitle(3,3) + year`" ([citing](https://retorque.re/zotero-better-bibtex/citing/index.html)),
which `tools/add_scrap.py` imitates when it builds `item.yaml` from Crossref.
If the owner's Zotero key for a paper differs, the Zotero key wins: rename the directories and the `paper`/`citationKey` fields to match.

### Three ways to read the library

| Route | Where it runs | What it gives | Notes |
|---|---|---|---|
| **Local API** `http://localhost:23119/api/` | On the computer running Zotero desktop | Items, collections, and attachment files: `/items/<itemKey>/file` "returns a `302` redirect to a `file://` URL for the attachment on disk" | Enable in Settings → Advanced → "Allow other applications on this computer to communicate with Zotero"; otherwise `403 Forbidden`. The docs say "Do not forward the port or otherwise expose it externally." Not reachable from the analysis server. ([local API](https://www.zotero.org/support/dev/web_api/v3/local_api)) |
| **Web API** `https://api.zotero.org` | Anywhere, including the analysis server | Items as JSON (`/users/<userID>/items`, `/collections/<collectionKey>/items`); attachment files via `/users/<userID>/items/<itemKey>/file` | Key in the `Zotero-API-Key` header, created at zotero.org → Settings → Keys. Whether `/file` serves attachments synced by WebDAV or linked files is not documented; Zotero Storage attachments are. ([basics](https://www.zotero.org/support/dev/web_api/v3/basics), [files](https://www.zotero.org/support/dev/web_api/v3/file_upload)) |
| **Better BibTeX automatic export** | On the computer running Zotero desktop | A BibTeX/BibLaTeX (or JSON) file kept up to date: "any changes to the collection or library will trigger an automatic re-export" | Can be written into a git working copy and pushed. Attachment paths in exports are not documented. ([auto-export](https://retorque.re/zotero-better-bibtex/exporting/auto/index.html)) |

### Workflow

1. In Zotero, select papers, right-click and choose **Send to Cedalion** (`zotero-plugin/`). There is no collection watching. The plugin reads local PDF files, so it uses the local route; the Web API is not used.
2. The plugin writes `papers/<citationKey>/item.yaml` (Zotero `citationKey` field, else the `tools/add_scrap.py` rule; only tags in `vocab/domain.yaml`; never overwrites; same DOI → reported as duplicate), copies the local PDF to `.cache/pdf/<key>.pdf` with its provenance file, and tags the item `cedalion`.
3. A paper with `item.yaml` but no `scraps/<citationKey>/` is waiting to be captured; choosing its figures and running `tools/` stays with the owner and agents.

Lab sharing means sharing paper lists, e.g. through a Zotero group library; images stay in the scrapbook.

## Tolaria

[Tolaria](https://github.com/refactoringhq/tolaria) is a desktop editor for folders of markdown notes. Cedalion keeps its data in nested YAML files, so `pixi run cards --vault <folder>` (`tools/cards.py`) writes a separate vault of cards outside the tool folder and the scrapbook: one note per paper, scrap, snippet, vocabulary term and colormap, with images copied into `assets/`, and links between them (`belongs_to`, `related_to`, `has`).

Open that vault in Tolaria, not the source folders: Tolaria writes view state into note frontmatter and hides git-ignored files. The cards are generated, so do not edit or commit them. With `git config core.hooksPath "$PWD/tools/git-hooks"`, git rewrites the vault after each commit, merge, pull, checkout or rebase. For a scrapbook in its own clone, set the same `core.hooksPath` (the hooks folder of the Cedalion clone) there too; the hooks then build from that clone. `cards` only reads the sources and never writes the scrapbook; a new scrap card starts with `_archived: true` when its `object.yaml` says `archived: true`, and when the vault and `object.yaml` differ, `cards` distinguishes scraps newly archived in the scrapbook (`--sync-from-book` to pull those marks into the vault) from local archive changes.

Only one designated owner vault writes `archived: true` back to a shared scrapbook: designate it once with `pixi run archive-import --vault <folder> --set-owner` (which records the vault ID in `.cedalion-archive-owner` in the scrapbook and binds it on that machine), then commit `.cedalion-archive-owner`. Thereafter, `pixi run archive-import --vault <folder>` (`tools/archive_import.py`) copies new archive marks into `object.yaml`; removing an existing `archived: true` always requires explicit confirmation with the token printed by the dry run (`--confirm-unarchive <token>`). Non-owner vaults keep their `_archived` marks local in Tolaria. The vault's `.cedalion-cards` records the bytes the tool last wrote to each card and image. A file it did not write, or one changed since (other than view keys starting with `_` that Tolaria adds, which are carried over), is never overwritten or removed: if the run would, it stops and writes nothing. A vault from an older Cedalion (a manifest without hashes) is not overwritten in place; `pixi run cards --from <old-vault> --vault <new-vault>` builds a new vault carrying over only its `_` values and your personal files.

Lab contributions to the shared scrapbook are validated with `pixi run check-contribution` (`tools/check_contribution.py`), which checks that a branch only adds new papers/scraps (and appends to `vocab/domain.yaml`), follows the Better BibTeX default `citationKey` rule (`auth.lower + shorttitle(3,3) + year`), omits personal `notes.md`, `archived:` flags, and `.cache/` PDFs, and reaches at least Level 1 with zero `tools/check.py` errors.
