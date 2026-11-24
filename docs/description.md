# Writing `description.md`

`description.md` has two sections, named after the JATS accessibility elements:

- **alt-text**: one sentence naming the kind of graphic and what it displays.
- **long-desc**: one bullet per panel, in panel order, using the panel ids in `object.yaml`.
  When panels carry no printed letters, number them `p1`, `p2`, … in reading order;
  one line before the bullets may state this and give the encoding the panels share.

## Scope: encodings and values only

Descriptions stay at the first two levels of Lundgard and Satyanarayan's model of chart descriptions
(*Accessible Visualization via Natural Language Descriptions: A Four-Level Model of Semantic Content*, IEEE TVCG 2022):

| Level | Content | Here |
|---|---|---|
| S1 elemental | Chart type, axes, encodings, scales, legends, panel layout | Yes |
| S2 statistical | Values readable from the graphic: ranges, extremes, labeled numbers | Yes |
| S3 perceptual | Trends, patterns, comparisons ("increases", "higher in the north") | No (Level 3, `notes.md`) |
| S4 contextual | Domain meaning, causes, significance | No (Level 2 quotes, Level 3 notes) |

Write what is drawn, not what it means. Avoid words that rank or judge: *clear, strong, striking, notable, interesting, effectively*.

## Per panel

State, as applicable:

- chart type (term from `vocab/chart.yaml`)
- x and y: variable, unit, range, scale (linear, log)
- color, size, shape: variable and legend breaks or range; colormap type (sequential, diverging, categorical, cyclic)
- map: extent, projection if stated, inset and its outline
- other marks: reference lines, bands, annotations, labels printed in the panel
- shared elements: a color bar or legend used by several panels

Copy printed text (axis titles, legend labels, panel titles) exactly as printed.
If a value cannot be read from the image, leave it out rather than estimate it.

## By kind

- **fig**: as above.
- **table-wrap**: rows and columns (count and header text), units, footnote markers. If transcribed, put the data in `<slug>.csv` next to the image.
- **media**: duration, frame content, what changes over time as drawn (not what it means). Store a representative frame as the image.
- **supplementary-material**: file names, formats and sizes only.
