"""Copy archive marks set on scrap cards in Tolaria (`_archived`) into the scrapbook's object.yaml files.

Each value has one place where it is changed and one direction (see tools/vault.py):
  Tolaria's archive button sets `_archived: true` on a scrap card, and removes `_archived` to unarchive it.
  Only the single owner vault registered for a scrapbook (both in the scrapbook's `.cedalion-archive-owner`
  and in the local owner binding file outside the vault) may update `object.yaml`; every other vault,
  including a copy of the owner vault, is a reader.

Before writing anything, this command reads the scrapbook whole (tools/index.py) and reads each scrap's
card once (checking origin, front matter and manifest hash on the same bytes). Scraps whose `object.yaml`
changed upstream (`book_changed`) are never written back; cards that would clear an existing
`archived: true` always stop with their list and a plan-bound `--confirm-unarchive <token>` tied to the
exact card hashes, object.yaml hashes, agreed checkpoints and owner binding.

After writing, both the scrapbook and the vault are read again and compared; exit 0 is returned only when
every applied change matches on both sides at completion, and the verified `agreed` checkpoint is updated
only for scraps where both sides agree.

Usage:
  python tools/archive_import.py --vault PATH [--scrapbook PATH] [--set-owner]
                                 [--confirm-unarchive TOKEN]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import index
import vault as vaults
from paths import TOOL_ROOT, for_command


def set_archived(source: str, archived: bool) -> str:
    """SOURCE (an object.yaml text) with its top-level `archived:` line set or removed."""
    body = re.sub(r"^archived:[ \t]*.*\n?", "", source, flags=re.M).rstrip("\n") + "\n"
    return body + ("archived: true\n" if archived else "")


def read_one_card(vault: Path, manifest: vaults.Manifest, scrap: index.Scrap, item: dict,
                  book: Path | None) -> tuple[bool, str] | str:
    """Read, parse and verify a single scrap card from one byte read. Returns (archived, card_sha256)
    or an error string."""
    name = f"{scrap.paper}-{scrap.slug}.md"
    rel = f"scraps/{scrap.paper}/{scrap.slug}"
    path = vault / name
    data, why = vaults.look(vault, name)
    if data is None:
        return f"{path}: {why or 'card is missing from the vault'}"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return f"{path}: does not read as UTF-8"
    split = vaults.view_lines(text)
    if split is None:
        return f"{path}: its front matter does not close, or its `_` keys do not parse"
    rest, user = split
    meta, body, error = index.front_matter(rest)
    if error or not isinstance(meta, dict):
        return f"{path}: {error or 'missing YAML front matter'}"
    folder_line = f"- Folder: `{rel}/`"
    if (meta.get("type") != "Scrap" or meta.get("belongs_to") != f"[[{scrap.paper}]]"
            or meta.get("paper_title") != item.get("title") or meta.get("label") != scrap.obj.get("label")
            or folder_line not in body.splitlines()):
        return f"{path}: is not the card of {rel} from {book}"
    if manifest.version in vaults.READ:
        seen = vaults.state_bytes(name, data, manifest.records.get(name))
        if seen.state not in ("written", "user"):
            return f"{path}: {seen.why}"
    elif name not in set(manifest.older or ()):
        return f"{path}: is not listed in {vault / vaults.MANIFEST}"
    values = vaults.view_values(user)
    if vaults.ARCHIVED in values and not isinstance(values[vaults.ARCHIVED], bool):
        return f"{path}: {vaults.ARCHIVED} must be true or false"
    return values.get(vaults.ARCHIVED) is True, vaults.sha(data)


def read_marks(vault: Path, manifest: vaults.Manifest,
               found: index.Sources) -> dict[tuple[str, str], tuple[bool, str]]:
    """Each scrap's `(paper, slug) -> (archived, card_sha256)` read from VAULT in one byte read per card."""
    papers = {p.key: p.item for p in found.papers}
    marks: dict[tuple[str, str], tuple[bool, str]] = {}
    problems: list[str] = []
    for scrap in found.scraps:
        result = read_one_card(vault, manifest, scrap, papers.get(scrap.paper) or {}, found.book)
        if isinstance(result, str):
            problems.append(result)
        else:
            marks[scrap.key] = result
    if problems:
        raise index.Unreadable(problems)
    return marks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vault", type=Path, required=True, help="Tolaria vault folder outside the repository")
    ap.add_argument("--scrapbook", type=Path, help="scrapbook folder (default: see tools/paths.py)")
    ap.add_argument("--set-owner", action="store_true",
                    help="register this vault as the single owner vault that may update object.yaml")
    ap.add_argument("--confirm-unarchive", metavar="TOKEN",
                    help="confirm unarchiving the exact scrap set identified by TOKEN")
    args = ap.parse_args(argv)
    root, book, vault = TOOL_ROOT, for_command(args.scrapbook, part="scraps"), args.vault.expanduser().resolve()
    if book is None:
        print("no scrapbook found; nothing written. Pass --scrapbook PATH or set CEDALION_SCRAPBOOK.",
              file=sys.stderr)
        return 2
    if any(vault == r or r in vault.parents for r in (root, book)):
        ap.error("the vault must be outside the tool root and the scrapbook")
    try:
        return run(root, book, vault, args.set_owner, args.confirm_unarchive)
    except index.Unreadable as bad:
        for problem in bad.problems:
            print(f"does not read: {problem}", file=sys.stderr)
        print(f"nothing written to {book}: every source and scrap card must read before marks are imported",
              file=sys.stderr)
        return 1
    except vaults.Stop as stop:
        for line in stop.lines:
            print(line, file=sys.stderr)
        return 2


