"""The Tolaria vault that tools/cards.py writes, and what of it is the tool's to change.

Each value has one place where it is changed and one direction:
  a card's content       the scrapbook -> the vault (tools/cards.py)
  a scrap's archive mark  the owner vault's Tolaria archive button -> the scrapbook (tools/archive_import.py)
  other `_` values        Tolaria; they live in the vault only, and cards carries them over
cards never writes the scrapbook.

The vault's manifest (MANIFEST, JSON, version 4) names the scrapbook the cards came from, a unique
`vault_id`, for each file the tool wrote the SHA-256 of the bytes it last wrote ("sha256") and of the card
as generated before the user's view keys were carried into it ("base"), and `agreed`: for each scrap
(`paper/slug`), the last archive value both the scrapbook and the vault card were verified to agree on
(omitted when not yet verified, e.g. upgraded from v2 or v3). Only the files in the manifest and the files
a run makes are looked at; everything else in the vault (the user's notes, an app's folders) is never read
or touched.

Each such file is in one state (`state` / `state_bytes`):
  absent     there is nothing at its path
  written    the manifest has it, and its bytes are what the tool last wrote (or its base without view keys)
  user       the manifest has it, and its bytes are what the tool last wrote except top-level front matter
             keys starting with `_` that the user (Tolaria) added: whole lines, which parse as YAML
  foreign    anything else: not in the manifest, other bytes (an edited body, a comment, a tag, a link
             rewritten after a rename), a front matter that does not close, not UTF-8, a folder or a link
and one table says what a run may do (`ACTIONS`):
              the run makes it              the run does not make it
  absent      write it (with its first      forget it
              `_` values, `initial`)
  written     write it if it differs        delete it
  user        write it, the user's lines    stop
              carried over verbatim
  foreign     stop                          stop
A stop stops everything before anything is written. Deletion needs a byte match with what the tool last
wrote. A new card's first `_` values are the scrap's archive mark (`_archived: true` when object.yaml says
`archived: true`), or the values carried from an older vault (`older_vault`).

Without a manifest the tool owns nothing. A manifest that does not read, or of an unknown version, stops
the run. Versions 2 and 3 (with hashes, without `agreed` or `vault_id`) are read with every scrap's agreed
value unknown, so upgrading never causes an implicit unarchive. An older manifest (a list of names, or JSON
without hashes) is not taken over: cards stops and names the one step that makes a new vault from it
(`--from`), which keeps the old vault as it is.

Writing: runs on one folder are serialized (a lock on the folder, where the system has one; lock order is
always scrapbook before vault); every file is replaced whole through a temporary file of a new name in its
own folder (`replace`); the manifest first with both the old and the new hash of each file to be written
(so a run stopped half way leaves files the next run still knows), then with the new ones. A file whose
bytes changed since the plan read them stops the writing there, and the run says how many of its files it
wrote (`Partial`). After writing, every file is read back (`verify`). The guarantee holds for a vault no
editor is writing to while the run writes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from index import Unreadable

MANIFEST = ".cedalion-cards"
BOOK_OWNER = ".cedalion-archive-owner"  # in the scrapbook: the single approved owner vault_id
VERSION = 4
READ = (2, 3, 4)  # manifest versions read as they are
# `_` keys the cards themselves write (the type notes); any other top-level `_` key is the user's.
OWN_KEYS = {"_icon", "_sidebar_label", "_order", "_list_properties_display"}
ARCHIVED = "_archived"  # the key Tolaria's archive button writes (and removes, to unarchive)
NAME = re.compile(r"[^/\\]+\.md|assets/[^/\\]+")
HEX = re.compile(r"[0-9a-f]{64}")
USER_KEY = re.compile(r"(_[A-Za-z0-9_-]*)\s*:")
LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


class Stop(Exception):
    """Files of the user's in the way: `lines` say which and why. Nothing was written."""

    def __init__(self, lines: list[str]):
        super().__init__("; ".join(lines))
        self.lines = lines


