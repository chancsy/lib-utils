"""apps_catalog.ini - shared, git-tracked record of how each app is best tracked.

Same [app:<name>] keys as portable_apps.ini (source, repo/asset or url/check_by/version_from/
version_file, folder, bin, preserve) plus a free-text `note`, but no install state. The Add form's
"From catalog" fills its fields from an entry; "Save to catalog" writes a tracked app's settings
back. Sharing a new recipe = committing this file.
"""
import configparser
import os
from dataclasses import dataclass, fields

from ._config import AppSpec

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apps_catalog.ini')
_PREFIX = 'app:'
_STATE_KEYS = ('installed_version', 'installed_marker', 'installed_asset', 'installed_on')
_HEADER = """\
; Portable Apps Manager - shared app catalog (git-tracked; commit changes to share them).
; How each app is best tracked: same keys as portable_apps.ini (see config.template.ini), plus
; `add_to_path` (the Add form's suggested default) and `note`, and no install state. Used by the
; Add form ("From catalog") and written by "Save to catalog" (which keeps an entry's existing note
; and records whether the app's bin is in PATH). Comments other than this header are dropped when
; the tool saves - put explanations in `note`.

"""


@dataclass
class CatalogEntry:
    spec: AppSpec    # settings only; installed_* fields are always empty
    note: str = ''
    add_to_path: bool = False   # suggested default for the Add form's "Add to PATH"


def _parser() -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None)   # no inline comments: notes may contain ';'
    cp.optionxform = str
    return cp


def load_catalog(path: str = CATALOG_PATH) -> dict[str, CatalogEntry]:
    if not os.path.isfile(path):
        return {}
    cp = _parser()
    cp.read(path, encoding='utf-8')
    out = {}
    for sec in cp.sections():
        if sec.startswith(_PREFIX):
            name = sec[len(_PREFIX):]
            out[name] = CatalogEntry(spec=AppSpec.from_section(name, cp[sec]), note=cp[sec].get('note', ''),
                                     add_to_path=cp[sec].getboolean('add_to_path', fallback=False))
    return out


def save_catalog(entries: dict[str, CatalogEntry], path: str = CATALOG_PATH) -> None:
    cp = _parser()
    for name in sorted(entries, key=str.lower):
        e = entries[name]
        sec = {k: v for k, v in e.spec.to_section().items() if k not in _STATE_KEYS}
        cp[_PREFIX + name] = sec | {'add_to_path': 'true' if e.add_to_path else 'false', 'note': e.note}
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(_HEADER)
        cp.write(f)
    os.replace(tmp, path)


def recipe(spec: AppSpec) -> AppSpec:
    """Copy of spec without install state (what goes into / comes out of the catalog)."""
    return AppSpec(**{f.name: getattr(spec, f.name) for f in fields(AppSpec) if f.name not in _STATE_KEYS})


def save_to_catalog(spec: AppSpec, note: str | None = None, add_to_path: bool | None = None,
                    path: str = CATALOG_PATH) -> bool:
    """Add or replace spec's entry. note / add_to_path = None keep the existing entry's value.
    Returns True if replaced."""
    entries = load_catalog(path)
    old = entries.get(spec.name)
    entries[spec.name] = CatalogEntry(
        spec=recipe(spec), note=old.note if (old and note is None) else (note or ''),
        add_to_path=(old.add_to_path if old else False) if add_to_path is None else add_to_path)
    save_catalog(entries, path)
    return old is not None
