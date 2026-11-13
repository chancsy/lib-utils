r"""On-demand elevation: run a batch of a module's own calls in a short-lived elevated helper after one UAC prompt,
so Jupyter / Python itself never runs as administrator. Used by utils.tools.task_scheduler and
utils.standalone.win_service_utils. Requires pywin32 (Windows only).

A module that wants this ("ops module") has
    OPS = ('op_a', 'op_b', ...)          # the only calls the helper accepts for this module
    def run_op(op: str, kwargs: dict)    # does one call, elevated; raises an exception with an int `.code` on failure
and calls  call('utils.<package>.<module>', [(op, kwargs), ...], 'Plain description')  from the non-elevated side.

call() starts this file as a script with the same interpreter (pythonw.exe if there is one, so no console window)
through ShellExecuteEx "runas", which shows the UAC prompt, and waits for it to exit.
- The helper's command line: the description (shown under the UAC prompt's "Show more details", e.g.
  "Disable \Tests\a, \Tests\b"), the ops module, and the request as readable JSON. It is fixed once the prompt is
  shown, so it must never hold a password: an elevated call that needs one asks in its own dialog (ask_password).
- The result is the helper's exit code: 0, or the `.code` of the first call that failed (the calls after it are not
  made). The non-elevated caller and the elevated helper share no files.
- Only ops modules in the utils package, and only the calls in their OPS, are accepted.
"""
from __future__ import annotations

import ctypes
import importlib
import json
import os
import subprocess
import sys

TIMEOUT_S = 600              # the user may take a while with the UAC prompt and a password dialog
UNEXPECTED = 0xE0F70001      # the helper failed outside the module's call (bad request, import error, ...)
CANCELLED = 1223             # ERROR_CANCELLED: UAC prompt declined, or a password dialog cancelled
TIMEOUT = 0xE0F70002         # not an exit code: call() gave up waiting
_HELPER = os.path.abspath(__file__)


class ElevationError(Exception):
    """The elevated call didn't happen or failed; `code`: CANCELLED, TIMEOUT, UNEXPECTED, or the op's error code."""

    def __init__(self, msg: str, code: int | None = None):
        super().__init__(msg)
        self.code = code


def is_admin() -> bool:
    """True if this process runs as administrator (elevated)."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def current_user() -> str:
    r"""This process's account as DOMAIN\user."""
    import win32api
    import win32con
    return win32api.GetUserNameEx(win32con.NameSamCompatible)


def ask_password(user: str, caption: str, message: str, retry: bool = False) -> str:
    """The Windows password dialog for `user` (user name fixed, nothing saved); ElevationError CANCELLED if cancelled.
    retry=True shows it with 'Wrong password - try again.'"""
    import pywintypes
    import win32cred
    flags = (win32cred.CREDUI_FLAGS_GENERIC_CREDENTIALS | win32cred.CREDUI_FLAGS_DO_NOT_PERSIST
             | win32cred.CREDUI_FLAGS_ALWAYS_SHOW_UI | win32cred.CREDUI_FLAGS_KEEP_USERNAME
             | win32cred.CREDUI_FLAGS_EXCLUDE_CERTIFICATES | (win32cred.CREDUI_FLAGS_INCORRECT_PASSWORD if retry else 0))
    info = {'CaptionText': caption, 'MessageText': ('Wrong password - try again.\n\n' if retry else '') + message}
    try:
        _, password, _ = win32cred.CredUIPromptForCredentials(caption, 1326 if retry else 0, user, None, False, flags,
                                                              info)
    except pywintypes.error as e:
        if e.winerror == CANCELLED:
            raise ElevationError('Password dialog cancelled - nothing changed', CANCELLED) from None
        raise ElevationError(f'Password dialog: {e.strerror}', e.winerror) from None
    return password


def _python() -> str:
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), 'pythonw.exe')
    return w if os.path.isfile(w) else exe


def _plain(text: str, limit: int = 300) -> str:
    """Description for the command line: no quotes, one line, not too long."""
    text = ' '.join(text.replace('"', "'").split())
    return text if len(text) <= limit else text[:limit - 3] + '...'


def params(module: str, requests: list[tuple[str, dict]], description: str) -> str:
    """The helper's command line after the interpreter: this file, the description, the ops module, the request as
    readable JSON. Quoted with the Windows C runtime rules (subprocess.list2cmdline), as the helper's argv is parsed."""
    data = json.dumps([{'op': op, 'kwargs': kw} for op, kw in requests], separators=(', ', ': '))
    return subprocess.list2cmdline([_HELPER, _plain(description), module, data])


