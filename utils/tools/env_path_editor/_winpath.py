"""Read, check and write the Windows User / System PATH straight from the registry.

The raw registry value is used, not os.environ['PATH']: the process PATH is System + User already
joined and with %VARS% expanded, so writing it back would copy System entries into User and bake in
expanded paths. Entries are kept exactly as written; only comparisons use the normalized form
(variables expanded, absolute, case-folded, no trailing backslash).
"""
import ctypes
import datetime
import os
import tempfile
import winreg
from dataclasses import dataclass, field

BACKUP_DIR = os.path.join(tempfile.gettempdir(), 'env_path_editor_backups')
MAX_ENV_VAR_LEN = 32767     # a single environment variable, in characters


@dataclass(frozen=True)
class Scope:
    name: str          # 'User' | 'System'
    hive: int
    subkey: str
    value: str = 'Path'

    @property
    def location(self) -> str:
        hive = {winreg.HKEY_CURRENT_USER: 'HKCU', winreg.HKEY_LOCAL_MACHINE: 'HKLM'}.get(self.hive, str(self.hive))
        return f'{hive}\\{self.subkey}\\{self.value}'


USER = Scope('User', winreg.HKEY_CURRENT_USER, 'Environment')
SYSTEM = Scope('System', winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')


class PathWriteError(Exception):
    pass


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


# ── normalize / check ─────────────────────────────────────────────────────────
def expand(entry: str) -> str:
    """%VARS% expanded with the current process environment; surrounding quotes removed."""
    e = entry.strip().strip('"')
    return winreg.ExpandEnvironmentStrings(e) if e else ''


def normalize(entry: str) -> str:
    """Comparison key: expanded, absolute, case-folded, no trailing backslash (except a drive root)."""
    x = expand(entry)
    if not x:
        return ''
    if not os.path.isabs(x):   # relative entries resolve against the cwd at lookup time - compare as written
        return os.path.normcase(os.path.normpath(x))
    return os.path.normcase(os.path.abspath(x))


@dataclass
class EntryCheck:
    entry: str
    expanded: str
    key: str                           # normalize(entry)
    problems: list[str] = field(default_factory=list)   # empty = OK
    duplicate_of: int | None = None    # index of the first entry with the same key (same scope)
    in_other_scope: int | None = None  # index in the other scope (User entries also in System)

    @property
    def ok(self) -> bool:
        return not self.problems


def check_entries(entries: list[str], other: list[str] | None = None) -> list[EntryCheck]:
    """Flag empty / unresolved-variable / relative / missing-folder / duplicate entries.

    `other`: the other scope's entries (System, when checking User) - a match there is flagged
    'also in System' because System is searched first, so the User copy is never used.
    """
    other_keys = {}
    for i, e in enumerate(other or []):
        other_keys.setdefault(normalize(e), i)
    first = {}
    out = []
    for i, e in enumerate(entries):
        x, k = expand(e), normalize(e)
        c = EntryCheck(e, x, k)
        if not k:
            c.problems.append('empty entry')
        elif '%' in x:
            c.problems.append('unresolved variable')
        elif not os.path.isabs(x):
            c.problems.append('relative path')
        elif not os.path.exists(x):
            c.problems.append('folder not found')
        elif not os.path.isdir(x):
            c.problems.append('not a folder')
        if k:
            if k in first:
                c.duplicate_of = first[k]
                c.problems.append(f'duplicate of #{first[k] + 1}')
            else:
                first[k] = i
            if k in other_keys:
                c.in_other_scope = other_keys[k]
                c.problems.append(f'also in System #{other_keys[k] + 1}')
        out.append(c)
    return out


def remove_duplicates(entries: list[str], other: list[str] | None = None) -> list[str]:
    """Drop empty entries, later duplicates (same normalized path), and entries already in `other`."""
    other_keys = {normalize(e) for e in other or []}
    seen, out = set(), []
    for e in entries:
        k = normalize(e)
        if k and k not in seen and k not in other_keys:
            seen.add(k)
            out.append(e)
    return out


def contains(entries: list[str], path: str) -> bool:
    k = normalize(path)
    return any(normalize(e) == k for e in entries)


# ── registry ──────────────────────────────────────────────────────────────────
def split(raw: str) -> list[str]:
    """Raw value -> entries. A single trailing ';' is not counted as an empty entry."""
    if not raw:
        return []
    parts = raw.split(';')
    if parts[-1] == '':
        parts.pop()
    return parts


def join(entries: list[str]) -> str:
    return ';'.join(entries)


def read_raw(scope: Scope) -> tuple[str, int]:
    """(raw value, registry type). A missing value is ('', REG_EXPAND_SZ)."""
    try:
        with winreg.OpenKey(scope.hive, scope.subkey, 0, winreg.KEY_READ) as k:
            value, typ = winreg.QueryValueEx(k, scope.value)
            return value or '', typ
    except FileNotFoundError:
        return '', winreg.REG_EXPAND_SZ


def read(scope: Scope) -> list[str]:
    return split(read_raw(scope)[0])


def backup(scopes: list[Scope], folder: str = BACKUP_DIR) -> str:
    """Write the current raw values of `scopes` to a timestamped text file; returns its path."""
    os.makedirs(folder, exist_ok=True)
    now = datetime.datetime.now()
    path = os.path.join(folder, f'{now:%Y%m%d_%H%M%S_%f}_path_backup.txt')
    lines = [f'# PATH backup {now:%Y-%m-%d %H:%M:%S}',
             '# To restore: paste a "raw" line into the Environment Variables dialog (Edit text...),',
             '# or call utils.tools.env_path_editor.restore_backup(<this file>).', '']
    for s in scopes:
        raw, typ = read_raw(s)
        lines += [f'[{s.name}]', f'location = {s.location}',
                  f'type = {"REG_EXPAND_SZ" if typ == winreg.REG_EXPAND_SZ else "REG_SZ"}',
                  f'raw = {raw}', 'entries:'] + [f'  {e}' for e in split(raw)] + ['']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return path


def write(scope: Scope, entries: list[str], expected_raw: str | None = None, backup_scopes: list[Scope] | None = None,
          notify: bool = True) -> str | None:
    """Write `entries` to the scope's Path value; returns the backup file path (if a backup was made).

    expected_raw: the raw value the edit was based on. If the registry no longer holds it (changed by
    something else since it was read), nothing is written and PathWriteError is raised.
    backup_scopes: back these scopes up to BACKUP_DIR first (None = no backup).
    """
    raw, _ = read_raw(scope)
    if expected_raw is not None and raw != expected_raw:
        raise PathWriteError(f'{scope.name} PATH was changed outside this tool since it was loaded - reload and redo the edit.')
    bak = backup(backup_scopes) if backup_scopes else None
    _set_raw(scope, join(entries))
    if notify:
        broadcast_change()
    return bak


def _set_raw(scope: Scope, new: str):
    if len(new) > MAX_ENV_VAR_LEN:
        raise PathWriteError(f'{scope.name} PATH would be {len(new)} characters; the limit is {MAX_ENV_VAR_LEN}.')
    typ = read_raw(scope)[1]
    if '%' in new:
        typ = winreg.REG_EXPAND_SZ    # REG_SZ would leave %VARS% unexpanded
    try:
        with winreg.CreateKeyEx(scope.hive, scope.subkey, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, scope.value, 0, typ, new)
    except PermissionError:
        raise PathWriteError(f'No permission to write {scope.location}'
                             + (' - run as administrator to edit the System PATH.' if scope.hive == winreg.HKEY_LOCAL_MACHINE else '.'))


def broadcast_change() -> bool:
    """Tell running programs (Explorer) the environment changed, so programs started from now on see it.
    Already-running programs (terminals, VS Code, Jupyter) keep their old PATH until restarted."""
    HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x001A, 0x0002
    result = ctypes.c_size_t()
    ok = ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, 'Environment',
                                                  SMTO_ABORTIFHUNG, 5000, ctypes.byref(result))
    return bool(ok)


def read_backup(path: str) -> dict[str, str]:
    """{scope name: raw value} from a backup file."""
    out, cur = {}, None
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith('[') and line.endswith(']'):
                cur = line[1:-1]
            elif cur and line.startswith('raw = '):
                out[cur] = line[len('raw = '):]
    return out


def restore_backup(path: str, scopes: tuple[Scope, ...] = (USER,), notify: bool = True) -> list[str]:
    """Write the raw values saved in a backup file back to the registry, exactly as saved; returns
    the scope names restored. User only by default - pass (USER, SYSTEM) (as administrator) for both."""
    saved = read_backup(path)
    done = []
    for s in scopes:
        if s.name in saved:
            _set_raw(s, saved[s.name])
            done.append(s.name)
    if done and notify:
        broadcast_change()
    return done
