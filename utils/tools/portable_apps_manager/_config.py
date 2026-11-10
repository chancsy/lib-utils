"""portable_apps.ini - the per-root app registry.

The ini lives in the portable-programs root itself (e.g. ~/Downloads/Programs/portable_apps.ini),
so each root carries its own list of tracked apps and their installed versions. On first use it
is written on the first save(); config.template.ini (next to this file) supplies its comment header.
"""
import configparser
import os
from dataclasses import dataclass, field

DEFAULT_ROOT = os.path.join(os.path.expanduser('~'), 'Downloads', 'Programs')
INI_NAME = 'portable_apps.ini'
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.template.ini')
_APP_PREFIX = 'app:'


@dataclass
class AppSpec:
    name: str                       # ini section is [app:<name>]
    folder: str                     # fixed folder name, relative to the root
    source: str = 'github'          # 'github' | 'url'
    # source = github
    repo: str = ''                  # 'owner/name'
    asset: str = ''                 # glob on the release asset name, or 're:<regex>'
    # source = url
    url: str = ''                   # fixed download URL (may redirect)
    check_by: str = ''              # final_url | etag | last_modified | download (see _sources.CHECK_MODES)
    version_from: str = ''          # auto (default) | file | top_folder | file_name | date (_installer.resolve_version)
    version_file: str = ''          # 'path/in/archive:key' (key=value file) or 'path' (auto key / first line); optional
    # common
    bin: str = ''                   # subfolder to add to PATH (phase 2); '.' = the app folder itself
    preserve: list[str] = field(default_factory=list)   # globs (relative paths) never overwritten or removed
    installed_version: str = ''     # shown to the user
    installed_marker: str = ''      # what update checks compare (tag / final URL path / ETag / Last-Modified)
    installed_asset: str = ''
    installed_on: str = ''

    @property
    def is_installed(self) -> bool:
        return bool(self.installed_version)

    @property
    def origin(self) -> str:
        return self.repo if self.source == 'github' else self.url

    def folder_path(self, root: str) -> str:
        return os.path.join(root, self.folder)

    def to_section(self) -> dict[str, str]:
        sec = {'source': self.source}
        if self.source == 'github':
            sec |= {'repo': self.repo, 'asset': self.asset}
        else:
            sec |= {'url': self.url, 'check_by': self.check_by, 'version_from': self.version_from or 'auto',
                    'version_file': self.version_file}
        return sec | {
            'folder': self.folder,
            'bin': self.bin,
            'preserve': ', '.join(self.preserve),
            'installed_version': self.installed_version,
            'installed_marker': self.installed_marker,
            'installed_asset': self.installed_asset,
            'installed_on': self.installed_on,
        }

    @classmethod
    def from_section(cls, name: str, sec) -> 'AppSpec':
        g = lambda k: sec.get(k, '')
        return cls(
            name=name, folder=sec.get('folder', name), source=sec.get('source', 'github'),
            repo=g('repo'), asset=g('asset'),
            url=g('url'), check_by=g('check_by'), version_from=g('version_from'), version_file=g('version_file'),
            bin=g('bin'),
            preserve=[p.strip() for p in g('preserve').split(',') if p.strip()],
            installed_version=g('installed_version'), installed_marker=g('installed_marker'),
            installed_asset=g('installed_asset'), installed_on=g('installed_on'),
        )


