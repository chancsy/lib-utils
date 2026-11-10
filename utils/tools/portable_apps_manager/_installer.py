"""Download -> plan -> apply, comparing the archive listing against the installed folder.

plan() downloads the asset and reads the archive's listing (path, size, CRC32) without extracting
anything, then classifies every file:
    new        in the archive, not on disk
    changed    on disk, but size or CRC32 differ
    unchanged  identical - never touched
    preserved  matches the app's 'preserve' globs - never overwritten or removed
    stale      on disk, not in the archive - removed only if the caller says so
    locked     changed/stale/modified files that are open in a running program
With the app's install manifest (_manifest.py; what the last install wrote), also:
    changed    only when the file on disk is still what the last install wrote
    modified   in the archive and differs on disk, but was edited since the last install (or the
               last install didn't write it) - kept unless the caller says to overwrite it
    user       on disk, not in the archive, not written by the last install - app / user data,
               never touched
    stale      only files the last install wrote; `edited` marks those changed since
apply() extracts only new + changed (+ the modified files the caller chose) into the folder and
removes the stale files the caller chose; it refuses to start while any file it would touch is
locked.
"""
import fnmatch
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
import zlib
from dataclasses import dataclass, field
from typing import Callable

from ._http import session
from ._manifest import FileRec
from ._sources import Asset

ProgressCb = Callable[[int, int], None]   # (done_bytes, total_bytes)
_CHUNK = 1 << 20


class InstallError(Exception):
    pass


# ── download ──────────────────────────────────────────────────────────────────

_RETRY_WAITS = (3, 10)   # seconds before the 2nd and 3rd attempt
# Disabled pending investigation of the github.com release-link 504s (see README, Limits and known issues).
_GITHUB_API_FALLBACK = False


