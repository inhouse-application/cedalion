# Install Cedalion on Windows: git and pixi if missing, a clone of the repository, its environment,
# and a check. Runs in Windows PowerShell 5.1 and PowerShell 7 as a normal user (no administrator,
# no Developer Mode); the skill is registered with directory junctions, not symbolic links.
# install.sh is the same installer for macOS and Linux, step for step: change both together.
#
#   powershell -ExecutionPolicy ByPass -c "irm <raw URL>/install/install.ps1 | iex"
#   powershell -ExecutionPolicy ByPass -File install.ps1 [-Scrapbook] [folder]
#   powershell -ExecutionPolicy ByPass -File install.ps1 -Unregister [folder]
#
# Default folder: %USERPROFILE%\cedalion. Through iex, give the options as environment variables:
#   CEDALION_INSTALL_DIR             the folder
#   CEDALION_INSTALL_SCRAPBOOK       1 for -Scrapbook
#   CEDALION_INSTALL_REF             branch or tag to install (default: this installer's release tag;
#                                    main for the newest)
#   CEDALION_INSTALL_REPO            repository to clone (default: the lab's GitHub repository)
#   CEDALION_INSTALL_SCRAPBOOK_REPO  scrapbook repository for -Scrapbook (default: the lab's private one)
#
# It runs in three steps. The survey only reads: the folder, the commit the release tag (or
# CEDALION_INSTALL_REF) names in the repository, the folder orion beside it, the scrapbook named in
# <folder>\.cedalion-scrapbook, the two skill links. The plan then says, for each of them, what happens:
#   folder       a new clone at that commit, a fast-forward of a Cedalion clone of the repository to it
#                (never back), or stop: anything else there (other files, another repository, an earlier
#                clone that holds a scrapbook: a papers\ or scraps\ folder, as tools/paths.py defines one)
#   orion        with -Scrapbook: a new clone of the scrapbook repository, or a pull of a clone of it;
#                anything else there is left as it is, and so is a scrapbook named elsewhere
#   .cedalion-scrapbook  written, naming orion, only when it named nothing and orion is a clone of
#                the scrapbook repository
#   skill links  made where nothing is, kept when they point to the folder, else left as they are
# Only a stop in the plan ends the run, before anything is changed or installed (git aside). A new
# clone is made in a temporary folder beside the folder and moved there once it is at the commit.
# install/test_install.py checks these rules on both installers.
#
# Run as a file, a failure exits with 1; through iex it sets $LASTEXITCODE to 1 and leaves the window open.
# Keep this file ASCII: Windows PowerShell 5.1 reads a file without a byte order mark in the ANSI code page.

param(
    [Parameter(Position = 0)] [string] $Folder = $env:CEDALION_INSTALL_DIR,
    [switch] $Scrapbook = ($env:CEDALION_INSTALL_SCRAPBOOK -eq '1'),
    [switch] $Unregister
)

# The release this installer belongs to, and installs. install/test_install.py keeps it equal to the
# version in zotero-plugin/addon/manifest.json, which the release workflow checks against the tag.
$CedalionRelease = 'v0.1.0'

# The user's folder from the environment, as install.sh uses $HOME (and Claude Code finds its skills).
$CedalionHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }

function Step { param([string] $message) Write-Host "`n==> $message" }

function Fail { param([string] $message) throw "Cedalion install stopped: $message" }

# The origin of the clone in $dir, or ''.
function Get-Origin {
    param([string] $dir)
    $out = & git -C $dir remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0) { return '' }
    [string] @($out)[0]
}

