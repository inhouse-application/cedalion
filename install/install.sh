#!/bin/sh
# Install Cedalion on macOS or Linux: pixi if missing, a clone of the repository, its environment,
# and a check. Runs as a normal user (no sudo); the skill is registered with symbolic links.
# install.ps1 is the same installer for Windows, step for step: change both together.
#
#   curl -fsSL <raw URL>/install/install.sh | sh
#   sh install.sh [--scrapbook] [folder]
#   sh install.sh --unregister [folder]
#
# Default folder: ~/cedalion. Through a pipe, give the options as environment variables:
#   CEDALION_INSTALL_DIR             the folder
#   CEDALION_INSTALL_SCRAPBOOK       1 for --scrapbook
#   CEDALION_INSTALL_REF             branch or tag to install (default: this installer's release tag;
#                                    main for the newest)
#   CEDALION_INSTALL_REPO            repository to clone (default: the lab's GitHub repository)
#   CEDALION_INSTALL_SCRAPBOOK_REPO  scrapbook repository for --scrapbook (default: the lab's private one)
#
# It runs in three steps. The survey only reads: the folder, the commit the release tag (or
# CEDALION_INSTALL_REF) names in the repository, the folder orion beside it, the scrapbook named in
# <folder>/.cedalion-scrapbook, the two skill links. The plan then says, for each of them, what happens:
#   folder       a new clone at that commit, a fast-forward of a Cedalion clone of the repository to it
#                (never back), or stop: anything else there (other files, another repository, an earlier
#                clone that holds a scrapbook: a papers/ or scraps/ folder, as tools/paths.py defines one)
#   orion        with --scrapbook: a new clone of the scrapbook repository, or a pull of a clone of it;
#                anything else there is left as it is, and so is a scrapbook named elsewhere
#   .cedalion-scrapbook  written, naming orion, only when it named nothing and orion is a clone of
#                the scrapbook repository
#   skill links  made where nothing is, kept when they point to the folder, else left as they are
# Only a stop in the plan ends the run, before anything is changed or installed (git aside). A new
# clone is made in a temporary folder beside the folder and moved there once it is at the commit.
# install/test_install.py checks these rules on both installers.
set -eu

# The release this installer belongs to, and installs. install/test_install.py keeps it equal to the
# version in zotero-plugin/addon/manifest.json, which the release workflow checks against the tag.
RELEASE=v0.1.1

# The whole installer is one function, called on the last line: a download cut short before that line
# never runs a command.
install_cedalion() {
REF="${CEDALION_INSTALL_REF:-}"
REPO="${CEDALION_INSTALL_REPO:-https://github.com/inhouse-application/cedalion.git}"
BOOK_REPO="${CEDALION_INSTALL_SCRAPBOOK_REPO:-https://github.com/inhouse-application/orion.git}"
mode=register
book=no
[ "${CEDALION_INSTALL_SCRAPBOOK:-}" = 1 ] && book=yes
TARGET="${CEDALION_INSTALL_DIR:-}"
while [ $# -gt 0 ]; do
    case "$1" in
        --unregister) mode=unregister ;;
        --scrapbook) book=yes ;;
        -*) printf 'Unknown option: %s\nUsage: sh install.sh [--scrapbook] [folder] | --unregister [folder]\n' "$1" >&2; exit 2 ;;
        *) TARGET="$1" ;;
    esac
    shift
done
say() { printf '\n==> %s\n' "$1"; }
fail() { printf '\nCedalion install stopped: %s\n' "$1" >&2; exit 1; }
START=$(pwd)