def download(asset: Asset, dest_dir: str, progress: ProgressCb | None = None) -> str:
    """Stream asset to dest_dir. Server errors (5xx) and dropped connections are retried with the
    waits in _RETRY_WAITS; client errors (404, 403, ...) fail at once. With _GITHUB_API_FALLBACK on,
    retries of GitHub assets go through the API asset URL (asset.api_url) instead."""
    import time
    import requests
    path = os.path.join(dest_dir, asset.name)
    for attempt in range(len(_RETRY_WAITS) + 1):
        sha = hashlib.sha256()
        done = 0
        url, headers = asset.url, {}
        if attempt and asset.api_url and _GITHUB_API_FALLBACK:
            url, headers = asset.api_url, {'Accept': 'application/octet-stream'}
        try:
            with session().get(url, headers=headers, stream=True, timeout=30) as r:
                r.raise_for_status()
                total = int(r.headers.get('Content-Length') or asset.size or 0)
                with open(path, 'wb') as f:
                    for chunk in r.iter_content(_CHUNK):
                        f.write(chunk)
                        sha.update(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
            break
        except requests.RequestException as e:
            status = e.response.status_code if getattr(e, 'response', None) is not None else None
            if (status is not None and status < 500) or attempt == len(_RETRY_WAITS):
                tries = f' (after {attempt + 1} attempts)' if attempt else ''
                raise InstallError(f'Download failed{tries}: {e}') from None
            time.sleep(_RETRY_WAITS[attempt])
    if asset.sha256 and sha.hexdigest() != asset.sha256.lower():
        raise InstallError(f'Download corrupted: SHA-256 of {asset.name} does not match the release digest')
    return path


# ── archive listing / extraction ──────────────────────────────────────────────

@dataclass
class Entry:
    rel: str      # path inside the app folder, '/'-separated (wrapping top folder stripped)
    member: str   # name inside the archive
    size: int
    crc: int | None


def _find_7z() -> str | None:
    if p := shutil.which('7z'):
        return p
    for c in (r'C:\Program Files\7-Zip\7z.exe', r'C:\Program Files (x86)\7-Zip\7z.exe'):
        if os.path.isfile(c):
            return c
    return None


def _safe_rel(name: str) -> str:
    rel = name.replace('\\', '/').lstrip('/')
    parts = rel.split('/')
    if '..' in parts or ':' in parts[0]:
        raise InstallError(f'Unsafe path in archive: {name}')
    return rel


def _strip_top(archive: '_Archive', entries: list[Entry], dir_names: list[str]) -> list[Entry]:
    """Drop a single folder that wraps the whole archive (like utils.unwrap_single_dir_archive).
    Its name is kept as archive.top (e.g. 'node-v26.13.0-win-x64') for version_from = top_folder."""
    tops = {e.rel.split('/')[0] for e in entries} | {d.split('/')[0] for d in dir_names}
    archive.top = ''
    if len(tops) == 1 and entries and all('/' in e.rel for e in entries):
        archive.top = tops.pop()
        n = len(archive.top) + 1
        for e in entries:
            e.rel = e.rel[n:]
    return entries


class _Archive:
    top = ''   # name of the single folder wrapping the archive, set by entries(); '' if none

    def entries(self) -> list[Entry]: ...
    def extract(self, entries: list[Entry], work_dir: str) -> dict[str, str]:
        """Extract the given entries; returns {rel: extracted file path}."""
        ...
    def read(self, entry: Entry) -> bytes:
        """One entry's content, in memory (used for small files such as version_file)."""
        ...


class _ZipArchive(_Archive):
    def __init__(self, path):
        self.path = path

    def entries(self):
        with zipfile.ZipFile(self.path) as z:
            infos = z.infolist()
        files = [Entry(_safe_rel(i.filename), i.filename, i.file_size, i.CRC) for i in infos if not i.is_dir()]
        return _strip_top(self, files,[_safe_rel(i.filename) for i in infos if i.is_dir()])

    def extract(self, entries, work_dir):
        out = {}
        with zipfile.ZipFile(self.path) as z:
            for e in entries:
                dst = os.path.join(work_dir, 'x', *e.rel.split('/'))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with z.open(e.member) as src, open(dst, 'wb') as f:
                    shutil.copyfileobj(src, f, _CHUNK)
                out[e.rel] = dst
        return out

    def read(self, entry):
        with zipfile.ZipFile(self.path) as z:
            return z.read(entry.member)


class _SevenZipArchive(_Archive):
    """.7z and 7-Zip self-extracting .7z.exe, through 7z.exe (no SFX code is run)."""
    def __init__(self, path):
        self.path = path
        self.exe = _find_7z()
        if not self.exe:
            raise InstallError('7-Zip (7z.exe) not found - install 7-Zip to handle .7z / .7z.exe assets')

    def _run(self, *args) -> str:
        r = subprocess.run([self.exe, *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
        if r.returncode != 0:
            raise InstallError(f'7z {args[0]} failed (exit {r.returncode}): {(r.stderr or r.stdout).strip()[:500]}')
        return r.stdout

    def entries(self):
        files, dirs = [], []
        for block in self._run('l', '-slt', '-ba', self.path).split('\n\n'):
            kv = dict(line.split(' = ', 1) for line in block.splitlines() if ' = ' in line)
            if 'Path' not in kv:
                continue
            rel = _safe_rel(kv['Path'])
            if 'D' in kv.get('Attributes', ''):
                dirs.append(rel)
            else:
                crc = kv.get('CRC', '').strip()
                files.append(Entry(rel, kv['Path'], int(kv.get('Size') or 0), int(crc, 16) if crc else None))
        return _strip_top(self, files,dirs)

    def extract(self, entries, work_dir):
        # 7z can't strip the wrapping folder or take a reliable member list (wildcard chars in names),
        # so extract everything into the work dir and pick the needed files from there.
        x = os.path.join(work_dir, 'x7')
        self._run('x', self.path, f'-o{x}', '-y')
        return {e.rel: os.path.join(x, *e.member.replace('\\', '/').split('/')) for e in entries}

    def read(self, entry):
        r = subprocess.run([self.exe, 'e', '-so', self.path, entry.member], capture_output=True)
        if r.returncode != 0:
            raise InstallError(f'7z e failed for {entry.member} (exit {r.returncode})')
        return r.stdout


class _TarArchive(_Archive):
    def __init__(self, path):
        self.path = path

    def entries(self):
        files, dirs = [], []
        with tarfile.open(self.path) as t:
            for m in t.getmembers():
                if m.isdir():
                    dirs.append(_safe_rel(m.name))
                elif m.isfile():
                    # tar has no CRC: stream the member once to compute one (no files written)
                    crc = 0
                    with t.extractfile(m) as f:
                        while chunk := f.read(_CHUNK):
                            crc = zlib.crc32(chunk, crc)
                    files.append(Entry(_safe_rel(m.name), m.name, m.size, crc))
        return _strip_top(self, files,dirs)

    def extract(self, entries, work_dir):
        out = {}
        with tarfile.open(self.path) as t:
            for e in entries:
                dst = os.path.join(work_dir, 'x', *e.rel.split('/'))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with t.extractfile(e.member) as src, open(dst, 'wb') as f:
                    shutil.copyfileobj(src, f, _CHUNK)
                out[e.rel] = dst
        return out

    def read(self, entry):
        with tarfile.open(self.path) as t, t.extractfile(entry.member) as f:
            return f.read()


class _SingleFile(_Archive):
    """A bare executable (or any non-archive asset) installed as-is."""
    def __init__(self, path):
        self.path = path

    def entries(self):
        name = os.path.basename(self.path)
        return [Entry(name, name, os.path.getsize(self.path), _file_crc(self.path))]

    def extract(self, entries, work_dir):
        return {e.rel: self.path for e in entries}

    def read(self, entry):
        with open(self.path, 'rb') as f:
            return f.read()


def open_archive(path: str) -> _Archive:
    n = path.lower()
    if n.endswith('.zip'):
        return _ZipArchive(path)
    if n.endswith(('.7z', '.7z.exe')):
        return _SevenZipArchive(path)
    if n.endswith(('.tar', '.tar.gz', '.tgz', '.tar.xz', '.txz', '.tar.bz2')):
        return _TarArchive(path)
    if n.endswith(('.msi', '.msix', '.appx', '.dmg', '.deb', '.rpm', '.appimage')):
        raise InstallError(f'{os.path.basename(path)}: installer/package format, not a portable archive')
    return _SingleFile(path)


# ── disk helpers ──────────────────────────────────────────────────────────────

def _file_crc(path: str) -> int:
    crc = 0
    with open(path, 'rb') as f:
        while chunk := f.read(_CHUNK):
            crc = zlib.crc32(chunk, crc)
    return crc


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _disk_files(folder: str) -> dict[str, str]:
    """{rel.lower(): rel} for every file under folder."""
    out = {}
    if os.path.isdir(folder):
        for dirpath, _, files in os.walk(folder):
            for f in files:
                rel = os.path.relpath(os.path.join(dirpath, f), folder).replace('\\', '/')
                out[rel.lower()] = rel
    return out


def _is_readonly(path: str) -> bool:
    return not (os.stat(path).st_mode & stat.S_IWRITE)


def is_locked(path: str) -> bool:
    """True if a running program holds the file (e.g. a running .exe or a loaded .dll)."""
    if not os.path.isfile(path) or _is_readonly(path):
        return False   # read-only files can't be probed with r+b; apply() clears the flag first
    try:
        with open(path, 'r+b'):
            return False
    except PermissionError:
        return True


def _make_writable(path: str):
    if os.path.exists(path) and _is_readonly(path):
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


def _matches_any(rel: str, globs: list[str]) -> bool:
    r = rel.lower()
    return any(fnmatch.fnmatchcase(r, g.lower()) or fnmatch.fnmatchcase(r.rsplit('/', 1)[-1], g.lower())
               for g in globs)


# ── plan / apply ──────────────────────────────────────────────────────────────

@dataclass
class Plan:
    dest: str
    version: str                                  # recorded as installed_version (see resolve_version)
    marker: str                                   # stored as installed_marker after apply
    asset: Asset
    work_dir: str
    archive: _Archive
    entries: dict[str, Entry]                     # rel -> Entry, for new + changed + modified
    all_entries: list[Entry] = field(default_factory=list)   # the whole archive listing (for the manifest)
    old_files: dict[str, FileRec] | None = None   # previous manifest {rel.lower(): rec}; None = no manifest
    new: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    user: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    edited: set[str] = field(default_factory=set)   # stale files changed since the last install
    locked: list[str] = field(default_factory=list)

    @property
    def has_manifest(self) -> bool:
        return self.old_files is not None

    def summary(self) -> str:
        parts = [f'{len(self.new)} new', f'{len(self.changed)} changed', f'{len(self.unchanged)} unchanged']
        for n, label in ((len(self.preserved), 'preserved'), (len(self.modified), 'modified locally'),
                         (len(self.user), 'user/app file(s) left alone'), (len(self.stale), 'stale'),
                         (len(self.locked), 'in use')):
            if n:
                parts.append(f'{n} {label}')
        if not self.has_manifest:
            parts.append('no install manifest yet')
        return ', '.join(parts)

    def file_records(self, removed: list[str]) -> dict[str, FileRec]:
        """The new manifest's files after apply: every archive file as shipped, plus the stale files
        that were kept (still the tool's files, so they are offered for removal again next time)."""
        out = {}
        for e in self.all_entries:
            crc = e.crc
            if crc is None:   # archive listed no CRC (7z, some empty files): compute it
                on_disk = os.path.join(self.dest, *e.rel.split('/'))
                written = e.rel in self.new or e.rel in self.changed or e.rel in self.unchanged
                crc = _file_crc(on_disk) if written and os.path.isfile(on_disk) else zlib.crc32(self.archive.read(e))
            out[e.rel] = FileRec(size=e.size, crc32=crc)
        if self.old_files:
            gone = {r.lower() for r in removed}
            for rel in self.stale:
                if rel.lower() not in gone and rel.lower() in self.old_files:
                    out[rel] = self.old_files[rel.lower()]
        return out

    def cleanup(self):
        shutil.rmtree(self.work_dir, ignore_errors=True)


def read_version_file(archive: _Archive, entries: list[Entry], version_file: str) -> str:
    """'path:key' -> value of that key=value line in the archive file.
    'path' alone -> for a key=value file, the value of the first key containing 'version' or
    'revision' (adb source.properties -> Pkg.Revision); otherwise the first non-empty line."""
    path, _, key = version_file.partition(':')
    path, key = path.strip().replace('\\', '/').lower(), key.strip()
    e = next((e for e in entries if e.rel.lower() == path), None)
    if e is None:
        raise InstallError(f'version_file: "{path}" is not in the archive')
    lines = [ln.strip() for ln in archive.read(e).decode('utf-8', errors='replace').splitlines() if ln.strip()]
    kv_line = re.compile(r'^[A-Za-z_][\w.\-]*\s*=')   # 'Pkg.Revision=37.0.1'; not '=====' separator lines
    pairs = [(k.strip(), v.strip()) for k, _, v in (ln.partition('=') for ln in lines if kv_line.match(ln))]
    if key:
        hit = next((v for k, v in pairs if k == key), None)
        if hit is None:
            raise InstallError(f'version_file: no key "{key}" in {e.rel}')
        return hit
    if lines and kv_line.match(lines[0]):
        hit = next(((k, v) for k, v in pairs if re.search(r'version|revision', k, re.IGNORECASE)), None)
        if hit is None:
            raise InstallError(f'version_file: {e.rel} is a key=value file with no version/revision key - '
                               f'name one as "{path}:<key>" (keys: {", ".join(k for k, _ in pairs[:15])})')
        return hit[1]
    if not lines:
        raise InstallError(f'version_file: {e.rel} is empty')
    return lines[0]


# 'v26.13.0', '9.0.2', '1.145.0' - dotted version, optional leading 'v'
_VERSION_IN_NAME = re.compile(r'(?<![0-9A-Za-z])v?\d+(?:\.\d+)+', re.IGNORECASE)
VERSION_FROM = ('auto', 'file', 'top_folder', 'file_name', 'date')


def _version_in(name: str) -> str:
    m = _VERSION_IN_NAME.search(name or '')
    return m.group(0) if m else ''


def resolve_version(archive: _Archive, entries: list[Entry], file_name: str, source_version: str,
                    version_from: str = 'auto', version_file: str = '') -> str:
    """The version to record as installed_version.
        file        version_file inside the archive (see read_version_file)
        top_folder  version in the folder wrapping the archive ('node-v26.13.0-win-x64' -> 'v26.13.0')
        file_name   version in the downloaded file name ('ffmpeg-9.0.2-essentials_build.zip' -> '9.0.2')
        date        the source's own version (url apps: version from the redirect URL, else Last-Modified date)
        auto        version_file if set, else top_folder, else file_name, else date
    An explicit choice that finds nothing raises InstallError instead of recording a wrong value."""
    mode = version_from or 'auto'
    if mode not in VERSION_FROM:
        raise InstallError(f'version_from: unknown "{mode}" (use {", ".join(VERSION_FROM)})')
    if mode == 'file' or (mode == 'auto' and version_file):
        if not version_file:
            raise InstallError('version_from = file, but no version file is set')
        return read_version_file(archive, entries, version_file)
    if mode in ('auto', 'top_folder'):
        if v := _version_in(archive.top):
            return v
        if mode == 'top_folder':
            raise InstallError(f'version_from = top_folder: no version in the archive\'s top folder '
                               f'"{archive.top or "(none - files are at the archive root)"}"')
    if mode in ('auto', 'file_name'):
        if v := _version_in(file_name):
            return v
        if mode == 'file_name':
            raise InstallError(f'version_from = file_name: no version in "{file_name}"')
    return source_version


def _same(path: str, size: int, crc: int | None) -> bool:
    return os.path.getsize(path) == size and (crc is None or _file_crc(path) == crc)


def plan(dest: str, version: str, asset: Asset, preserve: list[str],
         progress: ProgressCb | None = None, marker: str = '', version_file: str = '',
         version_from: str | None = None, manifest: dict[str, FileRec] | None = None) -> Plan:
    """version_from=None keeps the source's version (GitHub: the tag); see resolve_version() otherwise.
    manifest: the previous install's files ({rel.lower(): FileRec}, see Manifest.lookup), or None."""
    work_dir = tempfile.mkdtemp(prefix='portable_apps_')
    try:
        archive = open_archive(download(asset, work_dir, progress))
        entries = archive.entries()
        if version_from is not None:
            version = resolve_version(archive, entries, asset.name, version, version_from, version_file)
        if not marker:   # check_by = download: identify the file by its content
            marker = 'sha256:' + _file_sha256(os.path.join(work_dir, asset.name))
        p = Plan(dest=dest, version=version, marker=marker, asset=asset, work_dir=work_dir,
                 archive=archive, entries={}, all_entries=entries, old_files=manifest)

        def pristine(key: str, on_disk: str) -> bool:
            """Still what the last install wrote (always True without a manifest: old behaviour)."""
            if manifest is None:
                return True
            rec = manifest.get(key)
            return rec is not None and _same(on_disk, rec.size, rec.crc32)

        disk = _disk_files(dest)
        in_archive = set()
        for e in entries:
            key = e.rel.lower()
            in_archive.add(key)
            if key not in disk:
                p.new.append(e.rel)
                p.entries[e.rel] = e
                continue
            on_disk = os.path.join(dest, *disk[key].split('/'))
            if _same(on_disk, e.size, e.crc):
                p.unchanged.append(e.rel)
            elif _matches_any(e.rel, preserve):
                p.preserved.append(e.rel)
            elif pristine(key, on_disk):
                p.changed.append(e.rel)
                p.entries[e.rel] = e
            else:
                p.modified.append(e.rel)
                p.entries[e.rel] = e
        for key, rel in disk.items():
            if key in in_archive:
                continue
            if _matches_any(rel, preserve):
                p.preserved.append(rel)
            elif manifest is not None and key not in manifest:
                p.user.append(rel)
            else:
                p.stale.append(rel)
                if not pristine(key, os.path.join(dest, *rel.split('/'))):
                    p.edited.add(rel)
        for lst in (p.stale, p.user, p.modified):
            lst.sort(key=str.lower)
        p.locked = _locked(dest, p.changed + p.stale + p.modified)
        return p
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def _locked(dest: str, rels: list[str]) -> list[str]:
    return [r for r in rels if is_locked(os.path.join(dest, *r.split('/')))]


def apply(p: Plan, remove: list[str], overwrite: list[str] = ()) -> None:
    """Write new + changed files and the chosen modified files, delete the chosen stale files.
    Nothing is written if any of those files is in use."""
    remove = [r for r in remove if r in set(p.stale)]
    overwrite = [r for r in overwrite if r in set(p.modified)]
    locked = _locked(p.dest, p.changed + overwrite + remove)
    if locked:
        raise InstallError('Close the program first - files in use:\n  ' + '\n  '.join(locked))
    to_write = [p.entries[r] for r in p.new + p.changed + overwrite]
    extracted = p.archive.extract(to_write, p.work_dir)
    for e in to_write:
        dst = os.path.join(p.dest, *e.rel.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        _make_writable(dst)
        try:
            os.replace(extracted[e.rel], dst)
        except OSError:    # other volume, or the source is the downloaded file itself (_SingleFile)
            shutil.copy2(extracted[e.rel], dst)
    for rel in remove:
        f = os.path.join(p.dest, *rel.split('/'))
        _make_writable(f)
        os.remove(f)
    _prune_empty_dirs(p.dest, remove)


def _prune_empty_dirs(dest: str, removed: list[str]):
    dirs = {os.path.dirname(os.path.join(dest, *r.split('/'))) for r in removed}
    for d in sorted(dirs, key=len, reverse=True):
        while os.path.normcase(d) != os.path.normcase(dest) and os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
            d = os.path.dirname(d)


# ── remove / inspect ──────────────────────────────────────────────────────────

def delete_folder(folder: str) -> None:
    if not os.path.isdir(folder):
        return
    locked = [rel for rel in _disk_files(folder).values() if is_locked(os.path.join(folder, *rel.split('/')))]
    if locked:
        raise InstallError('Close the program first - files in use:\n  ' + '\n  '.join(locked[:20]))

    def _retry_writable(func, path, _exc):   # read-only files (e.g. git objects) block rmtree
        _make_writable(path)
        func(path)
    if sys.version_info >= (3, 12):
        shutil.rmtree(folder, onexc=_retry_writable)
    else:
        shutil.rmtree(folder, onerror=_retry_writable)


def detect_bin(folder: str) -> str:
    """Shallowest subfolder holding an .exe ('.' for the folder itself); '' if none."""
    best = None
    for dirpath, _, files in os.walk(folder):
        if any(f.lower().endswith('.exe') for f in files):
            rel = os.path.relpath(dirpath, folder).replace('\\', '/')
            key = (0 if rel == '.' else rel.count('/') + 1, rel.lower(), rel)
            best = min(best, key) if best else key
    return best[2] if best else ''
