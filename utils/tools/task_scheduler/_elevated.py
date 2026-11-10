"""task_scheduler calls in an elevated helper process: a UAC prompt on demand, so Jupyter / Python itself never needs
to run as administrator.

call() starts this file with the same interpreter (pythonw.exe if there is one, so no console window) through
ShellExecuteEx "runas", which shows the UAC prompt, and waits for it to exit. One prompt covers a batch of calls.
- The helper's command line is a plain description (shown under the UAC prompt's "Show more details", e.g.
  "Disable \\Tests\\a, \\Tests\\b") followed by the request as readable JSON. It is fixed once the prompt is shown and
  never holds a password: for logon 'password' the helper asks for it in its own Windows password dialog.
- The outcome comes back as the helper's exit code: 0, or the HRESULT / Win32 error code of the first call that
  failed (the calls after it are not made). So the non-elevated caller and the elevated helper share no files.
- Only the calls in OPS are accepted, and they run with elevate=False.
"""
from __future__ import annotations

import json
import os
import sys

OPS = ('register_task', 'set_enabled', 'run_task', 'stop_task', 'delete_task', 'delete_folder')
TIMEOUT_S = 600            # the user may take a while with the UAC prompt and the password dialog
_UNEXPECTED = 0xE0F70001   # helper failed outside a Task Scheduler call (bad request, import error, ...)
_ERROR_CANCELLED = 1223


def _python() -> str:
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), 'pythonw.exe')
    return w if os.path.isfile(w) else exe


def _plain(text: str, limit: int = 300) -> str:
    """Description for the command line: no quotes, one line, not too long."""
    text = ' '.join(text.replace('"', "'").split())
    return text if len(text) <= limit else text[:limit - 3] + '...'


def _params(requests: list[tuple[str, dict]], description: str) -> str:
    """The helper's command line after the interpreter: this file, the description, the request as readable JSON.
    Quoted with the Windows C runtime rules (subprocess.list2cmdline), which is how the helper's argv is parsed."""
    import subprocess
    data = json.dumps([{'op': op, 'kwargs': kw} for op, kw in requests], separators=(', ', ': '))
    return subprocess.list2cmdline([os.path.abspath(__file__), _plain(description), data])


def call(requests: list[tuple[str, dict]], description: str, timeout_s: float = TIMEOUT_S, _verb: str = 'runas') -> None:
    """Run [(op, kwargs), ...] (task_scheduler.<op>(**kwargs)) in one elevated helper; TaskSchedulerError if the UAC
    prompt is declined or a call fails. _verb='open' runs the helper without elevation (tests of the plumbing only)."""
    import pywintypes
    import win32con
    import win32event
    import win32process
    from win32com.shell import shell, shellcon

    from ._winsched import _HINTS, TaskSchedulerError, _com_init, _message
    _com_init()   # ShellExecuteEx may use COM; this can be a widget-callback thread
    for op, _ in requests:
        if op not in OPS:
            raise ValueError(f'{op!r} is not run elevated (allowed: {OPS})')
    params = _params(requests, description)
    try:
        r = shell.ShellExecuteEx(fMask=shellcon.SEE_MASK_NOCLOSEPROCESS, lpVerb=_verb, lpFile=_python(),
                                 lpParameters=params, nShow=win32con.SW_SHOWNORMAL)
    except pywintypes.error as e:
        if e.winerror == _ERROR_CANCELLED:
            raise TaskSchedulerError(f'UAC prompt declined - nothing changed ({description})', _ERROR_CANCELLED) from None
        raise TaskSchedulerError(f'Could not start the elevated helper: {e.strerror}', e.winerror) from None
    h = r['hProcess']
    try:
        if win32event.WaitForSingleObject(h, int(timeout_s * 1000)) != win32event.WAIT_OBJECT_0:
            raise TaskSchedulerError(f'No answer from the elevated helper within {timeout_s:.0f} s (a dialog still '
                                     'open?) - Reload later to see whether the change was made')
        code = win32process.GetExitCodeProcess(h) & 0xFFFFFFFF
    finally:
        h.Close()
    if code == 0:
        return
    if code == _ERROR_CANCELLED:
        raise TaskSchedulerError(f'Password dialog cancelled - nothing changed ({description})', code)
    if code == _UNEXPECTED:
        raise TaskSchedulerError(f'{description}: the elevated helper failed outside Task Scheduler; run the same call '
                                 'from an elevated Python with elevate=False to see the traceback', code)
    text = _HINTS.get(code) or _message(code) or 'failed'
    more = ' (the ones before it were done)' if len(requests) > 1 else ''
    raise TaskSchedulerError(f'{description} (elevated): {text} (0x{code:08X}){more}', code)


def _main(argv) -> int:
    try:
        requests = json.loads(argv[2])   # argv[1] is the description
        if not all(r['op'] in OPS for r in requests):
            return _UNEXPECTED
        # use the task_scheduler package this file belongs to (also when it isn't the installed one)
        import utils.tools
        tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.normcase(tools_dir) not in [os.path.normcase(os.path.abspath(p)) for p in utils.tools.__path__]:
            utils.tools.__path__.insert(0, tools_dir)
        from utils.tools import task_scheduler as ts
        from utils.tools.task_scheduler._winsched import _trigger_from_dict
        for r in requests:
            kwargs = dict(r['kwargs'])
            if r['op'] == 'register_task':
                kwargs['triggers'] = [_trigger_from_dict(d) for d in kwargs.get('triggers', [])]
            getattr(ts, r['op'])(**kwargs, elevate=False)
        return 0
    except Exception as e:
        code = getattr(e, 'code', None)
        return code if isinstance(code, int) and code else _UNEXPECTED


if __name__ == '__main__':
    rc = _main(sys.argv)
    os._exit(rc - 2 ** 32 if rc >= 2 ** 31 else rc)   # exit codes are DWORDs; os._exit takes a signed int
