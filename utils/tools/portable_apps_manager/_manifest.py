"""Install manifests - what the tool wrote into each app folder.

One JSON file per app in <root>/portable_apps.manifests/<name>.json, written after every install
or update: the archive's files with their size and CRC32. The next update compares the folder
against it to tell apart
    files the tool installed and nobody changed   -> safe to overwrite / remove
    files the tool installed that were edited     -> kept unless the user says otherwise
    files the tool never installed (not listed)   -> app / user data, left alone
An app without a manifest (installed before manifests existed) is planned the old way until its
next install writes one.
"""
import json
import os
from dataclasses import dataclass, field

MANIFEST_DIR = 'portable_apps.manifests'
FORMAT = 1
_BAD_CHARS = set('\\/:*?"<>|')


@dataclass
class FileRec:
    size: int
    crc32: int


@dataclass
class Manifest:
    app: str
    version: str
    asset: str
    installed_on: str
    files: dict[str, FileRec] = field(default_factory=dict)   # rel ('/'-separated) -> record

    def lookup(self) -> dict[str, FileRec]:
        """{rel.lower(): record} - folder paths are compared case-insensitively, like on disk."""
        return {rel.lower(): rec for rel, rec in self.files.items()}


def manifest_path(root: str, name: str) -> str:
    if not name or set(name) & _BAD_CHARS or name.strip(' .') != name:
        raise ValueError(f'App name "{name}" can\'t be used as a file name (no \\ / : * ? " < > |, '
                         'no leading/trailing space or dot)')
    return os.path.join(root, MANIFEST_DIR, name + '.json')


def load(root: str, name: str) -> Manifest | None:
    """The app's manifest, or None if it has none (or it can't be read - then it is rebuilt on the
    next install, and the plan falls back to the no-manifest behaviour meanwhile)."""
    path = manifest_path(root, name)
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        files = {rel: FileRec(size=int(r['size']), crc32=int(r['crc32'], 16)) for rel, r in d['files'].items()}
        return Manifest(app=d.get('app', name), version=d.get('version', ''), asset=d.get('asset', ''),
                        installed_on=d.get('installed_on', ''), files=files)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save(root: str, m: Manifest) -> str:
    path = manifest_path(root, m.app)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    d = {'format': FORMAT, 'app': m.app, 'version': m.version, 'asset': m.asset, 'installed_on': m.installed_on,
         'files': {rel: {'size': r.size, 'crc32': f'{r.crc32:08x}'}
                   for rel, r in sorted(m.files.items(), key=lambda kv: kv[0].lower())}}
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=1)
        f.write('\n')
    os.replace(tmp, path)
    return path


def delete(root: str, name: str) -> None:
    try:
        os.remove(manifest_path(root, name))
    except FileNotFoundError:
        pass
