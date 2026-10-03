"""Fetch .ttf fonts from a GitHub repo (default: karnyadavdev/Fonts).

Stdlib-only so no new entry is needed in requirements.txt.
Uses the public GitHub git-trees API to list files and
raw.githubusercontent.com to download.

Typical repo layout expected:
    <Family Folder>/<FontFile>.ttf
e.g. Fonts repo:
    "Fira Sans & Code/FiraSans-Regular.ttf"
    "SF Pro Text & Mono/SFProText-Regular.ttf"
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FONTS_REPO = os.environ.get("FONTWIZARD_FONTS_REPO", "karnyadavdev/Fonts")
DEFAULT_FONTS_BRANCH = os.environ.get("FONTWIZARD_FONTS_BRANCH", "main")

TREES_API_TEMPLATE = "https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
RAW_BASE_TEMPLATE = "https://raw.githubusercontent.com/{repo}/{branch}/"

TIMEOUT_S = 20


@dataclass(frozen=True)
class RemoteFont:
    """One .ttf file hosted in the GitHub fonts repo."""

    repo_path: str  # e.g. "SF Pro Text & Mono/SFProText-Regular.ttf"
    name: str  # e.g. "SFProText-Regular.ttf"
    folder: str  # e.g. "SF Pro Text & Mono" ("" if at root)
    download_url: str
    size: int = 0

    @property
    def display(self) -> str:
        if self.folder:
            return f"{self.folder} / {self.name}"
        return self.name


def _api_request(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "FontWizard",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ValueError(
                f"Fonts repo not found or branch missing: {url}. "
                "Check the repo name/branch (default karnyadavdev/Fonts@main)."
            ) from exc
        if exc.code == 403:
            raise ValueError(
                "GitHub API rate limit reached. Try again in a few minutes "
                "or pick a local .ttf file instead."
            ) from exc
        raise ValueError(f"GitHub request failed ({exc.code}): {url}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(
            f"Could not reach github.com. Check your internet connection. ({exc.reason})"
        ) from exc


def raw_url_for(repo: str, branch: str, repo_path: str) -> str:
    quoted = "/".join(urllib.parse.quote(part) for part in Path(repo_path).parts)
    return f"{RAW_BASE_TEMPLATE.format(repo=repo, branch=branch)}{quoted}"


def list_remote_fonts(
    repo: str | None = None,
    branch: str | None = None,
    timeout: int = TIMEOUT_S,
) -> list[RemoteFont]:
    """List every .ttf file in the GitHub fonts repo."""
    global TIMEOUT_S
    repo = repo or DEFAULT_FONTS_REPO
    branch = branch or DEFAULT_FONTS_BRANCH
    old_timeout = TIMEOUT_S
    TIMEOUT_S = timeout
    try:
        data = _api_request(TREES_API_TEMPLATE.format(repo=repo, branch=branch))
    finally:
        TIMEOUT_S = old_timeout

    tree = data.get("tree", [])
    # GitHub returns truncated=true when repo is huge; fonts repo is tiny so warn.
    if data.get("truncated"):
        pass  # still return what we got; best-effort

    fonts: list[RemoteFont] = []
    for entry in tree:
        if entry.get("type") != "blob":
            continue
        path = entry.get("path", "")
        if not path.lower().endswith(".ttf"):
            continue
        p = Path(path)
        fonts.append(
            RemoteFont(
                repo_path=path,
                name=p.name,
                folder=str(p.parent) if str(p.parent) != "." else "",
                download_url=raw_url_for(repo, branch, path),
                size=int(entry.get("size", 0) or 0),
            )
        )
    fonts.sort(key=lambda f: (f.folder.lower(), f.name.lower()))
    return fonts


def get_cache_dir(custom_dir: str | os.PathLike | None = None) -> Path:
    """Local folder where GitHub fonts are cached."""
    if custom_dir:
        cache = Path(custom_dir)
    else:
        try:
            from paths import RuntimePaths

            cache = RuntimePaths.discover().local_root / "github_fonts"
        except Exception:
            base = os.environ.get("LOCALAPPDATA") or str(Path.home())
            cache = Path(base) / "Font Wizard" / "github_fonts"
    # Split per repo-folder to keep sibling detection working:
    # detect_weight_overrides() scans the selected file's folder,
    # so family members must live side-by-side.
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _safe_folder_name(folder: str) -> str:
    # Keep human-readable but filesystem-safe.
    cleaned = "".join(c if c.isalnum() or c in (" ", "-", "_", "&", ".") else "_" for c in folder).strip()
    return cleaned or "Root"


_CHUNK = 262144  # 256 KB per read: fewer syscalls, same progress granularity.


def download_remote_font(
    font: RemoteFont,
    dest_dir: str | os.PathLike | None = None,
    progress=None,
    timeout: int = 20,
    attempts: int = 3,
) -> Path:
    """Download a single RemoteFont to cache, return the local .ttf path.

    Fonts are small (KB), so a failed attempt just deletes the partial and
    restarts cleanly — no resume machinery. The finished file is
    size-verified before it replaces any previous copy, so a truncated
    transfer can never become a font.
    """
    cache_root = get_cache_dir(dest_dir)
    target_dir = cache_root / _safe_folder_name(font.folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / font.name

    # Re-use cached file when size matches (avoids re-download).
    if target.exists() and font.size and target.stat().st_size == font.size:
        return target

    req = urllib.request.Request(
        font.download_url,
        headers={"User-Agent": "FontWizard"},
    )
    tmp = target.with_suffix(f"{target.suffix}.{os.getpid()}_{uuid.uuid4().hex[:6]}.part")
    expected = int(font.size or 0)
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as out:
                total = resp.headers.get("Content-Length")
                total = int(total) if total and total.isdigit() else expected
                done = 0
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress and total:
                        try:
                            # Cap at 99: 100 is only reported once the file
                            # is verified and in place, so the bar can never
                            # fake-finish.
                            progress(min(99, int(done * 100 / total)), font.name)
                        except Exception:
                            pass
            if expected and tmp.stat().st_size != expected:
                raise OSError("incomplete file")
            tmp.replace(target)
            return target
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            if attempt + 1 < max(1, attempts):
                try:
                    time.sleep(min(5, 1 + attempt))
                except Exception:
                    pass
                continue
            raise ValueError(f"Download failed for {font.display}: {exc}") from exc
    raise ValueError(f"Download failed for {font.display}: {last_error}")


def download_family(
    selected: RemoteFont,
    all_fonts: list[RemoteFont],
    dest_dir: str | os.PathLike | None = None,
    progress=None,
) -> list[Path]:
    """Download the selected font + all .ttf siblings in the same folder.

    Returns local paths. Downloading siblings matters because
    FontWizard auto-detects bold/italic/etc. by scanning the folder
    of the primary file (see font_detection.detect_weight_overrides).
    """
    family = [f for f in all_fonts if f.folder == selected.folder] or [selected]
    # Put selected first so caller can use result[0] as primary.
    family.sort(key=lambda f: (f != selected, f.name.lower()))
    local_paths: list[Path] = []
    for i, font in enumerate(family):
        def _cb(pct, _name, _i=i, _n=len(family)):
            if progress:
                try:
                    overall = int((_i * 100 + pct) / _n)
                    progress(overall, font.name)
                except Exception:
                    pass

        local_paths.append(download_remote_font(font, dest_dir=dest_dir, progress=_cb))
    return local_paths


@dataclass(frozen=True)
class RemoteFolder:
    """A folder in the GitHub repo that contains .ttf files."""

    folder: str  # repo-relative dir, e.g. "Fira Sans & Code" ("" if files sit at root)
    fonts: tuple[RemoteFont, ...]

    @property
    def name(self) -> str:
        return self.folder or "Fonts"

    @property
    def count(self) -> int:
        return len(self.fonts)

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.fonts)

    @property
    def regular_font(self) -> RemoteFont:
        return pick_regular_remote(self.fonts)


def list_remote_folders(
    repo: str | None = None,
    branch: str | None = None,
    timeout: int = TIMEOUT_S,
) -> list[RemoteFolder]:
    """Group .ttf files in the GitHub fonts repo by their containing folder."""
    fonts = list_remote_fonts(repo=repo, branch=branch, timeout=timeout)
    grouped: dict[str, list[RemoteFont]] = {}
    for font in fonts:
        grouped.setdefault(font.folder, []).append(font)

    folders: list[RemoteFolder] = []
    for folder, members in grouped.items():
        # Put a likely-Regular file first so callers can default to it.
        members.sort(
            key=lambda f: (
                0 if "regular" in f.name.lower() else 1,
                f.name.lower(),
            )
        )
        folders.append(RemoteFolder(folder=folder, fonts=tuple(members)))
    folders.sort(key=lambda f: f.name.lower())
    return folders


def download_folder(
    folder: RemoteFolder,
    dest_dir: str | os.PathLike | None = None,
    progress=None,
    max_workers: int = 4,
) -> list[Path]:
    """Download every .ttf in a repo folder. Returns local paths (input order preserved).

    All-or-nothing: every file is retried until it lands — a folder with a
    missing member is never returned. Files download concurrently (4
    workers; raising that invites throttling), and any file that still
    fails gets a full second pass before the folder is allowed to fail.
    """
    members = list(folder.fonts)
    if not members:
        raise ValueError(f"Folder '{folder.name}' contains no .ttf files.")

    total = len(members)
    lock = threading.Lock()
    state = {"done": 0, "pct": [0] * total}

    def _report(index, pct, name):
        if not progress:
            return
        with lock:
            state["pct"][index] = max(0, min(100, int(pct)))
            overall = int(sum(state["pct"]) / total)
        try:
            progress(overall, name)
        except Exception:
            pass

    results: list[Path | None] = [None] * total

    def _worker(index: int, font: RemoteFont) -> None:
        def _cb(pct, _name=None):
            _report(index, pct, font.name)

        results[index] = download_remote_font(font, dest_dir=dest_dir, progress=_cb)
        _report(index, 100, font.name)

    def _run_pass(indices):
        errs: list[str] = []
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(indices)))) as pool:
            futures = [pool.submit(_worker, i, members[i]) for i in indices]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    errs.append(str(exc))
        return errs

    errors = _run_pass(list(range(total)))
    failed = [i for i, path in enumerate(results) if path is None]
    if failed:
        # Second pass with fresh worker threads (hence fresh keep-alive
        # connections) for anything the first pass couldn't land.
        errors = _run_pass(failed)
        failed = [i for i, path in enumerate(results) if path is None]

    if failed:
        detail = errors[0] if errors else "unknown error"
        raise ValueError(
            f"{len(failed)} of {total} fonts failed to download: {detail}"
        )

    return [path for path in results if path is not None]


def pick_regular(local_paths: list[Path]) -> Path:
    """Choose the 'regular' face from downloaded files for weight auto-selection.

    Uses the app's own font classifier; falls back to the first static .ttf.
    """
    if not local_paths:
        raise ValueError("No font files were downloaded.")

    try:
        from font_detection import inspect_font, classify_weight
    except Exception:
        return local_paths[0]

    best: Path | None = None
    best_score = float("-inf")
    for path in local_paths:
        try:
            metadata = inspect_font(path)
        except Exception:
            continue
        if metadata.is_variable:
            continue
        weight = classify_weight(path, metadata)
        score = 0.0
        if weight == "regular":
            score += 100.0
        if metadata.weight_class == 400:
            score += 50.0
        elif metadata.weight_class:
            score -= abs(metadata.weight_class - 400) / 100.0
        if not metadata.is_italic:
            score += 25.0
        # The selected "regular" seeds the UI font slot, and a folder may mix
        # families (e.g. "Fira Sans & Code" holds FiraSans + FiraCode). A
        # monospace face must not win over a proportional one, or validation
        # reports more than one UI family.
        if metadata.is_monospace:
            score -= 500.0
        if score > best_score:
            best_score = score
            best = path

    return best or local_paths[0]


def pick_regular_remote(fonts: tuple[RemoteFont, ...] | list[RemoteFont]) -> RemoteFont:
    """Choose the best regular non-monospace face from remote fonts for preview.

    Prefers proportional (UI) face over monospace/code, static regular face over
    variable or styled weights (bold, italic, light, etc.).
    """
    if not fonts:
        raise ValueError("No remote fonts provided.")

    def score(name: str) -> int:
        n = name.lower()
        pts = 0
        if "mono" in n or "code" in n:
            pts -= 1000
        if "italic" in n or "oblique" in n:
            pts -= 500
        if any(w in n for w in ("bold", "black", "heavy", "extrabold", "semibold", "light", "thin", "extralight", "medium")):
            pts -= 200
        if "variable" in n:
            pts -= 100
        if "regular" in n:
            pts += 300
        return pts

    return max(fonts, key=lambda f: score(f.name))
