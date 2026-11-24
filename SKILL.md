---
name: cedalion
description: Figures, tables and maps from published papers, with plain descriptions, and matplotlib snippets for drawing their elements. Use when choosing a chart type or map layout, drawing or reviewing a scientific figure, or looking for an element such as an inset zoom, a shared color bar or group brackets.
---

# Cedalion

Paths below start in the folder that contains this file.

Before drawing, find out what each observation or cell of the data is, its units, and what the reader should compare.

Examples are in the scrapbook: this folder when it holds `scraps/`, else the folder whose path is written in `.cedalion-scrapbook` here (a relative path starts here). If there is neither, use the snippets alone. To find examples, search the scrapbook's `scraps/*/*/object.yaml` for a chart or element term from `vocab/` (for example `grep -rl inset-zoom <scrapbook>/scraps/*/*/object.yaml`), or search `tags` in its `papers/*/item.yaml` for a topic. Skip scraps whose `object.yaml` says `archived: true`. In a scrap, read `description.md` and look at the image listed in `object.yaml`. Read `notes.md` when it exists: it holds the owner's preferences. Read the caption or the paper's context only when the task needs the source's wording or science.

To draw, find the technique in `snippets/<category>/<id>/` and take the code you need into your own project. Render the figure and check its axes, units and values against the data. `python tools/flint.py <script.py>` lists text that falls outside the saved image; add `--measure` for text sizes, contrast and color distances.

When you cite an example, name the paper and the figure or table. Reproduce an image or caption outside Cedalion only when its `rights` in `object.yaml` allow it. To edit these files or the scrapbook, follow the `AGENTS.md` in that folder.
