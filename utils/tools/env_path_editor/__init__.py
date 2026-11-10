"""Env Path Editor - view, check and edit the Windows User / System PATH.

Entries are compared by their expanded absolute path (%VARS% expanded, case and trailing backslash
ignored), so C:\\Foo, c:\\foo\\ and %X%\\foo (X = C:\\) count as the same entry. Entries are written
back exactly as typed. User PATH needs no admin rights; System PATH can only be written as admin.

UI: env_path_editor.py (jupytext py:percent; run it in Jupyter, or call show_gui()).

API for other tools (e.g. portable_apps_updater), one registry write per call:
    update_user_path(add=[r'C:\\Apps\\git\\cmd'], remove=[r'C:\\Apps\\old'])   # -> (added, removed)
    add_user_path(r'C:\\Apps\\git\\cmd')      # True if added; False if already in User or System PATH
    remove_user_path(r'C:\\Apps\\git\\cmd')   # number of entries removed
    in_path(r'C:\\Apps\\git\\cmd')            # in User or System PATH?
"""
from ._winpath import (BACKUP_DIR, SYSTEM, USER, EntryCheck, PathWriteError, Scope, backup, broadcast_change,
                       check_entries, contains, expand, is_admin, normalize, read, read_backup, read_raw,
                       remove_duplicates, restore_backup, split, write)


def in_path(path: str) -> bool:
    """True if `path` is in the User or System PATH (compared as expanded absolute paths)."""
    return contains(read(USER), path) or contains(read(SYSTEM), path)


def update_user_path(add=(), remove=(), prepend: bool = False, backup_first: bool = False,
                     scope: Scope = USER, system_scope: Scope = SYSTEM) -> tuple[list[str], list[str]]:
    """Add and/or remove User PATH entries in one write; returns (added, removed).

    add: paths to add. Skipped if already in the User or System PATH (System is searched first,
        so a User copy would never be used). Added in the given order, at the end (or at the
        start with prepend=True).
    remove: paths to remove; every User entry with the same expanded absolute path is removed.
    backup_first: save the current User and System values to BACKUP_DIR before writing.
    Nothing is written (and nothing broadcast) when there is nothing to change.
    """
    raw, _ = read_raw(scope)
    entries = split(raw)
    system = read(system_scope)
    rm_keys = {normalize(p) for p in remove}
    removed = [e for e in entries if normalize(e) in rm_keys]
    entries = [e for e in entries if normalize(e) not in rm_keys]
    added = []
    for p in add:
        if not (contains(entries, p) or contains(system, p) or contains(added, p)):
            added.append(p)
    if not added and not removed:
        return [], []
    entries = added + entries if prepend else entries + added
    write(scope, entries, expected_raw=raw, backup_scopes=[scope, system_scope] if backup_first else None)
    return added, removed


def add_user_path(path: str, prepend: bool = False, backup_first: bool = False) -> bool:
    """Add one User PATH entry; False if it is already in the User or System PATH."""
    return bool(update_user_path(add=[path], prepend=prepend, backup_first=backup_first)[0])


def remove_user_path(path: str, backup_first: bool = False) -> int:
    """Remove every User PATH entry matching `path`; returns how many were removed."""
    return len(update_user_path(remove=[path], backup_first=backup_first)[1])