class Partial(Exception):
    """Writing stopped after `done` of `total` files were written; running again finishes."""

    def __init__(self, done: int, total: int, why: str):
        super().__init__(why)
        self.done, self.total, self.why = done, total, why


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def folded(name: str) -> str:
    """A name as a file system that ignores case and Unicode normalization sees it."""
    return unicodedata.normalize("NFC", name).casefold()


def new_vault_id() -> str:
    return uuid.uuid4().hex


# --- The note format Tolaria reads ----------------------------------------------------------------

def split_note(text: str) -> tuple[dict, str]:
    """Front matter and body of a note this module wrote."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return yaml.safe_load(text[4:end]) or {}, text[end + 5:]
    return {}, text


def flow(item) -> str:
    """One list item: a string double-quoted, any other value as YAML writes it (types preserved)."""
    if isinstance(item, str):
        return json.dumps(item, ensure_ascii=False)
    text = yaml.safe_dump(item, allow_unicode=True, default_flow_style=True, width=1000)
    return text.removesuffix("\n").removesuffix("\n...").strip()


def frontmatter(fields: dict) -> str:
    """YAML in the form Tolaria's documentation shows: indented, double-quoted list items and links.

    The properties panel showed list values written as unindented, single-quoted items as empty.
    """
    lines = []
    for key, value in fields.items():
        if isinstance(value, list) and not value:
            lines.append(f"{key}: []")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            lines += [f"  - {flow(item)}" for item in value]
        elif isinstance(value, str) and value.startswith("[["):
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            lines.append(yaml.safe_dump({key: value}, allow_unicode=True, sort_keys=False, width=1000).strip())
    return "\n".join(lines) + "\n"


def view_lines(text: str) -> tuple[str, list[str]] | None:
    """The note without the user's view keys, and those keys' lines as written: top-level front matter
    lines `_key: ...` (key not in OWN_KEYS) with their indented or list continuation lines. None when the
    text has no closed front matter, or the user's lines do not parse as a mapping."""
    if not text.startswith("---\n"):
        return (text, []) if text else None
    end = text.find("\n---\n", 3)
    if end == -1:
        return None
    lines = text[4:end + 1].splitlines(keepends=True)
    kept, user, mine = [], [], False
    for line in lines:
        if (m := USER_KEY.match(line)) and m.group(1) not in OWN_KEYS:
            mine = True
        elif not (mine and (line[:1] in (" ", "\t") or line.startswith("- "))):
            mine = False
        (user if mine else kept).append(line)
    if user:
        try:
            values = yaml.safe_load("".join(user))
        except yaml.YAMLError:
            return None
        if not isinstance(values, dict):
            return None
    return "---\n" + "".join(kept) + text[end + 1:], user


def with_view(text: str, user: list[str]) -> str:
    """A generated card with the user's view lines put back, verbatim, at the end of its front matter."""
    if not user:
        return text
    end = text.find("\n---\n", 3)
    return text[:end + 1] + "".join(user) + text[end + 1:]


def view_values(user: list[str] | tuple[str, ...]) -> dict:
    return (yaml.safe_load("".join(user)) or {}) if user else {}


def archived(user: list[str] | tuple[str, ...]) -> bool:
    """The archive mark of a note with these view lines, as Tolaria reads it."""
    return view_values(user).get(ARCHIVED) is True


def with_archived_mark(user: list[str] | tuple[str, ...], mark: bool) -> list[str]:
    """USER's view lines with `_archived:` set to `true` (MARK=True) or removed (MARK=False),
    preserving every other `_` view line verbatim."""
    kept: list[str] = []
    skip = False
    for line in user:
        if m := USER_KEY.match(line):
            skip = m.group(1) == ARCHIVED
        elif not (skip and (line[:1] in (" ", "\t") or line.startswith("- "))):
            skip = False
        if not skip:
            kept.append(line)
    if mark:
        kept.append(f"{ARCHIVED}: true\n")
    return kept


# --- Shared R / V / B archive decision & owner binding -----------------------------------------------