# A path given on the command line or in the environment, made absolute against the start folder (the
# PowerShell location when the script starts). A drive-relative path (C:book) depends on another folder,
# the current one of that drive, and is refused; a root keeps its separator (C:\), a UNC path its share.
function Get-FullPath {
    param([string] $path)
    if ($path -match '^[A-Za-z]:(?![\\/])') {
        Fail "$path is relative to the current folder of drive $($path.Substring(0, 2)), which Windows keeps apart; give a full path such as $($path.Substring(0, 2))\$($path.Substring(2))"
    }
    if ($path -eq '~' -or $path.StartsWith('~/') -or $path.StartsWith('~\')) { $path = $CedalionHome + $path.Substring(1) }
    $full = [IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($path))
    $root = [IO.Path]::GetPathRoot($full)
    if ($full.Length -gt $root.Length) { $full = $full.TrimEnd('\', '/') }
    $full
}

# The physical form of a path (Get-FullPath above): every component that is there followed through its
# links (symbolic links and junctions) and named as the file system stores it, and the rest, not there yet,
# appended as it is. Install, re-run and unregister name the folder by this one value, and a skill link is
# the installer's only when its target has the same one. install.sh's physical is the same.
function Get-PhysicalPath {
    param([string] $path)
    $full = Get-FullPath $path
    $hops = 0
    :resolve while ($true) {
        $root = [IO.Path]::GetPathRoot($full)
        $parts = @($full.Substring($root.Length).Split([char[]] @('\', '/'), [StringSplitOptions]::RemoveEmptyEntries))
        $current = $root
        for ($i = 0; $i -lt $parts.Count; $i++) {
            $next = Join-Path $current $parts[$i]
            $item = Get-Item -LiteralPath $next -Force -ErrorAction SilentlyContinue
            if (-not $item) {
                foreach ($part in @($parts | Select-Object -Skip $i)) { $current = Join-Path $current $part }
                break resolve
            }
            if ($item.LinkType) {
                $hops++
                if ($hops -gt 40) { Fail "$path leads through more than 40 links" }
                $to = Get-LinkTarget $item
                if (-not [IO.Path]::IsPathRooted($to)) { $to = Join-Path $current $to }
                $full = [IO.Path]::GetFullPath([IO.Path]::Combine([string[]] (@($to) + @($parts | Select-Object -Skip ($i + 1)))))
                continue resolve
            }
            $stored = @(Get-ChildItem -LiteralPath $current -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -eq $parts[$i] -or $_.Name.Normalize() -ieq $parts[$i].Normalize() } |
                Select-Object -First 1)
            $name = if ($stored.Count -gt 0) { $stored[0].Name } else { $item.Name }
            $current = Join-Path $current $name
        }
        break
    }
    if ($current.Length -gt [IO.Path]::GetPathRoot($current).Length) { $current = $current.TrimEnd('\', '/') }
    $current
}

function Test-Url { param([string] $repo) ($repo -match '://') -or ($repo -match '^[^\\/]+@[^:]+:') }

# A repository address as git compares it: a URL as it is, a local path in its physical form.
function Get-Address {
    param([string] $repo)
    if (-not $repo -or (Test-Url $repo)) { return $repo }
    Get-PhysicalPath $repo
}

# URLs compare exactly; local paths as the file system does on Windows, whatever their case.
function Test-SameRepo {
    param([string] $a, [string] $b)
    if ((Test-Url $a) -or (Test-Url $b)) { return $a -ceq $b }
    (Get-Address $a) -eq (Get-Address $b)
}

# True when $dir is absent or an empty folder: the only places a clone is made.
function Test-Free {
    param([string] $dir)
    if (-not (Test-Path -LiteralPath $dir)) { return $true }
    (Test-Path -LiteralPath $dir -PathType Container) -and -not (Get-ChildItem -LiteralPath $dir -Force | Select-Object -First 1)
}

# The definition of tools/paths.py: a folder that holds papers\ or scraps\, tracked or not, empty or not.
function Test-Scrapbook {
    param([string] $dir)
    (Test-Path -LiteralPath (Join-Path $dir 'papers') -PathType Container) -or (Test-Path -LiteralPath (Join-Path $dir 'scraps') -PathType Container)
}

function Get-Head {
    param([string] $dir)
    $out = & git -C $dir rev-parse HEAD 2>$null
    if ($LASTEXITCODE -ne 0) { return '' }
    [string] @($out)[0]
}

# --- Survey: reads only -------------------------------------------------------------------------

# The release tag, or $ref as a tag, else as a branch, in $repo: @{ Full; Commit }. An annotated tag
# is followed to its commit.
function Get-RefCommit {
    param([string] $repo, [string] $ref)
    $name = if ($ref) { $ref } else { $CedalionRelease }
    $lines = @(& git ls-remote $repo 2>$null)
    if ($LASTEXITCODE -ne 0) { Fail "could not read $repo. Check the address and your network, and run again." }
    $refs = New-Object 'System.Collections.Generic.Dictionary[string,string]'  # ref names are case-sensitive
    foreach ($line in $lines) {
        $sha, $refName = ([string] $line) -split "`t", 2
        if ($refName -and -not $refs.ContainsKey($refName)) { $refs[$refName] = $sha }
    }
    if (-not $ref -and $CedalionRelease -match '^v(\d+)\.(\d+)\.(\d+)$') {
        $bm = [int] $Matches[1]; $bn = [int] $Matches[2]; $bp = [int] $Matches[3]; $best = ''
        foreach ($key in $refs.Keys) {
            if ($key -match '^refs/tags/(v(\d+)\.(\d+)\.(\d+))$') {
                $t = $Matches[1]; $m = [int] $Matches[2]; $n = [int] $Matches[3]; $p = [int] $Matches[4]
                if ($m -gt $bm -or ($m -eq $bm -and ($n -gt $bn -or ($n -eq $bn -and $p -gt $bp)))) {
                    $bm = $m; $bn = $n; $bp = $p; $best = $t
                }
            }
        }
        if ($best) {
            Fail "this installer is for $CedalionRelease, but $best is available. Download the latest installer from https://github.com/inhouse-application/cedalion/releases/latest/download/install.ps1 (or set CEDALION_INSTALL_REF=$CedalionRelease to install $CedalionRelease explicitly)."
        }
    }
    if ($refs.ContainsKey("refs/tags/$name")) {
        $commit = if ($refs.ContainsKey("refs/tags/$name^{}")) { $refs["refs/tags/$name^{}"] } else { $refs["refs/tags/$name"] }
        return @{ Full = "refs/tags/$name"; Commit = $commit }
    }
    if ($ref -and $refs.ContainsKey("refs/heads/$name")) {
        return @{ Full = "refs/heads/$name"; Commit = $refs["refs/heads/$name"] }
    }
    if ($ref) { Fail "$repo has no branch or tag $name. Check CEDALION_INSTALL_REF, and run again." }
    Fail "$repo has no release tag $name. Run again later, or set CEDALION_INSTALL_REF=main for the newest commit."
}

# Stop if any path added between $base and $targetCommit already exists (untracked or git-ignored) in $dir,
# or has a non-directory or link ancestor in $dir.
function Assert-IncomingClean {
    param([string] $dir, [string] $gitDir, [string] $base, [string] $targetCommit)
    $added = @(& git -C $gitDir -c core.quotePath=false diff-tree -r --no-renames --name-only --diff-filter=A $base $targetCommit 2>$null | Where-Object { $_ })
    foreach ($rel in $added) {
        $norm = $rel -replace '/', [IO.Path]::DirectorySeparatorChar
        $fullRel = Join-Path $dir $norm
        if (Get-Item -LiteralPath $fullRel -Force -ErrorAction SilentlyContinue) {
            Fail "$fullRel already exists and is not tracked by git; it is kept as it is. Move it out of the way, and run again."
        }
        $p = Split-Path -Parent $norm
        while ($p) {
            $pFull = Join-Path $dir $p
            $pItem = Get-Item -LiteralPath $pFull -Force -ErrorAction SilentlyContinue
            if ($pItem -and ($pItem.LinkType -or -not $pItem.PSIsContainer)) {
                Fail "$pFull already exists and is not a folder; it is kept as it is. Move it out of the way, and run again."
            }
            $p = Split-Path -Parent $p
        }
    }
}

# Survey a fast-forward update of existing git clone $dir against $commit ($refFull) in $repo, without touching $dir.
function Get-RepoUpdatePlan {
    param([string] $dir, [string] $repo, [string] $commit, [string] $refFull)
    $head = Get-Head $dir
    if (-not $head) { Fail "$dir has no commit checked out." }
    $dirty = @(& git -C $dir status --porcelain --untracked-files=no 2>$null | Where-Object { $_ })
    if ($LASTEXITCODE -ne 0 -or $dirty.Count -gt 0) {
        Fail "$dir has local changes to tracked files; commit or stash them, and run again."
    }
    if ($head -eq $commit) {
        return @{ Head = $head; Mode = 'same'; OldTag = ''; Changed = 0 }
    }
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('.cedalion-survey.' + [IO.Path]::GetRandomFileName())
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        git init -q --bare $tmp 2>$null | Out-Null
        $infoDir = Join-Path (Join-Path $tmp 'objects') 'info'
        New-Item -ItemType Directory -Path $infoDir -Force | Out-Null
        $objDir = Join-Path (Join-Path $dir '.git') 'objects'
        [IO.File]::WriteAllText((Join-Path $infoDir 'alternates'), "$objDir`n", (New-Object Text.UTF8Encoding $false))
        git -C $tmp fetch -q --no-tags $repo $commit 2>$null | Out-Null
        $have = ''
        if ($LASTEXITCODE -eq 0) { $have = [string] @(& git -C $tmp rev-parse -q --verify "$commit^{commit}" 2>$null)[0] }
        if ($have -ne $commit) {
            Fail "could not fetch $commit ($refFull) from $repo into $dir; check your network, and run again."
        }
        git -C $tmp merge-base --is-ancestor $commit $head 2>$null
        if ($LASTEXITCODE -eq 0) {
            return @{ Head = $head; Mode = 'ahead'; OldTag = ''; Changed = 0 }
        }
        git -C $tmp merge-base --is-ancestor $head $commit 2>$null
        if ($LASTEXITCODE -ne 0) {
            Fail "$dir has commits of its own that are not in $refFull; it is left as it is."
        }
        Assert-IncomingClean $dir $tmp $head $commit
        $changed = @(& git -C $tmp diff --name-only $head $commit 2>$null | Where-Object { $_ }).Count
        $oldTag = [string] @(& git -C $dir describe --tags --exact-match $head 2>$null)[0]
        if ($LASTEXITCODE -ne 0 -or -not $oldTag) { $oldTag = $head.Substring(0, 7) }
        return @{ Head = $head; Mode = 'ff'; OldTag = $oldTag; Changed = $changed }
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# 'install' (a new clone) or 'update' (a Cedalion clone of $repo) with the HEAD it is at; anything else stops.
function Get-TargetPlan {
    param([string] $target, [string] $repo, $ref)
    if (Test-Path -LiteralPath (Join-Path $target '.git') -PathType Container) {
        if (Test-Scrapbook $target) {
            Fail "$target is an earlier Cedalion clone, which holds a scrapbook itself (papers\ or scraps\); it is left as it is. Install into another folder: install.ps1 -Scrapbook <folder>"
        }
        if (-not ((Test-Path -LiteralPath (Join-Path $target 'SKILL.md') -PathType Leaf) -and (Test-Path -LiteralPath (Join-Path $target 'snippets') -PathType Container))) {
            Fail "$target is a git repository but not Cedalion."
        }
        $origin = Get-Origin $target
        if (-not (Test-SameRepo $origin $repo)) {
            $what = if ($origin) { $origin } else { 'a repository without origin' }
            Fail "$target is a clone of $what, not $repo. Choose another folder, or set CEDALION_INSTALL_REPO to that address to update it."
        }
        $pointer = Read-Pointer $target
        if ($pointer.State -eq 'empty') {
            Fail "$(Join-Path $target '.cedalion-scrapbook') names no folder; it is left as it is. Write the scrapbook's path in it, or remove it, and run again."
        }
        if ($pointer.State -eq 'other') {
            Fail "$(Join-Path $target '.cedalion-scrapbook') is a folder or a link, not a file; it is left as it is. Remove it, and run again."
        }
        $u = Get-RepoUpdatePlan $target $repo $ref.Commit $ref.Full
        return @{ Plan = 'update'; Head = $u.Head; Mode = $u.Mode; OldTag = $u.OldTag; Changed = $u.Changed }
    }
    if (Test-Free $target) { return @{ Plan = 'install'; Head = ''; Mode = 'install'; OldTag = ''; Changed = 0 } }
    Fail "$target exists and is not empty. Choose another folder: install.ps1 <folder>"
}

# What .cedalion-scrapbook says: @{ State = 'none' | 'named' | 'empty'; Named = absolute path }. The first
# line; ReadAllLines drops a byte order mark and CR (tools/paths.py reads it the same way). A relative
# path is read from the tool root, the folder.
function Read-Pointer {
    param([string] $target)
    $pointer = Join-Path $target '.cedalion-scrapbook'
    $item = Get-Item -LiteralPath $pointer -Force -ErrorAction SilentlyContinue
    if (-not $item) { return @{ State = 'none'; Named = '' } }
    if ($item.LinkType -or $item.PSIsContainer) { return @{ State = 'other'; Named = '' } }
    $named = ([string] @([IO.File]::ReadAllLines($pointer))[0]).Trim()
    if (-not $named) { return @{ State = 'empty'; Named = '' } }
    if ($named -eq '~' -or $named.StartsWith('~/') -or $named.StartsWith('~\')) { $named = $CedalionHome + $named.Substring(1) }
    if (-not [IO.Path]::IsPathRooted($named)) { $named = Join-Path $target $named }
    @{ State = 'named'; Named = [IO.Path]::GetFullPath($named) }
}

# Resolve the remote ref and commit that an existing clone at $book tracks in $bookRepo.
function Get-BookRef {
    param([string] $book, [string] $bookRepo)
    $lines = @(& git ls-remote --symref $bookRepo 2>$null)
    if ($LASTEXITCODE -ne 0) { Fail "could not read $bookRepo. Check the address and your network, and run again." }
    $refs = New-Object 'System.Collections.Generic.Dictionary[string,string]'
    $headSym = ''
    foreach ($line in $lines) {
        $text = [string] $line
        if ($text -match '^ref:\s+(\S+)\s+HEAD$') {
            $headSym = $Matches[1]
            continue
        }
        $sha, $refName = $text -split "`t", 2
        if ($refName -and -not $refs.ContainsKey($refName)) { $refs[$refName] = $sha }
    }
    $branch = [string] @(& git -C $book symbolic-ref -q --short HEAD 2>$null)[0]
    if ($LASTEXITCODE -eq 0 -and $branch) {
        $merge = [string] @(& git -C $book config --get "branch.$branch.merge" 2>$null)[0]
        $want = if ($LASTEXITCODE -eq 0 -and $merge) { $merge } else { "refs/heads/$branch" }
    } else {
        $want = if ($headSym) { $headSym } else { 'HEAD' }
    }
    if (-not $refs.ContainsKey($want)) { Fail "$bookRepo has no ref $want for $book." }
    @{ Full = $want; Commit = $refs[$want] }
}

# 'clone', 'pull' or 'keep' (with a note) for orion beside the folder, and whether to write the pointer.
function Get-BookPlan {
    param([string] $target, [string] $book, [string] $bookRepo)
    $pointer = Join-Path $target '.cedalion-scrapbook'
    $read = Read-Pointer $target
    $write = $read.State -ne 'named'
    if ($read.State -eq 'named') {
        # A scrapbook named elsewhere is the user's: only orion beside the folder is the installer's.
        if ((Get-Address $read.Named) -ne (Get-Address $book)) {
            return @{ Plan = 'keep'; Note = "Keeping the scrapbook named in ${pointer}: $($read.Named)"; Write = $false }
        }
    }
    if (Test-Path -LiteralPath (Join-Path $book '.git') -PathType Container) {
        if (Test-SameRepo (Get-Origin $book) $bookRepo) {
            $bref = Get-BookRef $book $bookRepo
            $u = Get-RepoUpdatePlan $book $bookRepo $bref.Commit $bref.Full
            return @{ Plan = 'pull'; Note = ''; Write = $write; Ref = $bref; Head = $u.Head; Mode = $u.Mode; OldTag = $u.OldTag; Changed = $u.Changed }
        }
        return @{ Plan = 'keep'; Note = "$book is another repository; it is left as it is and not used. The tools are installed alone."; Write = $false }
    }
    if (Test-Free $book) { return @{ Plan = 'clone'; Note = ''; Write = $write } }
    @{ Plan = 'keep'; Note = "$book exists and is not a clone; it is left as it is and not used. The tools are installed alone."; Write = $false }
}

function Get-LinkTarget {
    param($item)
    # Windows PowerShell 5.1 returns the target as an array, PowerShell 7 as a string.
    $path = [string] @($item.Target)[0]
    if ($path.StartsWith('\\?\')) { $path = $path.Substring(4) }
    $path.TrimEnd('\', '/')
}

# What is at the skill link $link: 'ours' (a link to the folder), 'taken', or 'free'.
# What is at the skill link $link: 'ours' (a link whose target's physical form is the folder's), 'taken'
# (anything else: a folder, a file, a link elsewhere or to nowhere), or 'free'.
function Get-LinkState {
    param([string] $link, [string] $target)
    $item = Get-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue
    if ($item -and $item.LinkType -and (Test-Path -LiteralPath $target -PathType Container) -and
            ((Get-PhysicalPath $link) -eq $target)) { return 'ours' }
    if ($item) { return 'taken' }
    'free'
}

# --- Apply: writes only where the plan says ----------------------------------------------------

# A clone of $repo at $commit (on $branch when given, else detached) moved into the free folder $dir:
# made in a temporary folder beside it and moved once it is at that commit and holds $must. When
# anything fails, the temporary folder and the folders made above $dir are removed, and it returns $false.
function New-CloneAt {
    param([string] $repo, [string] $dir, [string] $commit, [string] $branch, [string] $must)
    $made = @()
    $d = Split-Path -Parent $dir
    while ($d -and -not (Test-Path -LiteralPath $d)) { $made += $d; $d = Split-Path -Parent $d }
    $parent = Split-Path -Parent $dir
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $tmp = Join-Path $parent ('.cedalion-install.' + [IO.Path]::GetRandomFileName())
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $clone = Join-Path $tmp 'clone'
    $ok = $false
    git -c advice.detachedHead=false clone --no-checkout --config core.autocrlf=false $repo $clone | Out-Host
    if ($LASTEXITCODE -eq 0) {
        if ($branch) {
            git -C $clone checkout -q -B $branch $commit | Out-Host
            if ($LASTEXITCODE -eq 0) { git -C $clone branch -q "--set-upstream-to=origin/$branch" $branch | Out-Host }
        } elseif ($commit) {
            git -C $clone -c advice.detachedHead=false checkout -q --detach $commit | Out-Host
        } else {
            git -C $clone checkout -q | Out-Host
        }
        if ($LASTEXITCODE -eq 0) {
            $ok = ((-not $commit) -or ((Get-Head $clone) -eq $commit)) -and
                ((-not $must) -or (Test-Path -LiteralPath (Join-Path $clone $must)))
        }
    }
    if ($ok) {
        if (Test-Path -LiteralPath $dir) { [IO.Directory]::Delete($dir, $false) }
        Move-Item -LiteralPath $clone -Destination $dir
        [IO.Directory]::Delete($tmp, $false)
        return $true
    }
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    foreach ($d in $made) {
        try { [IO.Directory]::Delete($d, $false) } catch { break }
    }
    $false
}

function Install-Target {
    param([string] $target, [string] $repo, $ref, $plan)
    Step "Getting Cedalion $($ref.Full) ($($ref.Commit)) into $target"
    $commit = $ref.Commit
    if ($plan.Plan -eq 'install') {
        if (-not (Test-Free $target)) { Fail "$target changed during the install; run again." }
        $branch = if ($ref.Full.StartsWith('refs/heads/')) { $ref.Full.Substring(11) } else { '' }
        if (-not (New-CloneAt $repo $target $commit $branch 'SKILL.md')) {
            Fail "could not clone $($ref.Full) of $repo as $commit with a SKILL.md. Check the address and your network, and run again."
        }
        return
    }
    if ((Get-Head $target) -ne $plan.Head) { Fail "$target changed during the install; run again." }
    if ($plan.Mode -eq 'same') {
        Write-Host "$target is at $($ref.Full) already."
        return
    }
    if ($plan.Mode -eq 'ahead') {
        Write-Host "$target is ahead of $($ref.Full); it is left there (an install never moves a clone back)."
        return
    }
    $dirty = @(& git -C $target status --porcelain --untracked-files=no 2>$null | Where-Object { $_ })
    if ($LASTEXITCODE -ne 0 -or $dirty.Count -gt 0) {
        Fail "$target has local changes to tracked files; commit or stash them, and run again."
    }
    git -C $target fetch -q --no-tags --no-write-fetch-head origin $commit | Out-Host
    $have = ''
    if ($LASTEXITCODE -eq 0) { $have = [string] @(& git -C $target rev-parse -q --verify "$commit^{commit}" 2>$null)[0] }
    if ($have -ne $commit) { Fail "could not fetch $commit ($($ref.Full)) from $repo into $target; check your network, and run again." }
    Assert-IncomingClean $target $target $plan.Head $commit
    git -C $target merge -q --no-overwrite-ignore --ff-only $commit | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "could not move $target forward to $($ref.Full); commit or stash local changes (or it has commits of its own), and run again." }
    $newName = if ($env:CEDALION_INSTALL_REF) { $env:CEDALION_INSTALL_REF } else { $CedalionRelease }
    Write-Host "Updated ${target}: $($plan.OldTag) -> $newName ($($plan.Changed) files changed)"
    Write-Host "Release notes: https://github.com/inhouse-application/cedalion/releases/tag/$CedalionRelease"
}

function Install-Book {
    param([string] $target, [string] $book, [string] $bookRepo, $plan)
    Step 'Getting the scrapbook'
    if ($plan.Plan -eq 'keep') {
        Write-Host $plan.Note
        return
    }
    if ($plan.Plan -eq 'pull') {
        if ((Get-Head $book) -ne $plan.Head) { Fail "$book changed during the install; run again." }
        if ($plan.Mode -eq 'same') {
            Write-Host "$book is at $($plan.Ref.Full) already."
        } elseif ($plan.Mode -eq 'ahead') {
            Write-Host "$book is ahead of $($plan.Ref.Full); it is left there (an install never moves a clone back)."
        } else {
            $dirty = @(& git -C $book status --porcelain --untracked-files=no 2>$null | Where-Object { $_ })
            if ($LASTEXITCODE -ne 0 -or $dirty.Count -gt 0) {
                Fail "$book has local changes to tracked files; commit or stash them, and run again."
            }
            $bCommit = $plan.Ref.Commit
            git -C $book fetch -q --no-tags --no-write-fetch-head origin $bCommit | Out-Host
            $have = ''
            if ($LASTEXITCODE -eq 0) { $have = [string] @(& git -C $book rev-parse -q --verify "$bCommit^{commit}" 2>$null)[0] }
            if ($have -ne $bCommit) { Fail "could not fetch $bCommit ($($plan.Ref.Full)) from $bookRepo into $book; check your network, and run again." }
            Assert-IncomingClean $book $book $plan.Head $bCommit
            git -C $book merge -q --no-overwrite-ignore --ff-only $bCommit | Out-Host
            if ($LASTEXITCODE -ne 0) { Fail "could not move $book forward to $($plan.Ref.Full); commit or stash local changes (or it has commits of its own), and run again." }
            Write-Host "Updated ${book}: $($plan.OldTag) -> $($bCommit.Substring(0, 7)) ($($plan.Changed) files changed)"
        }
    } else {
        if (-not (Test-Free $book)) {
            Write-Host "$book changed during the install; it is left as it is."
            return
        }
        if (-not (New-CloneAt $bookRepo $book '' '' '')) {
            Write-Host "Could not clone the scrapbook $bookRepo (it is private: ask the owner for access). The tools are installed alone; run this again with -Scrapbook once you have access."
            return
        }
    }
    if ($plan.Write) {
        $pointer = Join-Path $target '.cedalion-scrapbook'
        # UTF-8 without a byte order mark in both PowerShell versions (Set-Content differs between them).
        [IO.File]::WriteAllText($pointer, "$book`n", (New-Object Text.UTF8Encoding $false))
        Write-Host "Scrapbook: $book (written in $pointer)"
    }
}

# Make, keep or leave each skill link, as surveyed; with -Unregister, remove the links to the folder.
function Set-Skills {
    param([string] $target, [bool] $unregister)
    foreach ($dot in @('.claude', '.agents')) {
        $parent = Join-Path (Join-Path $CedalionHome $dot) 'skills'
        $link = Join-Path $parent 'cedalion'
        $state = Get-LinkState $link $target
        if ($state -eq 'ours') {
            if ($unregister) {
                # Removes the junction only; Remove-Item -Recurse would follow it into the clone.
                [IO.Directory]::Delete($link, $false)
                Write-Host "Unregistered $link"
            } else {
                Write-Host "Already registered: $link -> $target"
            }
        } elseif ($state -eq 'taken') {
            Write-Host "Skipped existing path: $link"
        } elseif (-not $unregister) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
            # Junctions need no administrator or Developer Mode. PowerShell on macOS and Linux has no
            # junctions, so a symbolic link stands in there (used only to test this script).
            $type = if ([Environment]::OSVersion.Platform -eq 'Win32NT') { 'Junction' } else { 'SymbolicLink' }
            New-Item -ItemType $type -Path $link -Value $target | Out-Null
            Write-Host "Registered $link -> $target"
        }
    }
}

# --- The run ---------------------------------------------------------------------------------------

function Install-Cedalion {
    param([string] $Folder, [bool] $Scrapbook, [bool] $Unregister)
    $ErrorActionPreference = 'Continue'  # git and pixi write progress to stderr; exit codes are checked
    $refName = $env:CEDALION_INSTALL_REF
    $repo = if ($env:CEDALION_INSTALL_REPO) { $env:CEDALION_INSTALL_REPO } else { 'https://github.com/inhouse-application/cedalion.git' }
    $bookRepo = if ($env:CEDALION_INSTALL_SCRAPBOOK_REPO) { $env:CEDALION_INSTALL_SCRAPBOOK_REPO } else { 'https://github.com/inhouse-application/orion.git' }
    if (-not $Folder) { $Folder = Join-Path $CedalionHome 'cedalion' }
    # The survey resolves every path and address once, against the start folder (the PowerShell location,
    # which the process's working directory does not follow); from here on only these values are used.
    $target = Get-PhysicalPath $Folder
    $repo = Get-Address $repo
    $bookRepo = Get-Address $bookRepo
    $book = Join-Path (Split-Path -Parent $target) 'orion'

    if ($Unregister) {
        Set-Skills $target $true
        return
    }

    # Where winget and the official installers put Git and pixi (user or machine scope); a new
    # window would find them on PATH, this one would not.
    $pixiHome = if ($env:PIXI_HOME) { $env:PIXI_HOME } else { "$CedalionHome\.pixi" }
    $env:PATH = (@($env:PATH, "$pixiHome\bin", "$env:LOCALAPPDATA\Programs\Git\cmd", "$env:ProgramFiles\Git\cmd",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links") -join [IO.Path]::PathSeparator)

    Step 'Checking git'
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            Fail 'git is not available, and neither is winget to install it. Install Git from https://git-scm.com/download/win (or "App Installer" from the Microsoft Store for winget), then run this again.'
        }
        Write-Host 'git not found; installing Git for Windows for this user with winget'
        winget install --id Git.Git --exact --source winget --scope user --accept-source-agreements --accept-package-agreements
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Fail 'git did not install. Install it from https://git-scm.com/download/win and run this again.'
        }
    }
    git --version

    Step 'Planning'
    $ref = Get-RefCommit $repo $refName
    $targetPlan = Get-TargetPlan $target $repo $ref
    Write-Host "folder ${target}: $($targetPlan.Plan) to $($ref.Full) ($($ref.Commit))"
    $bookPlan = $null
    if ($Scrapbook) {
        $bookPlan = Get-BookPlan $target $book $bookRepo
        Write-Host "scrapbook ${book}: $($bookPlan.Plan)"
    }

    Step 'Checking pixi'
    if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
        Write-Host 'pixi not found; installing it from https://pixi.sh (official installer)'
        # In a child process: the official installer may exit, which would end this one too.
        $shell = (Get-Process -Id $PID).Path
        & $shell -NoProfile -ExecutionPolicy ByPass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12; irm -UseBasicParsing https://pixi.sh/install.ps1 | iex"
    }
    if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
        Fail 'pixi did not install. Install it from https://pixi.sh and run this again.'
    }
    pixi --version

    Install-Target $target $repo $ref $targetPlan
    Set-Location -LiteralPath $target
    Set-Skills $target $false
    if ($Scrapbook) {
        Install-Book $target $book $bookRepo $bookPlan
    }

    Step 'Installing the environment (pixi install --locked)'
    pixi install --locked
    if ($LASTEXITCODE -ne 0) { Fail 'pixi install --locked failed; see above.' }

    Step 'Checking (pixi run check)'
    pixi run check --quiet
    if ($LASTEXITCODE -ne 0) { Fail 'the check reported errors; see above.' }

    Write-Host @"

Cedalion is installed in $target.

  cd "$target"
  pixi run check            # validate files; prints each scrap's level when a scrapbook is set up
  pixi run render-snippets  # run every plotting snippet

Open a new terminal if 'pixi' is not found there (the pixi installer adds it to your user PATH).
Optional next steps are in README.md: the Zotero plugin (zotero-plugin\README.md), Tolaria cards,
and the PDF caption tools.
"@
}

$cedalionStart = Get-Location
try {
    Install-Cedalion -Folder $Folder -Scrapbook $Scrapbook.IsPresent -Unregister $Unregister.IsPresent
    $global:LASTEXITCODE = 0
} catch {
    Write-Host "`n$($_.Exception.Message)" -ForegroundColor Red
    $global:LASTEXITCODE = 1
    if (-not $PSCommandPath) { Set-Location -LiteralPath $cedalionStart.Path }
    exit 1
} finally {
    # Through iex this runs in the caller's session: leave its location as it was.
    if (-not $PSCommandPath) { Set-Location -LiteralPath $cedalionStart.Path }
}
