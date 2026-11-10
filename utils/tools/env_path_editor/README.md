# Env Path Editor

A Jupyter UI plus API to view, check and edit the Windows User and System PATH.

```python
from utils.tools.env_path_editor.env_path_editor import show_gui
display(show_gui())                                   # or run env_path_editor.py as a notebook

from utils.tools import env_path_editor as epe        # no UI
epe.update_user_path(add=[r'C:\Apps\git\cmd'], remove=[r'C:\Apps\old'], backup_first=True)  # -> (added, removed)
epe.add_user_path(path); epe.remove_user_path(path); epe.in_path(path)
```

## Files

- `_winpath.py`: reads and writes the raw registry `Path` value (`HKCU\Environment`, `HKLM\...\Session Manager\Environment`), keeping the value type. `%VAR%` entries are stored unexpanded; a write containing `%` is forced to `REG_EXPAND_SZ`.
- `__init__.py`: the API for other tools (used by portable_apps_manager's `_pathlink.py`): `update_user_path(add, remove, prepend, backup_first)`, `add_user_path`, `remove_user_path`, `in_path`. Each call does at most one write and one broadcast, and nothing when there's nothing to change.
- `env_path_editor.py`: the UI (jupytext py:percent, paired to `_jupytext-sync-ipynb/`); `show_gui()` returns the widget.

## Behaviour

- **Comparison key** (duplicates, add, remove): `%VARS%` expanded with the process environment, surrounding quotes removed, absolute path, case-folded, trailing backslash dropped (`os.path.abspath` + `normcase`). Entries are written back exactly as typed.
- **Flags:** empty entry, unresolved variable, relative path, folder not found, not a folder, duplicate of #n (same scope), also in System #n (User entries; System is searched first, so the User copy is never used).
- **No sorting**; Move up / down for manual order.
- **Remove duplicates & empty:** keeps the first of each key; on User it also drops entries already in System.
- **Add** refuses an entry that is already in the scope, or (for User) already in System.
- **Save:** both scopes are checked against the value read at load. If either changed outside the tool, nothing is written. Optional backup (checkbox, default on) of both raw values to `%TEMP%\env_path_editor_backups\<timestamp>_path_backup.txt`. Then one `WM_SETTINGCHANGE "Environment"` broadcast; programs already running keep their old PATH.
- **Restore:** `restore_backup(file, scopes=(USER,))` writes the saved raw value back byte-identical. Not in the UI.
- **System scope** is read-only in the UI unless running as administrator (`IsUserAnAdmin`).

## Status

- Working: the UI and editing / saving the User PATH.
- Not yet tested: editing and saving the System PATH as administrator.