class AppsConfig:
    """Loads/saves <root>/portable_apps.ini.

    save_app() / delete_app() write one app at a time: they re-read the ini, replace or remove only
    that app's section and write it back, so edits made to the file since it was loaded (by hand,
    or by another copy of the tool) are kept for every other app and [settings]. save() writes the
    whole in-memory registry. changed_on_disk() tells whether the file differs from what was last
    loaded or written here."""

    def __init__(self, root: str):
        self.root = os.path.abspath(os.path.expanduser(root))
        self.path = os.path.join(self.root, INI_NAME)
        self.apps: dict[str, AppSpec] = {}
        self._settings: dict[str, str] = {}
        self._stamp = None   # (mtime_ns, size) of the file as last loaded / written; None = no file

    def exists(self) -> bool:
        return os.path.isfile(self.path)

    def _disk_stamp(self):
        try:
            st = os.stat(self.path)
            return st.st_mtime_ns, st.st_size
        except FileNotFoundError:
            return None

    def changed_on_disk(self) -> bool:
        return self._disk_stamp() != self._stamp

    def _read(self) -> configparser.ConfigParser:
        cp = self._parser()
        if self.exists():
            cp.read(self.path, encoding='utf-8')
        return cp

    def load(self) -> 'AppsConfig':
        """Read the ini; a missing ini is an empty registry (the file is only written by a save)."""
        self._stamp = self._disk_stamp()
        cp = self._read()
        self._settings = dict(cp['settings']) if cp.has_section('settings') else {}
        self.apps = {s[len(_APP_PREFIX):]: AppSpec.from_section(s[len(_APP_PREFIX):], cp[s])
                     for s in cp.sections() if s.startswith(_APP_PREFIX)}
        return self

    def save(self):
        """Write the whole in-memory registry (overwrites changes made on disk since load)."""
        cp = self._parser()
        cp['settings'] = self._settings
        for name in self.apps:
            cp[_APP_PREFIX + name] = self.apps[name].to_section()
        self._write(cp)

    def save_app(self, spec: AppSpec):
        """Add or replace spec's section in the ini as it is on disk now; other sections are kept
        as they are there, and so are keys of spec's own section that AppSpec doesn't know (added by
        hand). Afterwards self.apps is the merged registry, holding spec itself."""
        cp = self._read()
        sec = _APP_PREFIX + spec.name
        extra = {k: v for k, v in cp[sec].items() if k not in _KNOWN_KEYS} if cp.has_section(sec) else {}
        cp[sec] = spec.to_section() | extra
        self._write(cp)
        self.load()
        self.apps[spec.name] = spec

    def delete_app(self, name: str):
        """Remove name's section from the ini as it is on disk now (other sections kept)."""
        cp = self._read()
        cp.remove_section(_APP_PREFIX + name)
        self._write(cp)
        self.load()

    def _write(self, cp: configparser.ConfigParser):
        # configparser drops comments on write, so the template's comment header is re-emitted
        # on every save to keep the key reference at the top of the file. Sections are written as
        # [settings], then the apps sorted by name; keys of a section read from disk stay as they are.
        out = self._parser()
        out['settings'] = dict(cp['settings']) if cp.has_section('settings') else {}
        for sec in sorted((s for s in cp.sections() if s.startswith(_APP_PREFIX)), key=str.lower):
            out[sec] = dict(cp[sec])
        os.makedirs(self.root, exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(_template_header())
            out.write(f)
        os.replace(tmp, self.path)
        self._stamp = self._disk_stamp()

    def setting(self, key: str, default: str = '') -> str:
        return self._settings.get(key, default)

    def add(self, spec: AppSpec):
        same = next((n for n in self.apps if n.lower() == spec.name.lower()), None)   # case-insensitive:
        if same:                                                                     # names are manifest file names
            raise ValueError(f'An app named "{same}" is already tracked.')
        clash = next((a.name for a in self.apps.values() if a.folder.lower() == spec.folder.lower()), None)
        if clash:
            raise ValueError(f'Folder "{spec.folder}" is already used by "{clash}".')
        self.apps[spec.name] = spec

    def remove(self, name: str):
        self.apps.pop(name, None)

    @staticmethod
    def _parser() -> configparser.ConfigParser:
        cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(';',))
        cp.optionxform = str  # keep key case
        return cp


_KNOWN_KEYS = set(AppSpec('x', 'x', source='github').to_section()) | set(AppSpec('x', 'x', source='url').to_section())


def _template_header() -> str:
    lines = []
    with open(TEMPLATE_PATH, encoding='utf-8') as f:
        for line in f:
            if line.lstrip().startswith('['):
                break
            lines.append(line)
    return ''.join(lines)
