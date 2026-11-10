"""An app's `bin` folder on the Windows PATH, through utils.tools.env_path_editor.

Nothing is stored about PATH: the state shown is read from the registry each time, and removing
removes every User entry that resolves to the same folder (however it was written or added).
New entries go at the end of the User PATH, written with %USERPROFILE% when the folder is inside
the user profile. Every write backs up both PATH values first (env_path_editor.BACKUP_DIR).
"""
import os

from utils.tools import env_path_editor as epe

# Overridable for tests (env_path_editor.Scope objects pointing at a scratch registry key).
USER_SCOPE = epe.USER
SYSTEM_SCOPE = epe.SYSTEM

RESTART_NOTE = ('Programs that are already running (terminals, VS Code, Jupyter kernels) keep their old PATH '
                'until restarted.')


def bin_dir(root: str, spec) -> str | None:
    """Absolute folder the app would put on PATH, or None if it has no bin."""
    if not spec.bin:
        return None
    return os.path.normpath(os.path.join(spec.folder_path(root), spec.bin))


def entry_form(folder: str) -> str:
    """How a new entry is written: %USERPROFILE%\\... when inside the profile, else absolute."""
    prof = os.path.normcase(os.path.normpath(os.environ.get('USERPROFILE', '')))
    f = os.path.normpath(folder)
    if prof and os.path.normcase(f).startswith(prof + os.sep):
        return '%USERPROFILE%' + f[len(prof):]
    return f


class Snapshot:
    """User and System PATH entries read once (e.g. per table refresh)."""
    def __init__(self):
        self.user = epe.read(USER_SCOPE)
        self.system = epe.read(SYSTEM_SCOPE)

    def state(self, folder: str | None) -> str:
        """'system' | 'user' | 'none' | 'n/a' (no bin)."""
        if not folder:
            return 'n/a'
        if epe.contains(self.system, folder):
            return 'system'
        return 'user' if epe.contains(self.user, folder) else 'none'


def update(add: list[str] = (), remove: list[str] = ()) -> tuple[list[str], list[str]]:
    """One User PATH write: add folders (at the end, in entry_form) and remove every entry matching
    the remove folders. Returns (added, removed) as written in the registry."""
    return epe.update_user_path(add=[entry_form(f) for f in add], remove=list(remove), backup_first=True,
                                scope=USER_SCOPE, system_scope=SYSTEM_SCOPE)
