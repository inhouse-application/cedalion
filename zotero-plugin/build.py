"""Package only the Zotero runtime files at the root of the XPI.

The same inputs give the same bytes: entries go in a fixed order with a fixed
date, mode and host system, so the file times of a checkout do not reach the XPI.
"""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent


def add(archive, source, name):
    entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.create_system = 3  # Unix, so the mode below is read on every platform
    entry.external_attr = 0o100644 << 16  # regular file, rw-r--r--
    entry.compress_type = ZIP_DEFLATED
    archive.writestr(entry, source.read_bytes())


def main() -> None:
    addon = ROOT / "addon"
    output = ROOT / "dist" / "cedalion.xpi"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w") as archive:
        library = ROOT / "node_modules" / "js-yaml"
        add(archive, library / "dist" / "js-yaml.js", "vendor/js-yaml.js")
        add(archive, library / "LICENSE", "vendor/js-yaml.LICENSE")
        files = (path for path in addon.rglob("*") if path.is_file())
        for name, path in sorted((path.relative_to(addon).as_posix(), path) for path in files):
            add(archive, path, name)
    print(output.relative_to(ROOT.parent))


if __name__ == "__main__":
    main()
