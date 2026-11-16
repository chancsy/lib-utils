"""PDM File Downloader - search a SolidWorks PDM vault by file name and download copies of the files.

Back end: utils.standalone.solidworks_pdm_utils.SolidWorksPDM (the PDM client's COM API via pywin32).
UI: pdm_file_downloader.py (jupytext py:percent; run it in Jupyter, or call show_gui(**kwargs): vault, look_in, dest).

API, no UI:
    pdm_missing()                       # '' if the PDM client and pywin32 are present, else why not
    is_markup('AB12345_MUAB.pdf')       # True: an ECN markup file
    download_files(pdm, paths, dest)    # -> (saved, skipped, failed); pdm is a connected SolidWorksPDM
"""
import importlib.util
import os
import re
import sys

DEFAULT_VAULT = 'PDM Vault'
DEFAULT_DEST = os.path.join(os.path.expanduser('~'), 'Downloads', 'Downloaded PDM Files')
MARKUP_RE = re.compile(r'_MU[A-Z]{1,2}\.[^.]+$', re.IGNORECASE)  # ECN markups, e.g. AB12345_MUAB.pdf
_PDM_PROGID = 'ConisioLib.EdmVault'  # the COM class SolidWorksPDM dispatches


def pdm_missing() -> str:
    """'' if the SolidWorks PDM client and pywin32 are present, else a one-line reason.

    Checks the PDM client's COM class registration and that pywin32 is importable; it doesn't
    connect, so it says nothing about the vault itself.
    """
    if sys.platform != 'win32':
        return 'SolidWorks PDM needs Windows.'
    import winreg
    try:
        winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, _PDM_PROGID + r'\CLSID').Close()
    except OSError:
        return f'The SolidWorks PDM client is not installed on this PC ({_PDM_PROGID} is not registered).'
    if importlib.util.find_spec('win32com') is None:
        return 'pywin32 is not installed (pip install pywin32).'
    return ''


def is_markup(name: str) -> bool:
    """True for an ECN markup file name, e.g. ``AB12345_MUAB.pdf``."""
    return bool(MARKUP_RE.search(name))


def download_files(pdm, paths, dest: str, overwrite: bool = False, on_progress=None):
    """Download copies of vault files (no checkout) into `dest`.

    pdm: a connected SolidWorksPDM. paths: vault file paths.
    overwrite: False skips a file whose name already exists in `dest`.
    on_progress(done, total, name): called before each file (done = files finished so far) and once at the end.

    Returns (saved, skipped, failed): file names, file names, and 'name: reason' strings.
    """
    paths = list(paths)
    saved, skipped, failed = [], [], []
    for i, path in enumerate(paths):
        name = os.path.basename(path)
        if on_progress:
            on_progress(i, len(paths), name)
        if os.path.exists(os.path.join(dest, name)) and not overwrite:
            skipped.append(name)
            continue
        try:
            pdm.download_file(path, dest)
            saved.append(name)
        except PermissionError:
            failed.append(f'{name}: destination file is in use (open in another program?) or not writable')
        except Exception as e:
            failed.append(f'{name}: {e}')
    if on_progress:
        on_progress(len(paths), len(paths), '')
    return saved, skipped, failed