# A path given on the command line or in the environment, made absolute against the start folder, with
# . and .. read as text (as PowerShell's GetFullPath does) and no trailing /; symbolic links are kept.
absolute() {
    case "$1" in
        "~") p=$HOME ;;
        "~/"*) p="$HOME/${1#"~/"}" ;;
        /*) p=$1 ;;
        *) p="$START/$1" ;;
    esac
    out="" saved_ifs=$IFS
    set -f
    IFS=/
    for part in $p; do
        case "$part" in ""|.) ;; ..) out=${out%/*} ;; *) out="$out/$part" ;; esac
    done
    IFS=$saved_ifs
    set +f
    printf '%s\n' "${out:-/}"
}

# The physical form of a path (absolute above): every component that is there followed through its links,
# as `pwd -P` does, and the rest, not there yet, appended as it is. Install, re-run and unregister name the
# folder by this one value, and a skill link is the installer's only when its target has the same one.
# install.ps1's Get-PhysicalPath is the same.
physical() {
    p=$(absolute "$1") rest=""
    while [ "$p" != / ] && [ ! -d "$p" ]; do
        rest="/$(basename "$p")$rest"
        p=$(dirname "$p")
    done
    p=$(cd "$p" 2>/dev/null && pwd -P) || return 1
    printf '%s%s\n' "$(stored "$p")" "$rest"
}

# A folder path with each component named as the file system stores it (on a file system that ignores
# case or normalizes Unicode, `pwd -P` may keep the form it was given).
stored() {
    out="" saved_ifs=$IFS
    set -f
    IFS=/
    for part in $1; do
        [ -n "$part" ] || continue
        name=$(ls -a "${out:-/}" 2>/dev/null | awk -v p="$part" '$0 == p { print; found = 1; exit }
            END { if (!found) exit 1 }') ||
            name=$(ls -a "${out:-/}" 2>/dev/null | awk -v p="$part" 'tolower($0) == tolower(p) { print; exit }')
        if [ -z "$name" ] && [ -e "${out:-/}/$part" ]; then
            want=$(ls -id "${out:-/}/$part" 2>/dev/null | awk '{print $1}')
            [ -n "$want" ] && name=$(ls -ia "${out:-/}" 2>/dev/null | awk -v i="$want" '$1 == i && $2 != "." && $2 != ".." { sub(/^[[:space:]]*[0-9]+[[:space:]]+/, ""); print; exit }')
        fi
        out="$out/${name:-$part}"
    done
    IFS=$saved_ifs
    set +f
    printf '%s\n' "${out:-/}"
}

# A repository address as git compares it: a URL as it is, a local path in its physical form.
address() {
    case "$1" in
        *://*|*@*:*) printf '%s\n' "$1" ;;
        *) physical "$1" || printf '%s\n' "$1" ;;
    esac
}

# The survey resolves every path and address once; from here on only these values are used.
TARGET=$(physical "${TARGET:-$HOME/cedalion}") || fail "cannot read the folders on the way to ${TARGET:-$HOME/cedalion}"
REPO=$(address "$REPO")
BOOK_REPO=$(address "$BOOK_REPO")
BOOK="$(dirname "$TARGET")/orion"
POINTER="$TARGET/.cedalion-scrapbook"
LINKS="$HOME/.claude/skills/cedalion
$HOME/.agents/skills/cedalion"


# The origin of the clone in $1, or nothing.
origin_of() { git -C "$1" remote get-url origin 2>/dev/null || true; }

same_repo() { [ "$(address "$1")" = "$(address "$2")" ]; }

# True when $1 is absent or an empty folder: the only places a clone is made.
is_free() { [ ! -e "$1" ] && [ ! -L "$1" ] || { [ -d "$1" ] && [ -z "$(ls -A "$1" 2>/dev/null)" ]; }; }

# The definition of tools/paths.py: a folder that holds papers/ or scraps/, tracked or not, empty or not.
is_scrapbook() { [ -d "$1/papers" ] || [ -d "$1/scraps" ]; }

# --- Survey: reads only -------------------------------------------------------------------------

# FULL_REF and COMMIT: the release tag, or CEDALION_INSTALL_REF as a tag, else as a branch, in REPO.
# An annotated tag is followed to its commit.
survey_ref() {
    name="${REF:-$RELEASE}"
    refs=$(git ls-remote "$REPO") || fail "could not read $REPO. Check the address and your network, and run again."
    if [ -z "$REF" ]; then
        newer=$(printf '%s\n' "$refs" | awk -v cur="$RELEASE" '
            BEGIN {
                sub(/^v/, "", cur)
                split(cur, c, ".")
                bm = c[1] + 0; bn = c[2] + 0; bp = c[3] + 0; best = ""
            }
            $2 ~ /^refs\/tags\/v[0-9]+\.[0-9]+\.[0-9]+$/ {
                t = $2; sub(/^refs\/tags\//, "", t)
                split(substr(t, 2), a, ".")
                m = a[1] + 0; n = a[2] + 0; p = a[3] + 0
                if (m > bm || (m == bm && (n > bn || (n == bn && p > bp)))) {
                    bm = m; bn = n; bp = p; best = t
                }
            }
            END { if (best != "") print best }
        ')
        [ -z "$newer" ] || fail "this installer is for $RELEASE, but $newer is available. Download the latest installer from https://github.com/inhouse-application/cedalion/releases/latest/download/install.sh (or set CEDALION_INSTALL_REF=$RELEASE to install $RELEASE explicitly)."
    fi
    pick() { printf '%s\n' "$refs" | awk -v want="$1" '$2 == want { print $1; exit }'; }
    tag=$(pick "refs/tags/$name") peeled=$(pick "refs/tags/$name^{}") branch=$(pick "refs/heads/$name")
    if [ -n "$tag" ]; then
        FULL_REF="refs/tags/$name" COMMIT="${peeled:-$tag}"
    elif [ -n "$REF" ] && [ -n "$branch" ]; then
        FULL_REF="refs/heads/$name" COMMIT="$branch"
    elif [ -n "$REF" ]; then
        fail "$REPO has no branch or tag $name. Check CEDALION_INSTALL_REF, and run again."
    else
        fail "$REPO has no release tag $name. Run again later, or set CEDALION_INSTALL_REF=main for the newest commit."
    fi
}

# Stop if any path added between $3 and $4 already exists (untracked or git-ignored) in $1,
# or has a non-directory or symlink ancestor in $1. Sets COLLISION_PATH and returns 1 on clash.
check_incoming_collisions() {
    c_dir=$1 c_git=$2 c_base=$3 c_target=$4
    COLLISION_PATH=""
    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        if [ -e "$c_dir/$rel" ] || [ -L "$c_dir/$rel" ]; then
            COLLISION_PATH="$c_dir/$rel"
            return 1
        fi
        p=$(dirname "$rel")
        while [ "$p" != . ] && [ "$p" != / ]; do
            if [ -L "$c_dir/$p" ] || { [ -e "$c_dir/$p" ] && [ ! -d "$c_dir/$p" ]; }; then
                COLLISION_PATH="$c_dir/$p"
                return 1
            fi
            p=$(dirname "$p")
        done
    done <<EOF
$(git -C "$c_git" -c core.quotePath=false diff-tree -r --no-renames --name-only --diff-filter=A "$c_base" "$c_target")
EOF
    return 0
}

# Survey a fast-forward update of existing git clone $1 against $3 ($4) in $2, without touching $1.
# Sets REPO_HEAD, REPO_MODE (same | ahead | ff), REPO_OLD_TAG and REPO_CHANGED.
survey_repo_update() {
    u_dir=$1 u_repo=$2 u_commit=$3 u_ref=$4
    REPO_HEAD="" REPO_MODE="" REPO_OLD_TAG="" REPO_CHANGED=0
    REPO_HEAD=$(git -C "$u_dir" rev-parse HEAD) || fail "$u_dir has no commit checked out."
    [ -z "$(git -C "$u_dir" status --porcelain --untracked-files=no)" ] ||
        fail "$u_dir has local changes to tracked files; commit or stash them, and run again."
    if [ "$REPO_HEAD" = "$u_commit" ]; then
        REPO_MODE=same
        return 0
    fi
    tmp=$(mktemp -d "${TMPDIR:-/tmp}/.cedalion-survey.XXXXXX") || fail "could not make a temporary folder."
    git init -q --bare "$tmp"
    mkdir -p "$tmp/objects/info"
    printf '%s\n' "$u_dir/.git/objects" > "$tmp/objects/info/alternates"
    if ! git -C "$tmp" fetch -q --no-tags "$u_repo" "$u_commit" 2>/dev/null ||
       [ "$(git -C "$tmp" rev-parse -q --verify "$u_commit^{commit}" 2>/dev/null)" != "$u_commit" ]; then
        rm -rf "$tmp"
        fail "could not fetch $u_commit ($u_ref) from $u_repo into $u_dir; check your network, and run again."
    fi
    if git -C "$tmp" merge-base --is-ancestor "$u_commit" "$REPO_HEAD" 2>/dev/null; then
        REPO_MODE=ahead
    elif git -C "$tmp" merge-base --is-ancestor "$REPO_HEAD" "$u_commit" 2>/dev/null; then
        REPO_MODE=ff
        if ! check_incoming_collisions "$u_dir" "$tmp" "$REPO_HEAD" "$u_commit"; then
            rm -rf "$tmp"
            fail "$COLLISION_PATH already exists and is not tracked by git; it is kept as it is. Move it out of the way, and run again."
        fi
        REPO_CHANGED=$(git -C "$tmp" diff --name-only "$REPO_HEAD" "$u_commit" | wc -l | tr -d ' ')
        REPO_OLD_TAG=$(git -C "$u_dir" describe --tags --exact-match "$REPO_HEAD" 2>/dev/null || printf '%.7s' "$REPO_HEAD")
    else
        rm -rf "$tmp"
        fail "$u_dir has commits of its own that are not in $u_ref; it is left as it is."
    fi
    rm -rf "$tmp"
}

# TARGET_PLAN: install (a new clone) or update (a Cedalion clone of REPO); anything else stops.
survey_target() {
    HEAD_BEFORE="" UPDATE_MODE="" OLD_TAG="" CHANGED_FILES=0
    if [ -d "$TARGET/.git" ]; then
        is_scrapbook "$TARGET" && fail "$TARGET is an earlier Cedalion clone, which holds a scrapbook itself (papers/ or scraps/); it is left as it is. Install into another folder: sh install.sh --scrapbook <folder>"
        [ -f "$TARGET/SKILL.md" ] && [ -d "$TARGET/snippets" ] || fail "$TARGET is a git repository but not Cedalion."
        origin=$(origin_of "$TARGET")
        same_repo "$origin" "$REPO" || fail "$TARGET is a clone of ${origin:-a repository without origin}, not $REPO. Choose another folder, or set CEDALION_INSTALL_REPO to that address to update it."
        read_pointer
        [ "$POINTER_STATE" != empty ] || fail "$POINTER names no folder; it is left as it is. Write the scrapbook's path in it, or remove it, and run again."
        [ "$POINTER_STATE" != other ] || fail "$POINTER is a folder or a link, not a file; it is left as it is. Remove it, and run again."
        survey_repo_update "$TARGET" "$REPO" "$COMMIT" "$FULL_REF"
        HEAD_BEFORE="$REPO_HEAD" UPDATE_MODE="$REPO_MODE" OLD_TAG="$REPO_OLD_TAG" CHANGED_FILES="$REPO_CHANGED"
        TARGET_PLAN=update
    elif is_free "$TARGET"; then
        TARGET_PLAN=install
    else
        fail "$TARGET exists and is not empty. Choose another folder: sh install.sh <folder>"
    fi
}

# POINTER_STATE: none (no .cedalion-scrapbook), named (NAMED, absolute: a relative path is read from the
# tool root, the folder), empty (the file names nothing) or other (a folder or a link in its place). First
# line, without a byte order mark or CR, as tools/paths.py reads it.
read_pointer() {
    POINTER_STATE=none NAMED=""
    if [ -L "$POINTER" ] || { [ -e "$POINTER" ] && [ ! -f "$POINTER" ]; }; then
        POINTER_STATE=other
        return 0
    fi
    [ -e "$POINTER" ] || return 0
    named=$(head -n 1 "$POINTER" | tr -d '\r')
    named="${named#"$(printf '\357\273\277')"}"
    named=$(printf '%s' "$named" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
    if [ -z "$named" ]; then
        POINTER_STATE=empty
        return 0
    fi
    case "$named" in /*) ;; "~"*) named="$HOME${named#\~}" ;; *) named="$TARGET/$named" ;; esac
    POINTER_STATE=named NAMED="$named"
}

# Resolve the remote ref and commit that an existing clone at BOOK tracks in BOOK_REPO.
survey_book_ref() {
    BOOK_REF="" BOOK_COMMIT=""
    b_refs=$(git ls-remote --symref "$BOOK_REPO") || fail "could not read $BOOK_REPO. Check the address and your network, and run again."
    b_pick() { printf '%s\n' "$b_refs" | awk -v want="$1" '$1 != "ref:" && $2 == want { print $1; exit }'; }
    b_branch=$(git -C "$BOOK" symbolic-ref -q --short HEAD 2>/dev/null || true)
    if [ -n "$b_branch" ]; then
        b_merge=$(git -C "$BOOK" config --get "branch.$b_branch.merge" 2>/dev/null || true)
        b_want="${b_merge:-refs/heads/$b_branch}"
    else
        b_sym=$(printf '%s\n' "$b_refs" | awk '$1 == "ref:" && $3 == "HEAD" { print $2; exit }')
        b_want="${b_sym:-HEAD}"
    fi
    BOOK_COMMIT=$(b_pick "$b_want")
    [ -n "$BOOK_COMMIT" ] || fail "$BOOK_REPO has no ref $b_want for $BOOK."
    BOOK_REF="$b_want"
}

# BOOK_PLAN: clone, pull, or keep (with BOOK_NOTE); WRITE_POINTER: yes when the pointer names nothing.
survey_book() {
    read_pointer
    WRITE_POINTER=no
    BOOK_HEAD="" BOOK_MODE="" BOOK_OLD_TAG="" BOOK_CHANGED=0 BOOK_REF="" BOOK_COMMIT=""
    if [ "$POINTER_STATE" = named ]; then
        # A scrapbook named elsewhere is the user's: only orion beside the folder is the installer's.
        if [ "$(address "$NAMED")" != "$(address "$BOOK")" ]; then
            BOOK_PLAN=keep BOOK_NOTE="Keeping the scrapbook named in $POINTER: $NAMED"
            return
        fi
    else
        WRITE_POINTER=yes
    fi
    if [ -d "$BOOK/.git" ]; then
        if same_repo "$(origin_of "$BOOK")" "$BOOK_REPO"; then
            survey_book_ref
            survey_repo_update "$BOOK" "$BOOK_REPO" "$BOOK_COMMIT" "$BOOK_REF"
            BOOK_HEAD="$REPO_HEAD" BOOK_MODE="$REPO_MODE" BOOK_OLD_TAG="$REPO_OLD_TAG" BOOK_CHANGED="$REPO_CHANGED"
            BOOK_PLAN=pull
        else
            BOOK_PLAN=keep BOOK_NOTE="$BOOK is another repository; it is left as it is and not used. The tools are installed alone."
        fi
    elif is_free "$BOOK"; then
        BOOK_PLAN=clone
    else
        BOOK_PLAN=keep BOOK_NOTE="$BOOK exists and is not a clone; it is left as it is and not used. The tools are installed alone."
    fi
    [ "$BOOK_PLAN" = keep ] && WRITE_POINTER=no
    return 0
}

# What is at the skill link $1: ours (a link whose target's physical form is the folder's), taken
# (anything else: a folder, a file, a link elsewhere or to nowhere), or free.
survey_link() {
    if [ -L "$1" ] && [ "$(physical "$1" 2>/dev/null)" = "$TARGET" ] && [ -d "$TARGET" ]; then echo ours
    elif [ -e "$1" ] || [ -L "$1" ]; then echo taken
    else echo free
    fi
}

# --- Apply: writes only where the plan says ----------------------------------------------------

# A clone of $1 at commit $3 (on branch $4 when given, else detached) moved into the free folder $2:
# made in a temporary folder beside it and moved once it is at that commit and holds $5. When anything
# fails, the temporary folder and the folders made above $2 are removed, and the function returns 1.
clone_at() {
    repo=$1 dir=$2 commit=$3 branch=$4 must=$5
    made="" d=$(dirname "$dir")
    while [ ! -e "$d" ]; do made="$made$d
"; d=$(dirname "$d"); done
    mkdir -p "$(dirname "$dir")"
    tmp=$(mktemp -d "$(dirname "$dir")/.cedalion-install.XXXXXX") || return 1
    if git -c advice.detachedHead=false clone --no-checkout --config core.autocrlf=false "$repo" "$tmp/clone" &&
        if [ -n "$branch" ]; then git -C "$tmp/clone" checkout -q -B "$branch" "$commit" &&
            git -C "$tmp/clone" branch -q --set-upstream-to="origin/$branch" "$branch"
        elif [ -n "$commit" ]; then git -C "$tmp/clone" -c advice.detachedHead=false checkout -q --detach "$commit"
        else git -C "$tmp/clone" checkout -q
        fi &&
        { [ -z "$commit" ] || [ "$(git -C "$tmp/clone" rev-parse HEAD)" = "$commit" ]; } &&
        { [ -z "$must" ] || [ -e "$tmp/clone/$must" ]; } &&
        { [ ! -d "$dir" ] || rmdir "$dir"; } && mv "$tmp/clone" "$dir"; then
        rmdir "$tmp"
        return 0
    fi
    rm -rf "$tmp"
    printf '%s' "$made" | while IFS= read -r d; do rmdir "$d" 2>/dev/null || break; done
    return 1
}

apply_target() {
    say "Getting Cedalion $FULL_REF ($COMMIT) into $TARGET"
    branch=""
    case "$FULL_REF" in refs/heads/*) branch="${FULL_REF#refs/heads/}" ;; esac
    if [ "$TARGET_PLAN" = install ]; then
        is_free "$TARGET" || fail "$TARGET changed during the install; run again."
        clone_at "$REPO" "$TARGET" "$COMMIT" "$branch" SKILL.md ||
            fail "could not clone $FULL_REF of $REPO as $COMMIT with a SKILL.md. Check the address and your network, and run again."
        return 0
    fi
    [ "$(git -C "$TARGET" rev-parse HEAD)" = "$HEAD_BEFORE" ] || fail "$TARGET changed during the install; run again."
    if [ "$UPDATE_MODE" = same ]; then
        echo "$TARGET is at $FULL_REF already."
    elif [ "$UPDATE_MODE" = ahead ]; then
        echo "$TARGET is ahead of $FULL_REF; it is left there (an install never moves a clone back)."
    else
        [ -z "$(git -C "$TARGET" status --porcelain --untracked-files=no)" ] ||
            fail "$TARGET has local changes to tracked files; commit or stash them, and run again."
        git -C "$TARGET" fetch -q --no-tags --no-write-fetch-head origin "$COMMIT" &&
            [ "$(git -C "$TARGET" rev-parse -q --verify "$COMMIT^{commit}")" = "$COMMIT" ] ||
            fail "could not fetch $COMMIT ($FULL_REF) from $REPO into $TARGET; check your network, and run again."
        check_incoming_collisions "$TARGET" "$TARGET" "$HEAD_BEFORE" "$COMMIT" ||
            fail "$COLLISION_PATH already exists and is not tracked by git; it is kept as it is. Move it out of the way, and run again."
        git -C "$TARGET" merge -q --no-overwrite-ignore --ff-only "$COMMIT" ||
            fail "could not move $TARGET forward to $FULL_REF; commit or stash local changes (or it has commits of its own), and run again."
        echo "Updated $TARGET: $OLD_TAG -> ${REF:-$RELEASE} ($CHANGED_FILES files changed)"
        echo "Release notes: https://github.com/inhouse-application/cedalion/releases/tag/$RELEASE"
    fi
}

apply_book() {
    say "Getting the scrapbook"
    case "$BOOK_PLAN" in
        keep) echo "$BOOK_NOTE"; return 0 ;;
        pull)
            [ "$(git -C "$BOOK" rev-parse HEAD)" = "$BOOK_HEAD" ] || fail "$BOOK changed during the install; run again."
            if [ "$BOOK_MODE" = same ]; then
                echo "$BOOK is at $BOOK_REF already."
            elif [ "$BOOK_MODE" = ahead ]; then
                echo "$BOOK is ahead of $BOOK_REF; it is left there (an install never moves a clone back)."
            else
                [ -z "$(git -C "$BOOK" status --porcelain --untracked-files=no)" ] ||
                    fail "$BOOK has local changes to tracked files; commit or stash them, and run again."
                git -C "$BOOK" fetch -q --no-tags --no-write-fetch-head origin "$BOOK_COMMIT" &&
                    [ "$(git -C "$BOOK" rev-parse -q --verify "$BOOK_COMMIT^{commit}")" = "$BOOK_COMMIT" ] ||
                    fail "could not fetch $BOOK_COMMIT ($BOOK_REF) from $BOOK_REPO into $BOOK; check your network, and run again."
                check_incoming_collisions "$BOOK" "$BOOK" "$BOOK_HEAD" "$BOOK_COMMIT" ||
                    fail "$COLLISION_PATH already exists and is not tracked by git; it is kept as it is. Move it out of the way, and run again."
                git -C "$BOOK" merge -q --no-overwrite-ignore --ff-only "$BOOK_COMMIT" ||
                    fail "could not move $BOOK forward to $BOOK_REF; commit or stash local changes (or it has commits of its own), and run again."
                printf 'Updated %s: %s -> %.7s (%s files changed)\n' "$BOOK" "$BOOK_OLD_TAG" "$BOOK_COMMIT" "$BOOK_CHANGED"
            fi ;;
        clone)
            if ! is_free "$BOOK"; then
                echo "$BOOK changed during the install; it is left as it is."
                return 0
            fi
            if ! clone_at "$BOOK_REPO" "$BOOK" "" "" ""; then
                echo "Could not clone the scrapbook $BOOK_REPO (it is private: ask the owner for access). The tools are installed alone; run this again with --scrapbook once you have access."
                return 0
            fi ;;
    esac
    if [ "$WRITE_POINTER" = yes ]; then
        printf '%s\n' "$BOOK" > "$POINTER"
        echo "Scrapbook: $BOOK (written in $POINTER)"
    fi
}

# Make, keep or leave each skill link, as surveyed; with --unregister, remove the links to the folder.
apply_links() {
    printf '%s\n' "$LINKS" | while IFS= read -r link; do
        case "$(survey_link "$link")" in
            ours)
                if [ "$mode" = unregister ]; then
                    unlink "$link"
                    printf 'Unregistered %s\n' "$link"
                else
                    printf 'Already registered: %s -> %s\n' "$link" "$TARGET"
                fi ;;
            taken) printf 'Skipped existing path: %s\n' "$link" ;;
            free)
                if [ "$mode" = register ]; then
                    mkdir -p "$(dirname "$link")"
                    ln -sn "$TARGET" "$link"
                    printf 'Registered %s -> %s\n' "$link" "$TARGET"
                fi ;;
        esac
    done
}

# --- The run ---------------------------------------------------------------------------------------

if [ "$mode" = unregister ]; then
    apply_links
    exit 0
fi

say "Checking git"
# On a Mac without the Command Line Tools, `git` opens Apple's installer and fails until it finishes.
if ! git --version >/dev/null 2>&1; then
    fail "git is not available. Install it (on macOS: xcode-select --install for the Command Line Tools), then run this script again."
fi
git --version

say "Planning"
survey_ref
survey_target
[ "$book" = yes ] && survey_book
echo "folder $TARGET: $TARGET_PLAN to $FULL_REF ($COMMIT)"
[ "$book" = yes ] && echo "scrapbook $BOOK: $BOOK_PLAN"

say "Checking pixi"
if ! command -v pixi >/dev/null 2>&1; then
    if [ -x "${PIXI_HOME:-$HOME/.pixi}/bin/pixi" ]; then
        PATH="${PIXI_HOME:-$HOME/.pixi}/bin:$PATH"
    else
        echo "pixi not found; installing it from https://pixi.sh (official installer)"
        curl -fsSL https://pixi.sh/install.sh | sh
        PATH="${PIXI_HOME:-$HOME/.pixi}/bin:$PATH"
    fi
fi
command -v pixi >/dev/null 2>&1 || fail "pixi did not install. Install it from https://pixi.sh and run this again."
pixi --version

apply_target
apply_links
[ "$book" = yes ] && apply_book

cd "$TARGET"
say "Installing the environment (pixi install --locked)"
pixi install --locked || fail "pixi install --locked failed; see above."

say "Checking (pixi run check)"
pixi run check --quiet || fail "the check reported errors; see above."

cat <<EOF

Cedalion is installed in $TARGET.

  cd "$TARGET"
  pixi run check            # validate files; prints each scrap's level when a scrapbook is set up
  pixi run render-snippets  # run every plotting snippet

Open a new terminal if 'pixi' is not found there (the pixi installer adds it to your shell profile).
Optional next steps are in README.md: the Zotero plugin (zotero-plugin/README.md), Tolaria cards,
and the PDF caption tools.
EOF
}

install_cedalion "$@"
