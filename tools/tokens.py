"""Read styles/cedalion.tokens.json (DTCG 2025.10) and write the Matplotlib sheets from it.

The token file is the source of the style sheets: each group under `sheet` becomes
styles/<name>.mplstyle, its nested group path becoming the rc key (sheet.default.axes.linewidth
-> axes.linewidth). A group of color tokens named prop_cycle becomes the color cycle. rc
settings with no DTCG type (booleans) sit in the group's $extensions under EXTENSION.
Lengths are DTCG dimensions (px or rem) and are written to the sheets in pt.

Color schemes that no installed library provides sit under `palette`; tools/color.py reads them.

Usage: python tools/tokens.py                 write styles/<sheet>.mplstyle
       python tools/tokens.py --check         exit 1 if a sheet differs from the tokens
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from tools.units import convert
except ImportError:  # run as python tools/tokens.py
    from units import convert


ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "styles/cedalion.tokens.json"
EXTENSION = "org.cedalion.matplotlib"  # rc settings without a DTCG type, copied as they are
ALIAS = re.compile(r"^\{([^{}]+)\}$")


def load(path: Path = TOKENS) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def tokens(tree: dict, prefix: tuple = (), inherited: str | None = None):
    """Yield (path, $type, $value, node) for every token, with group types inherited."""
    kind = tree.get("$type", inherited)
    for name, node in tree.items():
        if name.startswith("$") or not isinstance(node, dict):
            continue
        if "$value" in node:
            yield prefix + (name,), node.get("$type", kind), node["$value"], node
        else:
            yield from tokens(node, prefix + (name,), kind)


def resolve(tree: dict, value, seen: tuple = ()):
    """Follow a curly-brace alias to the target token's value."""
    match = ALIAS.match(value) if isinstance(value, str) else None
    if not match:
        return value
    path = match.group(1)
    if path in seen:
        raise ValueError(f"circular alias {' -> '.join(seen + (path,))}")
    node = tree
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"alias {value} names no token")
        node = node[part]
    if "$value" not in node:
        raise ValueError(f"alias {value} names a group, not a token")
    return resolve(tree, node["$value"], seen + (path,))


def problems(tree: dict) -> list[str]:
    """What breaks the DTCG rules this repository relies on."""
    found = []
    for path, kind, value, _ in tokens(tree):
        where = ".".join(path)
        if any(c in part for part in path for c in "{}."):
            found.append(f"{where}: names must not contain '{{', '}}' or '.'")
        if kind is None:
            found.append(f"{where}: no $type on the token or its groups")
        try:
            value = resolve(tree, value)
        except ValueError as e:
            found.append(f"{where}: {e}")
            continue
        if kind == "color":
            ok = (isinstance(value, dict) and value.get("colorSpace") == "srgb"
                  and len(value.get("components", ())) == 3
                  and all(isinstance(c, (int, float)) and 0 <= c <= 1 for c in value["components"]))
            if not ok:
                found.append(f"{where}: colors here are srgb with three components in 0–1")
            elif value.get("hex") and value["hex"].lower() != hex_of(value):
                found.append(f"{where}: hex {value['hex']} does not match components {hex_of(value)}")
        elif kind == "number" and not isinstance(value, (int, float)):
            found.append(f"{where}: a number token needs a JSON number")
        elif kind == "dimension" and not (isinstance(value, dict) and value.get("unit") in ("px", "rem")
                                          and isinstance(value.get("value"), (int, float))):
            found.append(f"{where}: a dimension is {{\"value\": number, \"unit\": \"px\" | \"rem\"}}")
    return found


def hex_of(color: dict) -> str:
    return "#" + "".join(f"{round(c * 255):02x}" for c in color["components"])


def palettes(tree: dict) -> dict[str, list[tuple[str, str]]]:
    """Each scheme under `palette` as (color name, hex) in its published order, keyed
    by its dotted path below `palette` ("tol.bright")."""
    out: dict[str, list[tuple[str, str]]] = {}
    for path, kind, value, _ in tokens(tree["palette"], inherited=tree["palette"].get("$type")):
        if kind == "color":
            out.setdefault(".".join(path[:-1]), []).append((path[-1], hex_of(resolve(tree, value))))
    return out


# --- Matplotlib sheets ------------------------------------------------------------------

def rc_value(value):
    """Dimensions in pt for Matplotlib; other values as they are."""
    if isinstance(value, dict) and "unit" in value:
        return f"{round(convert(value['value'], value['unit'], 'pt'), 3):g}"
    return value


def rc_lines(tree: dict, group: dict, prefix: tuple = ()) -> list[str]:
    lines = []
    if "$description" in group and prefix:
        lines += [f"# {line}" for line in group["$description"].splitlines()]
    for key, value in group.get("$extensions", {}).get(EXTENSION, {}).items():
        lines.append(f"{'.'.join(prefix + (key,))}: {value}")
    for name, node in group.items():
        if name.startswith("$") or not isinstance(node, dict):
            continue
        key = ".".join(prefix + (name,))
        if name == "prop_cycle":
            colors = [hex_of(resolve(tree, value))[1:] for _, _, value, _ in tokens(node)]
            lines += [f"# {line}" for line in node.get("$description", "").splitlines()]
            lines.append(f"{key}: cycler('color', {colors})")
        elif "$value" in node:
            lines += [f"# {line}" for line in node.get("$description", "").splitlines()]
            lines.append(f"{key}: {rc_value(resolve(tree, node['$value']))}")
        else:
            lines += rc_lines(tree, node, prefix + (name,))
    return lines


def sheets(tree: dict) -> dict[Path, str]:
    header = f"# Written by tools/tokens.py from {TOKENS.relative_to(ROOT).as_posix()}; edit the tokens, not this file."
    out = {}
    for name, group in tree["sheet"].items():
        if name.startswith("$"):
            continue
        body = [f"# {line}" for line in group.get("$description", "").splitlines()]
        out[ROOT / "styles" / f"{name}.mplstyle"] = "\n".join([header, *body, *rc_lines(tree, group)]) + "\n"
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit 1 if a sheet differs from the tokens")
    args = parser.parse_args(argv)

    tree = load()
    found = problems(tree)
    for p in found:
        print(f"ERROR {TOKENS.relative_to(ROOT).as_posix()}: {p}", file=sys.stderr)
    if found:
        return 1

    stale = []
    for path, text in sheets(tree).items():
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            continue
        stale.append(path)
        if not args.check:
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT).as_posix()}")
    if args.check:
        for path in stale:
            print(f"ERROR {path.relative_to(ROOT).as_posix()} differs from the tokens; run python tools/tokens.py",
                  file=sys.stderr)
        return 1 if stale else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