def _check(module: str, requests):
    if not module.startswith('utils.'):
        raise ValueError(f'ops module {module!r}: only modules of the utils package are run elevated')
    ops = getattr(importlib.import_module(module), 'OPS', ())
    for op, _ in requests:
        if op not in ops:
            raise ValueError(f'{op!r} is not run elevated (allowed for {module}: {ops})')


def call(module: str, requests: list[tuple[str, dict]], description: str, timeout_s: float = TIMEOUT_S,
         _verb: str = 'runas') -> None:
    """Run [(op, kwargs), ...] of ops module `module` in one elevated helper. ElevationError if the UAC prompt is
    declined (CANCELLED), the helper doesn't finish within timeout_s after Yes (TIMEOUT), or a call fails (its code).
    _verb='open' runs the helper without elevation (tests of the plumbing only)."""
    import pythoncom
    import pywintypes
    import win32con
    import win32event
    import win32process
    from win32com.shell import shell, shellcon

    _check(module, requests)
    try:   # ShellExecuteEx may use COM; this can be a widget-callback thread
        pythoncom.CoInitialize()
    except pywintypes.com_error:
        pass   # already initialised in another mode - usable as it is
    try:
        r = shell.ShellExecuteEx(fMask=shellcon.SEE_MASK_NOCLOSEPROCESS, lpVerb=_verb, lpFile=_python(),
                                 lpParameters=params(module, requests, description), nShow=win32con.SW_SHOWNORMAL)
    except pywintypes.error as e:
        if e.winerror == CANCELLED:
            raise ElevationError(f'UAC prompt declined - nothing changed ({description})', CANCELLED) from None
        raise ElevationError(f'Could not start the elevated helper: {e.strerror}', e.winerror) from None
    h = r['hProcess']
    try:
        if win32event.WaitForSingleObject(h, int(timeout_s * 1000)) != win32event.WAIT_OBJECT_0:
            raise ElevationError(f'No answer from the elevated helper within {timeout_s:.0f} s (a dialog still open?) '
                                 '- check later whether the change was made', TIMEOUT)
        code = win32process.GetExitCodeProcess(h) & 0xFFFFFFFF
    finally:
        h.Close()
    if code == 0:
        return
    if code == CANCELLED:
        raise ElevationError(f'Password dialog cancelled - nothing changed ({description})', code)
    if code == UNEXPECTED:
        raise ElevationError(f'{description}: the elevated helper failed outside the call itself; run the same call '
                             'from an elevated Python with elevate=False to see the traceback', code)
    raise ElevationError(f'{description} (elevated) failed', code)


# --- the elevated side: this file run as a script -----------------------------------------------------------------

def _use_this_copy():
    """Use the utils package this file belongs to, also when it isn't the installed one (a test copy of
    utils/standalone with a tools/ folder next to it)."""
    here = os.path.dirname(_HELPER)
    import utils.standalone
    import utils.tools
    for pkg, d in ((utils.standalone, here), (utils.tools, os.path.join(os.path.dirname(here), 'tools'))):
        if os.path.isdir(d) and os.path.normcase(d) not in [os.path.normcase(os.path.abspath(p)) for p in pkg.__path__]:
            pkg.__path__.insert(0, d)


def _main(argv) -> int:
    """argv = [this file, description, ops module, request JSON]. Exit code: 0, the `.code` of the first call that
    failed, or UNEXPECTED."""
    try:
        module, requests = argv[2], json.loads(argv[3])   # argv[1] is the description
        if not module.startswith('utils.'):
            return UNEXPECTED
        _use_this_copy()
        ops = importlib.import_module(module)
        if not all(r['op'] in ops.OPS for r in requests):
            return UNEXPECTED
        for r in requests:
            ops.run_op(r['op'], dict(r['kwargs']))
        return 0
    except Exception as e:
        code = getattr(e, 'code', None)
        return code if isinstance(code, int) and code else UNEXPECTED


if __name__ == '__main__':
    # run as a script, this file's folder is sys.path[0]: drop it, so its sibling modules can't shadow anything
    if sys.path and os.path.normcase(os.path.abspath(sys.path[0])) == os.path.normcase(os.path.dirname(_HELPER)):
        sys.path.pop(0)
    rc = _main(sys.argv)
    os._exit(rc - 2 ** 32 if rc >= 2 ** 31 else rc)   # exit codes are DWORDs; os._exit takes a signed int
