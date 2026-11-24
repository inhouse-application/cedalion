"""Convert lengths between pt, px, rem, mm and in.

CSS fixes 1 in = 96 px = 72 pt, and 1 rem = 16 px unless the root font size is changed.
DTCG dimensions allow only px and rem; Matplotlib wants pt; journals give widths in mm.

Usage: python tools/units.py 7pt px      -> 9.3333px
       python tools/units.py 183mm in
"""

import re
import sys

PER_INCH = {"in": 1, "pt": 72, "px": 96, "rem": 6, "mm": 25.4}  # rem: 96 px / 16 px


def convert(value: float, source: str, target: str) -> float:
    return value / PER_INCH[source] * PER_INCH[target]


def parse(text: str) -> tuple[float, str]:
    match = re.fullmatch(r"\s*(-?[\d.]+)\s*([a-z]+)\s*", text)
    if not match or match.group(2) not in PER_INCH:
        raise ValueError(f"{text!r}: expected a number and one of {', '.join(PER_INCH)}")
    return float(match.group(1)), match.group(2)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in PER_INCH:
        print(__doc__.strip().splitlines()[-2].strip(), file=sys.stderr)
        return 2
    value, source = parse(argv[0])
    print(f"{round(convert(value, source, argv[1]), 4):g}{argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