def archive_status(book_mark: bool, vault_mark: bool, agreed: bool | None) -> str:
    """Classify one scrap from (R=book_mark, V=vault_mark, B=agreed or None when unknown).

      agreed        R == V
      book_changed  B is known, R != B, V == B (scrapbook changed upstream; card still matches B)
      vault_changed B is known, R == B, V != B (local Tolaria button changed the card)
      unreconciled  B is unknown and R != V (v2/old v3 upgrade, or first mismatch without checkpoint)
    """
    if book_mark == vault_mark:
        return "agreed"
    if agreed is not None and book_mark != agreed and vault_mark == agreed:
        return "book_changed"
    if agreed is not None and book_mark == agreed and vault_mark != agreed:
        return "vault_changed"
    return "unreconciled"


def owner_store_path() -> Path:
    """Path to the local owner binding file, outside both the vault and git."""
    given = os.environ.get("CEDALION_ARCHIVE_OWNER")
    if given:
        return Path(given).expanduser().resolve()
    return (Path.home() / ".local/state/cedalion/archive-owners.json").resolve()


def read_book_owner(book: Path) -> str | None:
    """The approved owner vault_id recorded in the scrapbook, or None when unset."""
    path = book / BOOK_OWNER
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise Unreadable([f"{path}: is not a file"])
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as error:
        raise Unreadable([f"{path}: cannot be read ({error})"])
    return text or None


def write_book_owner(book: Path, vault_id: str) -> None:
    replace(book / BOOK_OWNER, (vault_id + "\n").encode("utf-8"))


def read_local_owners() -> dict[str, dict[str, str]]:
    path = owner_store_path()
    if not path.exists() and not path.is_symlink():
        return {}
    if path.is_symlink() or not path.is_file():
        raise Unreadable([f"{path}: is not a file"])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise Unreadable([f"{path}: cannot be read ({error})"])
    if not isinstance(data, dict):
        raise Unreadable([f"{path}: is not a mapping of scrapbook -> owner vault"])
    return data


def read_local_owner(book: Path) -> tuple[str, str] | None:
    entry = read_local_owners().get(str(book.resolve()))
    if not isinstance(entry, dict):
        return None
    vpath, vid = entry.get("vault"), entry.get("vault_id")
    if isinstance(vpath, str) and isinstance(vid, str) and vpath and vid:
        return vpath, vid
    return None


def write_local_owner(book: Path, vault: Path, vault_id: str) -> None:
    path = owner_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = read_local_owners()
    data[str(book.resolve())] = {"vault": str(vault.resolve()), "vault_id": vault_id}
    replace(path, (json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))


def is_archive_owner(book: Path, vault: Path, vault_id: str | None) -> tuple[bool, str]:
    """True only when VAULT's vault_id matches BOTH the scrapbook's approved owner ID and this machine's
    local owner binding for BOOK (exact physical path and vault_id)."""
    if not vault_id:
        return False, "this vault has no vault_id yet (run cards first)"
    book_id = read_book_owner(book)
    local = read_local_owner(book)
    if book_id is None and local is None:
        return False, (f"no owner vault is registered for {book}; "
                       f"run archive-import --vault \"{vault}\" --set-owner on the owner's vault")
    if book_id != vault_id:
        return False, (f"{book / BOOK_OWNER} names another vault_id ({book_id or 'none'}), "
                       f"not this vault ({vault_id[:8]})")
    if local is None:
        return False, (f"this machine has no local owner binding for {book} in {owner_store_path()}; "
                       "only the bound owner vault may write archive marks")
    if local != (str(vault.resolve()), vault_id):
        return False, (f"the bound owner vault for {book} is {local[0]} ({local[1][:8]}), "
                       f"not {vault.resolve()} ({vault_id[:8]})")
    return True, ""


