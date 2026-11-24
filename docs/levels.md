# Levels

A scrap's level says how far its text goes beyond what can be checked against the source.
Levels are cumulative and are derived by `tools/check.py` from the files present; no file records them.

| Level | Name | Adds | Checked against | Written by |
|---|---|---|---|---|
| 0 | captured | `papers/<key>/item.yaml`, `object.yaml` Level 0 fields, the image file | Download and Crossref/Zotero record | `tools/add_scrap.py` |
| 1 | described | `caption.md`, `description.md`, `object.yaml` `layout` and `panels` (each panel with at least one `chart` term) | The image and the caption | Agent; owner skims |
| 2 | contextualized | `context.yaml` in the scrap and `papers/<key>/context.yaml`; every value has a `loc` such as `Results ¶3`, or is `not stated` | The paper's text | Agent, with locations |
| 3 | interpreted | `notes.md` | Nothing; it is judgment | Owner only |

`palette.yaml` (the colors of each legend or color bar, sampled from the image) is optional in the same way; `tools/check.py` compares every recorded color with the image.
It is mechanical evidence for Level 2: Level 2 values may cite its entries as their location.

Every object should reach Level 1. Raise an object to Level 2 or 3 only when it is needed.

A scrap without a verbatim caption source stays at Level 0 even if `description.md` exists;
`tools/check.py` reports it as `0 (+description)` so the missing caption is visible.