def register_owner(book: Path, vault: Path, manifest: vaults.Manifest) -> int:
    if manifest.version != vaults.VERSION or not manifest.vault_id:
        print(f"{vault} must have a version {vaults.VERSION} manifest with a vault_id before --set-owner "
              f"(run pixi run cards --vault \"{vault}\" first).", file=sys.stderr)
        return 2
    prev_book = vaults.read_book_owner(book)
    prev_local = vaults.read_local_owner(book)
    vaults.write_book_owner(book, manifest.vault_id)
    vaults.write_local_owner(book, vault, manifest.vault_id)
    if prev_book and prev_book != manifest.vault_id:
        print(f"transferred archive owner for {book} from {prev_book[:8]} to {vault} ({manifest.vault_id[:8]})")
    elif prev_local and prev_local != (str(vault.resolve()), manifest.vault_id):
        print(f"updated local archive owner binding for {book} to {vault} ({manifest.vault_id[:8]})")
    else:
        print(f"registered owner vault for {book}: {vault} ({manifest.vault_id[:8]})")
    print(f"Commit {book / vaults.BOOK_OWNER} in the scrapbook so other clones recognize this owner vault.")
    return 0


def run(root: Path, book: Path, vault: Path, set_owner: bool = False,
        confirm_unarchive: str | None = None) -> int:
    # Always lock scrapbook before vault to keep one lock order across all writers.
    book_lock = vaults.Lock(book, "another run is writing this scrapbook")
    vault_lock = vaults.Lock(vault, "another run is writing this vault")
    try:
        manifest = vaults.read_manifest(vault)
        if not manifest.there:
            print(f"{vault} has no {vaults.MANIFEST}; nothing written to {book}.", file=sys.stderr)
            return 2
        if manifest.scrapbook not in (None, str(book)):
            print(f"{vault} was made from {manifest.scrapbook}, not {book}; nothing written.", file=sys.stderr)
            return 2
        if set_owner:
            return register_owner(book, vault, manifest)
        if manifest.version not in vaults.READ or not manifest.vault_id:
            print(
                f"{vault} has an older manifest without hashes/vault_id and cannot write to {book}. "
                f"Migrate it first with `pixi run cards --from \"{vault}\" --vault <new-vault>`, "
                "then register the owner vault with `pixi run archive-import --vault <new-vault> --set-owner`.",
                file=sys.stderr,
            )
            return 2

        found = index.sources(root, book, images=False).whole()
        marks = read_marks(vault, manifest, found)
        papers = {p.key: p.item for p in found.papers}
        owner_ok, owner_why = vaults.is_archive_owner(book, vault, manifest.vault_id)
        if not owner_ok:
            print(f"{vault} is a reader for {book}: {owner_why}; nothing written.", file=sys.stderr)
            return 2

        to_archive: list[tuple[index.Scrap, str, bytes]] = []
        to_unarchive: list[tuple[index.Scrap, str, bytes, bool | None]] = []
        deferred_book: list[str] = []
        for scrap in found.scraps:
            key = f"{scrap.paper}/{scrap.slug}"
            r = bool(scrap.obj.get("archived"))
            v, card_sha = marks[scrap.key]
            b = manifest.agreed.get(key) if manifest.version == vaults.VERSION else None
            status = vaults.archive_status(r, v, b)
            if status == "agreed":
                continue
            if status == "book_changed":
                deferred_book.append(key)
                continue
            new_text = set_archived(scrap.source, v)
            parsed, error = index.yaml_text(new_text)
            base_before = {k: val for k, val in scrap.obj.items() if k != "archived"}
            base_after = ({k: val for k, val in (parsed or {}).items() if k != "archived"}
                          if isinstance(parsed, dict) else None)
            if error or index.scrap_problem(parsed) or bool(parsed.get("archived")) != v or base_after != base_before:
                raise index.Unreadable([f"{scrap.path}: cannot update archived mark cleanly"])
            new_bytes = new_text.encode("utf-8")
            if v:
                to_archive.append((scrap, card_sha, new_bytes))
            else:
                to_unarchive.append((scrap, card_sha, new_bytes, b))

        # Clearing any existing `archived: true` always requires the exact plan-bound token.
        if to_unarchive:
            token = vaults.unarchive_token(
                book, vault, manifest.vault_id,
                [(f"{s.paper}/{s.slug}", csha, vaults.sha(s.source.encode("utf-8")), b)
                 for s, csha, _, b in to_unarchive],
            )
            if confirm_unarchive != token:
                print(f"nothing written to {book}: {len(to_unarchive)} scrap(s) would be unarchived and need "
                      "explicit confirmation:", file=sys.stderr)
                for scrap, _, _, b in to_unarchive:
                    why = "unreconciled (not previously verified in this vault)" if b is None else "unarchived in Tolaria"
                    print(f"  unarchived: scraps/{scrap.paper}/{scrap.slug} ({why})", file=sys.stderr)
                print(f"To keep them archived and update your vault cards instead: "
                      f"pixi run cards --vault \"{vault}\" --sync-from-book", file=sys.stderr)
                print(f"To unarchive exactly the list above: "
                      f"pixi run archive-import --vault \"{vault}\" --confirm-unarchive {token}", file=sys.stderr)
                return 2

        changes: list[tuple[index.Scrap, bool, str, bytes]] = (
            [(s, True, csha, data) for s, csha, data in to_archive]
            + [(s, False, csha, data) for s, csha, data, _ in to_unarchive]
        )
        done = 0
        applied: dict[tuple[str, str], bool] = {}
        try:
            for scrap, want, card_sha, new_bytes in changes:
                if index.read_bytes(scrap.path)[0] != scrap.source.encode("utf-8"):
                    print(f"stopped while writing {book} ({done} of {len(changes)} written: "
                          f"{scrap.path} changed since it was read); run again to finish.", file=sys.stderr)
                    return 1
                live = read_one_card(vault, manifest, scrap, papers.get(scrap.paper) or {}, book)
                if isinstance(live, str) or live[0] != want or live[1] != card_sha:
                    reason = live if isinstance(live, str) else f"{vault / f'{scrap.paper}-{scrap.slug}.md'} changed while writing"
                    print(f"stopped while writing {book} ({done} of {len(changes)} written: {reason}); "
                          "run again to finish.", file=sys.stderr)
                    return 1
                vaults.replace(scrap.path, new_bytes)
                done += 1
                applied[scrap.key] = want
                print(f"{'archived' if want else 'unarchived'}: scraps/{scrap.paper}/{scrap.slug}")
        except OSError as error:
            print(f"stopped while writing {book} ({done} of {len(changes)} written: "
                  f"{error.filename or scrap.path}: {error.strerror or error}); run again to finish.",
                  file=sys.stderr)
            return 1

        # Post-write dual-side verification: re-read BOTH the scrapbook and the vault.
        # Any read error here happens after writes, so never report "nothing written".
        try:
            after_book = index.sources(root, book, images=False).whole()
            after_manifest = vaults.read_manifest(vault)
            after_marks = read_marks(vault, after_manifest, after_book)
        except index.Unreadable as bad:
            print(f"wrote {done} of {len(changes)} file(s) to {book}, then post-write verification failed:",
                  file=sys.stderr)
            for problem in bad.problems:
                print(f"  {problem}", file=sys.stderr)
            return 1

        after_by_key = {s.key: bool(s.obj.get("archived")) for s in after_book.scraps}
        mismatched = []
        for skey, want in applied.items():
            if skey not in after_by_key or skey not in after_marks:
                mismatched.append(f"scraps/{skey[0]}/{skey[1]} (missing after write)")
            elif after_by_key[skey] != want or after_marks[skey][0] != want:
                mismatched.append(
                    f"scraps/{skey[0]}/{skey[1]} (book={after_by_key[skey]}, vault={after_marks[skey][0]}, expected={want})"
                )

        # Record verified agreed checkpoints only where BOTH sides currently agree.
        if after_manifest.version == vaults.VERSION and after_manifest.vault_id:
            updated_agreed = dict(after_manifest.agreed)
            for s in after_book.scraps:
                str_key = f"{s.paper}/{s.slug}"
                r_now = after_by_key[s.key]
                v_now = after_marks[s.key][0]
                if r_now == v_now:
                    updated_agreed[str_key] = r_now
            if updated_agreed != after_manifest.agreed:
                vaults.replace(
                    vault / vaults.MANIFEST,
                    vaults.manifest_text(book, after_manifest.records, after_manifest.vault_id,
                                         updated_agreed).encode("utf-8"),
                )

        if mismatched:
            print(f"wrote {done} of {len(changes)} file(s), but final book/vault state disagrees on "
                  f"{len(mismatched)} scrap(s): {', '.join(mismatched)}", file=sys.stderr)
            return 1
        if deferred_book:
            print(f"deferred {len(deferred_book)} scrap(s) that changed in {book} "
                  f"({', '.join(deferred_book)}): run pixi run cards --vault \"{vault}\" --sync-from-book "
                  "to update vault cards")
        return 0
    finally:
        vault_lock.close()
        book_lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