def unarchive_token(book: Path, vault: Path, vault_id: str,
                    items: list[tuple[str, str, str, bool | None]]) -> str:
    """Deterministic 12-hex-char confirmation token binding BOOK, VAULT, VAULT_ID, and the exact
    sorted unarchive items `(paper/slug, card_sha256, object_yaml_sha256, agreed)`."""
    payload = {
        "book": str(book.resolve()),
        "vault": str(vault.resolve()),
        "vault_id": vault_id,
        "unarchive": [list(item) for item in sorted(items)],
    }
    return sha(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))[:12]


# --- The manifest -------------------------------------------------------------------------------------

@dataclass
class Manifest:
    scrapbook: str | None = None
    records: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # name -> [(sha256, base)]
    older: list[str] | None = None  # the names of an older manifest, without hashes
    there: bool = False
    version: int | None = None
    vault_id: str | None = None
    agreed: dict[str, bool] = field(default_factory=dict)  # "paper/slug" -> last verified agreed bool


def read_manifest(vault: Path) -> Manifest:
    """The manifest; an empty one when there is none (the tool owns nothing). Unreadable when it is there
    but does not read, is of an unknown version, or does not have the shape of one."""
    path = vault / MANIFEST
    if not path.exists() and not path.is_symlink():
        return Manifest()
    bad = lambda why: Unreadable([f"{path}: {why}"])  # noqa: E731
    if path.is_symlink() or not path.is_file():
        raise bad("is not a file")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise bad(f"cannot be read ({error})")
    if not text.strip():
        raise bad("is empty")
    if not text.startswith("{"):  # the first format: one name a line
        names = [line for line in text.splitlines() if line.strip()]
        if not all(NAME.fullmatch(n) for n in names):
            raise bad("is not a list of card and image names")
        return Manifest(older=names, there=True, version=1)
    try:
        data = json.loads(text)
    except ValueError:
        raise bad("does not parse as JSON")
    if not isinstance(data, dict) or not isinstance(data.get("scrapbook"), (str, type(None))):
        raise bad("is not a manifest of cards")
    version = data.get("version")
    if version is None and isinstance(data.get("files"), list):  # JSON without hashes
        if not all(isinstance(n, str) and NAME.fullmatch(n) for n in data["files"]):
            raise bad("names files that are not cards or images")
        return Manifest(data["scrapbook"], {}, data["files"], True, 1)
    if version not in READ:
        raise bad(f"is of version {version!r}, which this tool does not know; nothing was read")
    files = data.get("files")
    if not isinstance(files, dict):
        raise bad("is not a manifest of cards")
    records = {}
    for name, record in files.items():
        pairs = record if isinstance(record, list) else None
        if not (NAME.fullmatch(name) and pairs and all(
                isinstance(p, list) and len(p) == 2 and all(isinstance(h, str) and HEX.fullmatch(h) for h in p) for p in pairs)):
            raise bad(f"has a record for {name!r} that is not [[sha256, base], ...]")
        records[name] = [tuple(p) for p in pairs]
    vault_id = None
    agreed: dict[str, bool] = {}
    if version == 4:
        raw_id = data.get("vault_id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise bad("version 4 manifest needs a vault_id")
        vault_id = raw_id
        raw_agreed = data.get("agreed")
        if not isinstance(raw_agreed, dict) or not all(
                isinstance(k, str) and isinstance(v, bool) for k, v in raw_agreed.items()):
            raise bad("version 4 manifest agreed must be a mapping of paper/slug to true or false")
        agreed = dict(raw_agreed)
    return Manifest(data["scrapbook"], records, None, True, version, vault_id, agreed)


def manifest_text(book: Path, records: dict[str, list[tuple[str, str]]],
                  vault_id: str, agreed: dict[str, bool]) -> str:
    return json.dumps({
        "version": VERSION,
        "scrapbook": str(book),
        "vault_id": vault_id,
        "files": {n: [list(p) for p in records[n]] for n in sorted(records)},
        "agreed": {k: agreed[k] for k in sorted(agreed)},
    }, indent=1, ensure_ascii=False) + "\n"


# --- States and the table -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Seen:
    state: str                    # absent, written, user, foreign
    why: str = ""                 # for foreign: what makes it so
    data: bytes | None = None     # the bytes read
    user: tuple[str, ...] = ()    # the user's view lines (state user)


def look(vault: Path, name: str) -> tuple[bytes | None, str]:
    """The bytes at NAME, or None and why they are not a file's bytes ("" when nothing is there)."""
    path = vault / name
    if not path.exists() and not path.is_symlink():
        return None, ""
    if path.is_symlink() or not path.is_file():
        return None, "is a folder or a link"
    try:
        return path.read_bytes(), ""
    except OSError as error:
        return None, f"cannot be read ({error.strerror})"


def state_bytes(name: str, data: bytes, record: list[tuple[str, str]] | None) -> Seen:
    """Pure state classification of already-read bytes DATA against manifest RECORD."""
    if record is None:
        return Seen("foreign", "the tool did not write it (it is not in the manifest)", data)
    here = sha(data)
    if any(here == base for _, base in record):
        return Seen("written", data=data)
    if name.endswith(".md"):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return Seen("foreign", "is not UTF-8", data)
        split = view_lines(text)
        if split is None:
            return Seen("foreign", "its front matter does not close, or its `_` keys do not parse", data)
        rest, user = split
        if user and any(sha(rest.encode("utf-8")) == base for _, base in record):
            return Seen("user", data=data, user=tuple(user))
    return Seen("foreign", "differs from what the tool last wrote", data)


def state(vault: Path, name: str, record: list[tuple[str, str]] | None) -> Seen:
    """The state of NAME (see the module); RECORD is its manifest entry."""
    data, why = look(vault, name)
    if data is None:
        return Seen("absent") if not why else Seen("foreign", why)
    return state_bytes(name, data, record)


# state -> (what to do when the run makes the file, when it does not)
ACTIONS = {
    "absent": ("write", "forget"),
    "written": ("write", "delete"),
    "user": ("write", "stop"),
    "foreign": ("stop", "stop"),
}


@dataclass
class Plan:
    """Everything one run writes, computed from what was read."""
    book: Path
    vault_id: str
    agreed: dict[str, bool] = field(default_factory=dict)
    pending_agreed: dict[str, bool] = field(default_factory=dict)
    writes: dict[str, bytes] = field(default_factory=dict)              # vault files that differ -> bytes
    deletes: list[str] = field(default_factory=list)
    seen: dict[str, Seen] = field(default_factory=dict)
    records: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # the manifest after the run
    pending: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # the manifest while writing

    def manifest(self) -> bytes:
        return manifest_text(self.book, self.records, self.vault_id, self.agreed).encode("utf-8")


def classify(vault: Path, manifest: Manifest, made: dict[str, bytes]) -> dict[str, Seen]:
    """The state of every file the manifest names or the run makes."""
    return {n: state(vault, n, manifest.records.get(n)) for n in sorted(set(manifest.records) | set(made))}


def plan(book: Path, manifest: Manifest, seen: dict[str, Seen], made: dict[str, bytes],
         initial: dict[str, list[str]], override_view: dict[str, list[str]] | None = None,
         agreed: dict[str, bool] | None = None, vault_id: str | None = None) -> Plan:
    """Apply the table to every file; Stop, naming each file of the user's in the way, before anything.
    MADE: every file the run makes -> its bytes; INITIAL: a new card's first `_` lines;
    OVERRIDE_VIEW: explicit replacement `_` lines for existing cards (e.g. --sync-from-book)."""
    override_view = override_view or {}
    vid = vault_id or manifest.vault_id or new_vault_id()
    out = Plan(book, vault_id=vid, agreed=dict(agreed if agreed is not None else manifest.agreed),
               pending_agreed=dict(manifest.agreed), seen=seen)
    stops = []
    for name, found in seen.items():
        action = ACTIONS[found.state][0 if name in made else 1]
        if action == "stop":
            stops.append(f"{name}: {found.why or 'has view keys of the user, and its card is no longer made'}")
            continue
        if action == "forget":
            continue
        if action == "delete":
            out.deletes.append(name)
            continue
        base = made[name]
        if name in override_view:
            user = list(override_view[name])
        elif found.state == "user":
            user = list(found.user)
        elif found.state == "absent":
            user = list(initial.get(name, []))
        else:
            user = []
        data = with_view(base.decode("utf-8"), user).encode("utf-8") if user else base
        if found.data != data:
            out.writes[name] = data
        out.records[name] = [(sha(data), sha(base))]
        old = manifest.records.get(name) or []
        out.pending[name] = list(dict.fromkeys([*old, *out.records[name]]))
    if stops:
        raise Stop(stops)
    for name in out.deletes:
        out.pending[name] = manifest.records[name]
    return out


def collisions(origins: list[tuple[str, str]]) -> list[str]:
    """Output names ((name, what it comes from)) that one file system would take for one file: equal once
    case and Unicode normalization are folded. Each such group as a line."""
    groups: dict[str, list[tuple[str, str]]] = {}
    for name, origin in dict.fromkeys(origins):
        groups.setdefault(folded(name), []).append((name, origin))
    return [" and ".join(f"{origin} ({name})" for name, origin in sorted(group))
            for group in groups.values() if len(group) > 1]


# --- Writing -----------------------------------------------------------------------------------------

class Lock:
    """Runs on one folder one at a time: an exclusive lock on the folder (none where the system has
    no such lock, Windows)."""

    def __init__(self, folder: Path, label: str = "another run is writing this folder"):
        self.fd = None
        try:
            import fcntl
        except ImportError:
            return
        if not folder.is_dir():
            return  # not created yet
        self.fd = os.open(folder, os.O_RDONLY)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            raise Stop([f"{folder}: {label}"])

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)


