# Standards

Published standards this repository follows.

## Used

| Standard | Used for | Notes |
|---|---|---|
| [Zotero schema](https://github.com/zotero/zotero-schema) (schema version 45) | Field names in `papers/*/item.yaml`; `dataset` field names for data entries in `context.yaml` | `citationKey` is a native Zotero field. Zotero has no figure item type, so objects link to papers by `citationKey` rather than being Zotero items |
| Better BibTeX default citation key `[auth:lower][shorttitle3_3][year]` | `citationKey` until a Zotero export replaces it | Replace keys from Zotero when the owner's formula differs |
| [JATS Tag Library 1.4](https://jats.nlm.nih.gov/publishing/tag-library/1.4/) | `kind` terms (`fig`, `table-wrap`, `media`, …); `label`, `caption`; `alt-text` and `long-desc` section names; captions extracted from PMC JATS XML | `long-desc` is allowed on fig, graphic, media, supplementary-material and table-wrap |
| [SPDX license identifiers](https://spdx.org/licenses/) | `rights` in `object.yaml` (`CC-BY-4.0`, `LicenseRef-publisher`, `NOASSERTION`) | |
| Creative Commons TASL attribution (Title, Author, Source, License) | Credit lines when an open-licensed object is shown outside the repository | |
| Lundgard & Satyanarayan four-level model; W3C WAI complex-image guidance | Scope of `description.md` (S1–S2 only) | |
| ISO 8601 | Dates | |
| [STAC 1.1.0](https://stacspec.org/) field names | `start_datetime`, `end_datetime` in `context.yaml` | Names only; no STAC catalog |
| `AGENTS.md` convention | Agent rules, imported by `CLAUDE.md` | |
| [Citation File Format](https://citation-file-format.github.io/) | `CITATION.cff` | |
