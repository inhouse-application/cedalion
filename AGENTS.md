# AGENTS.md

Rules for any coding agent that edits this repository. `CLAUDE.md` imports this file.

## Papers and scraps

These live in the scrapbook: this folder when it holds `scraps/`, else the folder named in `.cedalion-scrapbook` (`tools/paths.py`). A scrapbook in its own folder has its own `AGENTS.md` with these rules; `templates/`, `vocab/` and the tools stay here.

Each paper has a folder `papers/<citationKey>/`. Each figure, table or media item from it has a folder `scraps/<citationKey>/<slug>/`. `templates/` shows the fields of each file, and `vocab/` lists the terms you may use. To add a chart, element or domain term, give its common name (as people search for it) and a one-line definition.

In a scrap:

- `object.yaml` records the source, license, files and panels. Archive or unarchive a scrap in Tolaria and run `pixi run archive-import --vault <folder>`; do not edit `archived:` by hand.
- `caption.md` is the caption copied verbatim from JATS XML or the PDF named in `caption_source`. Prefer the version of record; for a manuscript or preprint, record its version and URL. Leave the file out until you have the source.
- `description.md` says what is drawn and with which values, following `docs/description.md`. No trends, causes or judgments.
- `palette.yaml` lists the colors of legends and color bars. Mark a pixel for each with `at` and let `python tools/palettes.py` fill in the hex.
- In `context.yaml` files, give a text location for each value, or write `not stated`.
- `notes.md` is the owner's. Do not write it.

`docs/sources.md` explains where files come from and how they may be reused; `docs/levels.md` explains levels.

## Snippets and styles

Add a snippet when an element appears in two scraps or the owner asks for one. Its title is the term's name from `vocab/`, optionally after a variant name ("Split violin plot"). It draws synthetic data, runs on its own and writes `snippet.png` next to itself. Its `about:` lists the chart and element terms drawn in `snippet.png`, its own term first. Run `python tools/render_snippets.py` after changing one.

The sheets in `styles/` are written from `styles/cedalion.tokens.json`: edit the tokens and run `python tools/tokens.py`.

## Commits

Run `python tools/check.py` before committing. Leave out `Co-Authored-By` trailers and "Generated with" lines.