def default_mode() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


def replace(path: Path, data: bytes) -> None:
    """Put DATA at PATH whole: written to a file of a new name made in the same folder (so on the same
    disk, and never a file that is there already), then moved over PATH. PATH's mode is kept."""
    try:
        mode = path.stat().st_mode & 0o7777 if path.is_file() and not path.is_symlink() else default_mode()
    except OSError:
        mode = default_mode()
    fd, tmp = tempfile.mkstemp(prefix=".cedalion-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write(vault: Path, out: Plan) -> int:
    """Write what the plan holds: the manifest with both hashes, the vault's files, then the manifest
    after the run. The number of files written or removed. Partial when a file's bytes changed since the
    plan, or a write fails, after the first change."""
    final = out.manifest()
    now, _ = look(vault, MANIFEST)
    if not out.writes and not out.deletes and now == final:
        return 0
    total, done = len(out.writes) + len(out.deletes), 0
    try:
        vault.mkdir(parents=True, exist_ok=True)
        (vault / "assets").mkdir(exist_ok=True)
        replace(vault / MANIFEST,
                manifest_text(out.book, out.pending, out.vault_id, out.pending_agreed).encode("utf-8"))
        for name, data in out.writes.items():
            cur, why = look(vault, name)
            if why or cur != out.seen[name].data:
                raise Partial(done, total, f"{name} changed while the cards were planned ({why or 'bytes differ'})")
            replace(vault / name, data)
            done += 1
        for name in out.deletes:
            cur, why = look(vault, name)
            if why or cur != out.seen[name].data:
                raise Partial(done, total, f"{name} changed while the cards were planned ({why or 'bytes differ'})")
            (vault / name).unlink()
            done += 1
        replace(vault / MANIFEST, final)
    except OSError as error:
        raise Partial(done, total, f"{error.filename or vault}: {error.strerror or error}")
    return done


def verify(vault: Path, out: Plan) -> list[str]:
    """Every file of the plan read back: the manifest and each record as written, each removed file gone."""
    wrong = []
    if look(vault, MANIFEST)[0] != out.manifest():
        wrong.append(MANIFEST)
    for name, record in out.records.items():
        data, _ = look(vault, name)
        if data is None or sha(data) != record[0][0]:
            wrong.append(name)
    wrong += [name for name in out.deletes if (vault / name).exists() or (vault / name).is_symlink()]
    return wrong


# --- A vault of an older manifest -----------------------------------------------------------------

@dataclass
class Older:
    """What a new vault takes from an older one: the `_` lines of its cards, and the user's files."""
    present: set[str] = field(default_factory=set)               # cards that were in the older vault
    carried: dict[str, list[str]] = field(default_factory=dict)  # card -> its user's `_` lines
    personal: list[str] = field(default_factory=list)            # paths of the user's files and folders
    gone: list[str] = field(default_factory=list)                # cards with `_` lines no longer made
    unread: list[str] = field(default_factory=list)              # cards whose `_` lines cannot be read


def survey_older(vault: Path, manifest: Manifest, made: set[str] | None = None) -> Older:
    """The cards of the older vault with the user's `_` lines, and every other file in it (not the
    manifest, not a file it names): at the top, and in assets/. MADE: the cards a run makes now."""
    names = set(manifest.older if manifest.older is not None else manifest.records)
    found = Older()
    for name in sorted(n for n in names if n.endswith(".md")):
        data, why = look(vault, name)
        if data is None:
            if why:
                found.unread.append(f"{name}: {why}")
            continue
        try:
            split = view_lines(data.decode("utf-8"))
        except UnicodeDecodeError:
            split = None
        if split is None:
            found.unread.append(f"{name}: its front matter does not close, or its `_` keys do not parse")
            continue
        found.present.add(name)
        if split[1]:
            if made is not None and name not in made:
                found.gone.append(name)
            else:
                found.carried[name] = split[1]
    for entry in sorted(vault.iterdir()) if vault.is_dir() else []:
        rel = entry.name
        if rel == MANIFEST or rel in names:
            continue
        if rel == "assets" and entry.is_dir() and not entry.is_symlink():
            found.personal += [f"assets/{a.name}" for a in sorted(entry.iterdir()) if f"assets/{a.name}" not in names]
            continue
        found.personal.append(rel)
    return found


def copy_personal(old: Path, new: Path, paths: list[str]) -> None:
    """Copy each path (a file, a folder with all in it, a link as a link) from OLD to the same place in NEW."""
    for rel in paths:
        src, dst = old / rel, new / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            os.symlink(os.readlink(src), dst)
        elif src.is_dir():
            shutil.copytree(src, dst, symlinks=True)
        else:
            shutil.copy2(src, dst)


def verify_personal(old: Path, new: Path, paths: list[str]) -> list[str]:
    """Every personal file, link and folder copied from OLD to NEW verified byte-for-byte."""
    wrong: list[str] = []

    def check(src: Path, dst: Path, label: str) -> None:
        if src.is_symlink():
            if not dst.is_symlink() or os.readlink(src) != os.readlink(dst):
                wrong.append(label)
        elif src.is_dir():
            if not dst.is_dir() or dst.is_symlink():
                wrong.append(label)
                return
            src_names = sorted(p.name for p in src.iterdir())
            dst_names = sorted(p.name for p in dst.iterdir())
            if src_names != dst_names:
                wrong.append(label)
                return
            for child in src_names:
                check(src / child, dst / child, f"{label}/{child}")
        else:
            if not dst.is_file() or dst.is_symlink() or src.read_bytes() != dst.read_bytes():
                wrong.append(label)

    for rel in paths:
        check(old / rel, new / rel, rel)
    return wrong


def links(vault: Path, paths: list[str]) -> dict[str, set[str]]:
    """The wiki links of the notes among PATHS that lead to a note of VAULT: note -> the notes linked."""
    out = {}
    for rel in paths:
        if not rel.endswith(".md") or not (vault / rel).is_file():
            continue
        try:
            text = (vault / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out[rel] = {t.strip() for t in LINK.findall(text) if (vault / f"{t.strip()}.md").is_file()}
    return out
