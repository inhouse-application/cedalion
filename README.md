# Cedalion

*(pronounced seh-DAY-lee-on; Greek Κηδαλίων, Kēdalíōn)*

Tools and plotting snippets for people and coding agents who draw scientific figures, used with a scrapbook of the non-text parts of published papers (figures, tables, media).
Each object in the scrapbook is captured with its source and license and is described plainly. Plotting snippets for elements that recur are kept here.

## Installing

Run the command for your system to install or update Cedalion.

**macOS / Linux**

```sh
bash -o pipefail -c 'curl -fsSL https://github.com/inhouse-application/cedalion/releases/latest/download/install.sh | sh'
```

**Windows (PowerShell)**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -c "irm -UseBasicParsing -ErrorAction Stop https://github.com/inhouse-application/cedalion/releases/latest/download/install.ps1 | iex"
```

Lab members using the private scrapbook: [Connect `orion`](docs/integrations.md#connect-orion).

<details>
<summary>Install options</summary>

- **Default folder**: `~/cedalion` (macOS/Linux) or `%USERPROFILE%\cedalion` (Windows). Set `CEDALION_INSTALL_DIR` (or pass a folder path to the script) to choose another folder.
- **Unregister skill links**: run `install.sh --unregister [folder]` or `install.ps1 -Unregister [folder]`.
- **macOS without Command Line Tools**: run `xcode-select --install` first.

</details>

## About the name

**The myth.** The giant hunter Orion was blinded and told that the rays of the rising sun would restore his sight.
On Lemnos the smith-god Hephaestus lent him his apprentice Cedalion as a guide.
Orion carried Cedalion on his shoulders, and from there the boy directed the giant eastward until his sight returned.
Nicolas Poussin painted the scene in *Blind Orion Searching for the Rising Sun* (1658, The Metropolitan Museum of Art).

**The phrase.** In the twelfth century Bernard of Chartres said that we are like dwarfs sitting on the shoulders of giants:
we see more and farther than they did, not because our sight is sharper, but because their stature lifts us up.
The saying survives through John of Salisbury's *Metalogicon* (1159): *nanos gigantum humeris insidentes*.
Isaac Newton used it in a 1675/76 letter to Robert Hooke: "If I have seen further it is by standing on ye sholders of Giants."
Robert K. Merton traced this lineage in *On the Shoulders of Giants* (1965).

## Contents

| Path | Holds |
|---|---|
| `snippets/<category>/<id>/` | Runnable plotting snippet for one element, its rendered output and a short note |
| `vocab/` | Controlled terms for kind, role, chart and element |
| `templates/` | Blank copy of every scrapbook and snippet file |
| `docs/` | Standards used, levels, description rules; where files come from and how they are processed (`sources.md`), Zotero and Tolaria (`integrations.md`) |
| `tools/` | Capture, checks, snippet rendering, Tolaria cards |
| `install/` | Installers for macOS and Linux (`install.sh`) and Windows (`install.ps1`), and their tests |
| `zotero-plugin/` | Zotero 10 plugin: right-click **Send to Cedalion** writes `papers/<citationKey>/item.yaml` and copies the PDF into `.cache/pdf/` of the scrapbook ([README](zotero-plugin/README.md)) |

The scrapbook holds the examples:

| Path | Holds |
|---|---|
| `papers/<citationKey>/` | `item.yaml`: paper metadata with Zotero field names. `context.yaml`: paper-level 5W2H (Level 2) |
| `scraps/<citationKey>/<slug>/` | One object: image file, `object.yaml`, `caption.md`, `description.md`, `palette.yaml`, `context.yaml`, `notes.md` |
| `vocab/domain.yaml` | Subject domains of papers |
| `inbox.yaml` | Objects waiting to be captured |

It is this folder when it holds `scraps/`, or a separate folder. The tools find it in this order: `--scrapbook PATH`, `$CEDALION_SCRAPBOOK`, the path written in `.cedalion-scrapbook` here (the installer writes it), this folder. Without a scrapbook, the checks and snippets work on this folder alone.

Scraps are described in levels by how they can be checked: 0 captured, 1 described, 2 contextualized, 3 interpreted.
See [`docs/levels.md`](docs/levels.md).

## Using it

Run the commands inside the pixi environment (`pixi shell`, or prefix each with `pixi run`).

```sh
python tools/add_scrap.py          # capture everything in inbox.yaml (Level 0, and captions where JATS is available)
python tools/captions_from_pdf.py  # extract missing captions from .cache/pdf/<citationKey>.pdf (requires PyMuPDF and PDFFigures2)
python tools/palettes.py <palette.yaml>  # fill palette hex values from the pixels named in `at`; list matching color schemes
python tools/palettes.py --subsets scraps/<citationKey> [--apply]  # legends that use some colors of a scheme used elsewhere in the paper
python tools/tokens.py             # write styles/*.mplstyle from styles/cedalion.tokens.json (DTCG)
python tools/units.py 7pt px       # convert lengths between pt, px, rem, mm and in
python tools/color.py view okabe_ito [--out out.png]  # colors under normal vision, deuteranopia and protanopia
python tools/flint.py <script.py> [--measure] [--json]  # text boxes outside the saved area; --measure adds sizes, contrast and legend color distances
python tools/check.py              # validate files, vocabulary and palette colors; print each scrap's level
python tools/render_snippets.py    # run every snippet and refresh its PNG
```

Snippets use `styles/default.mplstyle` at 183 mm. To preview all snippets in a separate folder, run
`pixi run render-snippets --style elsevier --width 190 --out /tmp/cedalion-preview` from the repository root.
For a single `snippet.py`, set `CEDALION_STYLE` to a sheet name in `styles/` or a file path and `CEDALION_WIDTH_MM` to the finished width in millimeters.

## PDF captions

PDFs live in the scrapbook's `.cache/pdf/`, outside git, each with a sibling YAML file giving its `version` and source `url` (see [`docs/sources.md`](docs/sources.md)). Existing scraps already carry their captions. To extract new ones, build the locator once and run the extractor:

```sh
export CEDALION_TOOLS="$HOME/.local/share/cedalion-tools"
pixi run -e pdf python tools/bench/install_java.py --pdffigures2-only
pixi run -e pdf python tools/captions_from_pdf.py --pdf-dir /path/to/pdf-cache
```

Check line-end hyphens the extractor prints.

Agents start at [`SKILL.md`](SKILL.md). Rules for agents editing these files are in [`AGENTS.md`](AGENTS.md).

## Rights

The tools, snippets, styles, vocabularies, templates and documentation here are under the MIT License (`LICENSE`).
Captured images, captions and tables in a scrapbook remain under their publishers' licenses, recorded per object in `object.yaml` (`rights`).
Objects marked `LicenseRef-publisher` or `NOASSERTION` are kept for private reference only and must not be redistributed;
keep a scrapbook private unless every object in it carries an open license.
