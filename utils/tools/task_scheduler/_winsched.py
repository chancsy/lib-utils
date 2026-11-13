"""Windows Task Scheduler through its COM API (Schedule.Service, via pywin32): register, list, enable / disable,
run / stop, export and delete tasks. Only the basic settings are covered; see __init__.py for the API summary."""
from __future__ import annotations

import datetime as _dt
import re
from contextlib import contextmanager
from dataclasses import dataclass, field

import pythoncom
import pywintypes
import win32api
import win32com.client

from ...standalone import elevate_utils as _elevate
from ...standalone.elevate_utils import current_user, is_admin  # noqa: F401 - part of this package's API

ROOT = '\\'

_TRIGGER_TIME, _TRIGGER_DAILY, _TRIGGER_BOOT, _TRIGGER_LOGON = 1, 2, 8, 9
_TRIGGER_NAMES = {0: 'On an event', 1: 'Once', 2: 'Daily', 3: 'Weekly', 4: 'Monthly', 5: 'Monthly (day of week)',
                  6: 'On idle', 7: 'When registered', 8: 'At startup', 9: 'At log on', 11: 'On session change'}
_ACTION_EXEC = 0
_CREATE, _CREATE_OR_UPDATE = 2, 6

LOGON_TYPES = {'password': 1, 's4u': 2, 'interactive': 3}
_LOGON_NAMES = {0: 'none', 1: 'password', 2: 's4u', 3: 'interactive', 4: 'group', 5: 'service account',
                6: 'interactive or password'}
RUN_LEVELS = {'limited': 0, 'highest': 1}
MULTIPLE_INSTANCES = {'parallel': 0, 'queue': 1, 'ignore_new': 2, 'stop_existing': 3}
_STATES = {0: 'unknown', 1: 'disabled', 2: 'queued', 3: 'ready', 4: 'running'}

_RESULTS = {
    0: 'success',
    0x41300: 'ready to run',
    0x41301: 'running',
    0x41302: 'disabled',
    0x41303: 'has not run yet',
    0x41304: 'no more runs scheduled',
    0x41306: 'stopped by Stop / End',
    0x8004131F: 'not started: an instance is already running',
    0x800710E0: 'refused by the operator or administrator',
    0x8007052E: 'logon failure (wrong user name or password)',
    0x80070002: 'file not found (check the program path)',
    0x8007010B: 'start-in folder not found',
    0xC000013A: 'stopped (Ctrl+C or window closed)',
}

_HINTS = {
    0x80070005: 'access denied - needs administrator rights: an at-startup trigger, an at-log-on trigger for any '
                'user, logon "s4u", run level "highest", changing (e.g. enabling / disabling) a task registered with '
                'administrator rights, deleting anything in a folder created with them, and other users\' tasks '
                '(elevate="auto" or True asks for them with a UAC '
                'prompt)',
    0x8007052E: 'logon failure - wrong user name or password',
    0x80070534: 'unknown user name',
    0x80070002: 'not found',
    0x800700B7: 'already exists',
}


class TaskSchedulerError(Exception):
    """A Task Scheduler call failed; `code` is the HRESULT (e.g. 0x80070005 access denied), if any."""

    def __init__(self, msg: str, code: int | None = None):
        super().__init__(msg)
        self.code = code


def _code(e: pywintypes.com_error) -> int:
    sc = e.excepinfo[5] if e.excepinfo and e.excepinfo[5] else e.hresult
    return sc & 0xFFFFFFFF


def _message(code: int) -> str:
    try:
        return win32api.FormatMessage(code).strip()
    except pywintypes.error:
        return ''


@contextmanager
def _com(what: str):
    """Turn a COM error from the block into a TaskSchedulerError that says what failed and why."""
    try:
        yield
    except pywintypes.com_error as e:
        code = _code(e)
        text = _HINTS.get(code) or (e.excepinfo[2] if e.excepinfo and e.excepinfo[2] else '') or _message(code)
        raise TaskSchedulerError(f'{what}: {text} (0x{code:08X})', code) from None


def ask_password(user: str, task_path: str = '', retry: bool = False) -> str:
    """The Windows password dialog for `user` (user name fixed, nothing saved); TaskSchedulerError 1223 if cancelled."""
    try:
        return _elevate.ask_password(user, 'Task Scheduler',
                                     f'Password of {user}, to run {task_path or "the task"} whether the user is logged '
                                     'on or not. Windows keeps it with the task.', retry)
    except _elevate.ElevationError as e:
        raise TaskSchedulerError(str(e), e.code) from None


def needs_admin(triggers=(), logon: str = '', run_level: str = '') -> bool:
    """True if registering these settings needs administrator rights (at-startup or any-user log-on trigger, s4u,
    highest). Changing other users' tasks does too; that only shows as access denied."""
    triggers = [_as_trigger(t) for t in ([triggers] if isinstance(triggers, (str, Trigger)) else triggers)]
    return (any(t.kind == 'startup' or (t.kind == 'logon' and t.any_user) for t in triggers)
            or logon == 's4u' or run_level == 'highest')


def _elevating(elevate, needed: bool) -> bool:
    if elevate not in (True, False, 'auto'):
        raise ValueError(f'elevate {elevate!r}: use "auto", True or False')
    return not is_admin() and (elevate is True or (elevate == 'auto' and needed))


def _print_notice(msg: str):
    print(msg, flush=True)


_notify = _print_notice


def set_notify(fn) -> None:
    """Where 'UAC prompt: ...' notices go just before a prompt is shown (default: print; None: nowhere).
    The UI sends them to its log."""
    global _notify
    _notify = fn or (lambda msg: None)


def _elevated_call(requests: list[tuple[str, dict]], description: str):
    """One UAC prompt for a batch of [(op, kwargs), ...] run in the elevated helper."""
    from ._elevated import call
    _notify(f'UAC prompt: {description} - answer it on this PC\'s screen')
    call(requests, description)


def result_text(code: int | None) -> str:
    """Last-run result as text: 'success', 'has not run yet', 'exit code 1', '0x8007052E logon failure ...'."""
    if code is None:
        return ''
    c = code & 0xFFFFFFFF
    if c in _RESULTS:
        return _RESULTS[c]
    if c < 0x10000:
        return f'exit code {c}'
    msg = _message(c)
    return f'0x{c:08X}' + (f' {msg}' if msg else '')


# ── durations ─────────────────────────────────────────────────────────────────
def _iso_duration(seconds: float) -> str:
    """Seconds -> ISO 8601 duration as Task Scheduler stores it, e.g. 90 -> 'PT1M30S', 0 -> 'PT0S'."""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return 'PT' + (f'{h}H' if h else '') + (f'{m}M' if m else '') + (f'{sec}S' if sec or not (h or m) else '')


def _seconds(iso: str) -> int:
    """ISO 8601 duration -> seconds ('' -> 0)."""
    m = re.fullmatch(r'P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?', (iso or '').strip())
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def _fmt_s(seconds: int) -> str:
    return f'{seconds} s' if seconds < 120 else f'{seconds // 60} min' if seconds % 60 == 0 else f'{seconds} s'


# ── triggers ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Trigger:
    """When a task starts. Build with at_startup(), at_logon(), daily() or once()."""
    kind: str                           # 'startup', 'logon', 'daily', 'once'
    at: _dt.datetime | None = None      # daily: first day and the time of day; once: when
    delay_s: int = 0                    # startup / logon: wait this long after boot / logon
    every_days: int = 1                 # daily
    any_user: bool = False              # logon: anyone's logon (needs admin), not only the task's user's

    def __str__(self):
        if self.kind == 'startup':
            text = 'At startup'
        elif self.kind == 'logon':
            text = 'At log on' + (' of any user' if self.any_user else '')
        elif self.kind == 'daily':
            text = f'Daily at {self.at:%H:%M}' + (f' every {self.every_days} days' if self.every_days > 1 else '')
        else:
            text = f'Once at {self.at:%Y-%m-%d %H:%M}'
        return text + (f', delay {_fmt_s(self.delay_s)}' if self.delay_s else '')


def _parse_time(at) -> _dt.datetime:
    """datetime, 'HH:MM' (today) or 'YYYY-MM-DD HH:MM[:SS]' -> datetime (seconds dropped)."""
    if isinstance(at, _dt.datetime):
        return at.replace(microsecond=0)
    text = str(at).strip()
    m = re.fullmatch(r'(\d{1,2}):(\d{2})', text)
    if m:
        return _dt.datetime.combine(_dt.date.today(), _dt.time(int(m[1]), int(m[2])))
    try:
        return _dt.datetime.fromisoformat(text).replace(microsecond=0)
    except ValueError:
        raise ValueError(f'Time {at!r}: use HH:MM or YYYY-MM-DD HH:MM') from None


def at_startup(delay_s: int = 0) -> Trigger:
    """At system start-up, before anyone logs on (registering it needs administrator rights)."""
    return Trigger('startup', delay_s=int(delay_s))


def at_logon(delay_s: int = 0, any_user: bool = False) -> Trigger:
    """When the task's user logs on (any_user=True: anyone; needs administrator rights)."""
    return Trigger('logon', delay_s=int(delay_s), any_user=any_user)


def daily(at, every_days: int = 1) -> Trigger:
    """Every `every_days` days at `at` ('HH:MM', from today; or a datetime / 'YYYY-MM-DD HH:MM' for the first run)."""
    if int(every_days) < 1:
        raise ValueError('every_days must be 1 or more')
    return Trigger('daily', at=_parse_time(at), every_days=int(every_days))


def once(at) -> Trigger:
    """Once, at `at` (datetime, 'YYYY-MM-DD HH:MM', or 'HH:MM' today)."""
    return Trigger('once', at=_parse_time(at))


_TRIGGER_WORDS = {'startup': at_startup, 'boot': at_startup, 'logon': at_logon}


def _as_trigger(t) -> Trigger:
    if isinstance(t, Trigger):
        return t
    if isinstance(t, str) and t.lower() in _TRIGGER_WORDS:
        return _TRIGGER_WORDS[t.lower()]()
    raise ValueError(f'Trigger {t!r}: use at_startup(), at_logon(), daily(...), once(...), "startup" or "logon"')


def _boundary(text: str) -> _dt.datetime | None:
    try:
        return _dt.datetime.fromisoformat(text[:19])
    except (TypeError, ValueError):
        return None


def _trigger_from_com(t) -> tuple[Trigger | None, str]:
    """(Trigger, description) for a COM trigger; Trigger is None for kinds this tool doesn't build (weekly, ...)."""
    kind = t.Type
    spec = None
    if kind == _TRIGGER_BOOT:
        spec = Trigger('startup', delay_s=_seconds(t.Delay))
    elif kind == _TRIGGER_LOGON:
        spec = Trigger('logon', delay_s=_seconds(t.Delay), any_user=not t.UserId)
    elif kind in (_TRIGGER_DAILY, _TRIGGER_TIME):
        at = _boundary(t.StartBoundary)
        if at:
            spec = Trigger('daily', at=at, every_days=t.DaysInterval) if kind == _TRIGGER_DAILY else Trigger('once', at=at)
    text = str(spec) if spec else _TRIGGER_NAMES.get(kind, f'Trigger type {kind}')
    if not t.Enabled:
        text += ' (trigger disabled)'
    return spec, text


# ── task info ─────────────────────────────────────────────────────────────────
@dataclass
class TaskInfo:
    """A registered task, as read back from Task Scheduler."""
    name: str
    path: str                           # folder + name, e.g. \RestartMon
    enabled: bool
    state: str                          # 'ready', 'running', 'disabled', 'queued', 'unknown'
    command: str = ''
    arguments: str = ''
    working_dir: str = ''
    triggers: list[str] = field(default_factory=list)          # descriptions, e.g. 'At startup, delay 30 s'
    trigger_specs: list[Trigger | None] = field(default_factory=list)
    user: str = ''
    logon: str = ''                     # 'password', 's4u', 'interactive', ...
    run_level: str = ''                 # 'limited', 'highest'
    priority: int | None = None
    time_limit_s: int = 0               # 0 = no limit
    allow_on_battery: bool = True
    description: str = ''
    source: str = ''                    # RegistrationInfo.Source: who made it, e.g. a tool's marker
    last_run: _dt.datetime | None = None
    last_result: int | None = None
    next_run: _dt.datetime | None = None
    error: str = ''                     # set if the definition couldn't be read (e.g. access denied)

    @property
    def folder(self) -> str:
        return self.path[:-len(self.name)].rstrip('\\') or ROOT

    @property
    def result(self) -> str:
        return result_text(self.last_result)

    @property
    def runs(self) -> str:
        """'whether logged on or not' / 'only when logged on' (the Task Scheduler UI's wording)."""
        return {'password': 'whether logged on or not', 's4u': 'whether logged on or not (no password)',
                'interactive': 'only when logged on'}.get(self.logon, self.logon)


def _time(v) -> _dt.datetime | None:
    """COM date -> naive local datetime; Task Scheduler uses 1999-11-30 (last run) and 1899-12-30 (next run) for 'never'."""
    if v is None or v.year < 2000:
        return None
    return _dt.datetime(v.year, v.month, v.day, v.hour, v.minute, v.second)


def _info(t) -> TaskInfo:
    info = TaskInfo(name=t.Name, path=t.Path, enabled=bool(t.Enabled), state=_STATES.get(t.State, str(t.State)))
    try:
        info.last_run, info.last_result, info.next_run = _time(t.LastRunTime), t.LastTaskResult, _time(t.NextRunTime)
    except pywintypes.com_error:
        pass
    try:
        d = t.Definition
        p = d.Principal
        info.user, info.logon = p.UserId or p.GroupId or '', _LOGON_NAMES.get(p.LogonType, str(p.LogonType))
        info.run_level = {v: k for k, v in RUN_LEVELS.items()}.get(p.RunLevel, str(p.RunLevel))
        s = d.Settings
        info.priority, info.time_limit_s = s.Priority, _seconds(s.ExecutionTimeLimit)
        info.allow_on_battery = not (s.DisallowStartIfOnBatteries or s.StopIfGoingOnBatteries)
        info.description = d.RegistrationInfo.Description or ''
        info.source = d.RegistrationInfo.Source or ''
        actions = list(d.Actions)
        execs = [a for a in actions if a.Type == _ACTION_EXEC]
        if execs:
            info.command, info.arguments, info.working_dir = execs[0].Path, execs[0].Arguments or '', execs[0].WorkingDirectory or ''
        if len(actions) > 1 or (actions and not execs):
            info.arguments += f'  [+{len(actions) - bool(execs)} more action(s)]'
        for tr in d.Triggers:
            spec, text = _trigger_from_com(tr)
            info.trigger_specs.append(spec)
            info.triggers.append(text)
    except pywintypes.com_error as e:
        info.error = f'definition not readable: {_HINTS.get(_code(e)) or _message(_code(e))}'
    return info


# ── service / folders ─────────────────────────────────────────────────────────
def _norm_folder(folder: str | None) -> str:
    return '\\' + (folder or '').strip().strip('\\')


def _split(name: str, folder: str | None) -> tuple[str, str]:
    r"""(folder, name); a name with a folder in it (r'\Tests\Resume') overrides `folder`."""
    name = name.strip()
    if '\\' in name.strip('\\'):
        f, _, n = name.strip('\\').rpartition('\\')
        return _norm_folder(f), n
    if not name.strip('\\'):
        raise ValueError('Task name is empty')
    return _norm_folder(folder), name.strip('\\')


def _com_init():
    """COM must be initialised on each thread that uses it; Jupyter widget callbacks can run on another thread than
    the one that built the UI. Repeat calls on a thread are harmless."""
    try:
        pythoncom.CoInitialize()
    except pywintypes.com_error:
        pass   # already initialised in another mode (e.g. multi-threaded) - usable as it is


def _service():
    _com_init()
    s = win32com.client.Dispatch('Schedule.Service')
    s.Connect()
    return s


def _get_folder(folder: str | None, create: bool = False):
    path = _norm_folder(folder)
    s = _service()
    try:
        return s, s.GetFolder(path)
    except pywintypes.com_error as e:
        if not (create and _code(e) == 0x80070002):
            with _com(f'Open task folder {path}'):
                raise
    with _com(f'Create task folder {path}'):
        return s, s.GetFolder(ROOT).CreateFolder(path.lstrip('\\'), None)


def _get(name: str, folder: str | None):
    folder, name = _split(name, folder)
    _, f = _get_folder(folder)
    with _com(f'Task {_join(folder, name)}'):
        return f.GetTask(name)


def _join(folder: str, name: str) -> str:
    return folder.rstrip('\\') + '\\' + name


# ── API ───────────────────────────────────────────────────────────────────────
def list_tasks(folder: str = ROOT, include_hidden: bool = True) -> list[TaskInfo]:
    """The tasks directly in `folder` (not in its subfolders), sorted by name."""
    _, f = _get_folder(folder)
    with _com(f'List tasks in {_norm_folder(folder)}'):
        tasks = [_info(t) for t in f.GetTasks(1 if include_hidden else 0)]
    return sorted(tasks, key=lambda i: i.name.lower())


def list_folders(folder: str = ROOT) -> list[str]:
    """Paths of the subfolders directly in `folder`, e.g. ['\\Emerson', '\\Microsoft']."""
    _, f = _get_folder(folder)
    with _com(f'List folders in {_norm_folder(folder)}'):
        return sorted((sub.Path for sub in f.GetFolders(0)), key=str.lower)


def get_task(name: str, folder: str = ROOT) -> TaskInfo:
    """Read one task (TaskSchedulerError with code 0x80070002 if it doesn't exist)."""
    return _info(_get(name, folder))


def task_exists(name: str, folder: str = ROOT) -> bool:
    try:
        _get(name, folder)
        return True
    except TaskSchedulerError as e:
        if e.code == 0x80070002:
            return False
        raise


def _act(names, folder: str, what: str, fn, elevate, op: str, **op_kwargs) -> list[str]:
    """fn(folder_obj, task_name) for each task in `names` (one name or a list); the ones refused with access denied
    are then done together in the elevated helper, after one UAC prompt (elevate 'auto'; True: all of them there).
    Returns the task paths, in order."""
    paths, denied = [], []
    for n in ([names] if isinstance(names, str) else list(names)):
        f_path, n = _split(n, folder)
        path = _join(f_path, n)
        paths.append(path)
        if _elevating(elevate, False):   # elevate=True: straight to the helper
            denied.append(path)
            continue
        try:
            _, f = _get_folder(f_path)
            with _com(f'{what} {path}'):
                fn(f, n)
        except TaskSchedulerError as e:
            if e.code != 0x80070005 or not _elevating(elevate, True):
                raise
            denied.append(path)
    if denied:
        _elevated_call([(op, dict(name=p, **op_kwargs)) for p in denied], f'{what} {", ".join(denied)}')
    return paths


def _one_or_list(names, values):
    return values[0] if isinstance(names, str) else values


def set_enabled(name, enabled: bool, folder: str = ROOT, elevate='auto'):
    """Enable or disable a task, or a list of tasks (-> list of TaskInfo). A disabled task keeps its triggers but
    never starts. elevate: tasks refused with access denied are done after one UAC prompt ('auto'; True: all; False:
    the access denied error instead)."""
    paths = _act(name, folder, 'Enable' if enabled else 'Disable',
                 lambda f, n: setattr(f.GetTask(n), 'Enabled', bool(enabled)), elevate, 'set_enabled', enabled=bool(enabled))
    return _one_or_list(name, [get_task(p) for p in paths])


def enable_task(name, folder: str = ROOT, elevate='auto'):
    return set_enabled(name, True, folder, elevate)


def disable_task(name, folder: str = ROOT, elevate='auto'):
    return set_enabled(name, False, folder, elevate)


def run_task(name, folder: str = ROOT, elevate='auto'):
    """Start a task (or a list of tasks) now, as its own user and settings (like Run in the Task Scheduler UI)."""
    paths = _act(name, folder, 'Run', lambda f, n: f.GetTask(n).Run(None), elevate, 'run_task')
    return _one_or_list(name, [get_task(p) for p in paths])


def stop_task(name, folder: str = ROOT, elevate='auto'):
    """Stop every running instance of a task (or of a list of tasks); the process is terminated."""
    paths = _act(name, folder, 'Stop', lambda f, n: f.GetTask(n).Stop(0), elevate, 'stop_task')
    return _one_or_list(name, [get_task(p) for p in paths])


def delete_task(name, folder: str = ROOT, missing_ok: bool = False, elevate='auto'):
    """Delete a task, or a list of tasks (a running instance keeps running). True per task deleted; False if it
    didn't exist and missing_ok."""
    names = [name] if isinstance(name, str) else list(name)
    present = [n for n in names if not missing_ok or task_exists(n, folder)]
    if present:
        _act(present, folder, 'Delete', lambda f, n: f.DeleteTask(n, 0), elevate, 'delete_task')
    return _one_or_list(name, [n in present for n in names])


def delete_folder(folder: str, elevate='auto') -> None:
    """Delete an empty task folder (Windows refuses one that still has tasks or subfolders). A folder created by an
    elevated registration needs administrator rights to delete: a UAC prompt with elevate 'auto'."""
    path = _norm_folder(folder)
    if path == ROOT:
        raise ValueError('The root task folder cannot be deleted')
    parent, _, name = path.rpartition('\\')
    if _elevating(elevate, False):
        _elevated_call([('delete_folder', dict(folder=path))], f'Delete folder {path}')
        return
    try:
        _, f = _get_folder(parent or ROOT)
        with _com(f'Delete folder {path}'):
            f.DeleteFolder(name, 0)
    except TaskSchedulerError as e:
        if e.code != 0x80070005 or not _elevating(elevate, True):
            raise
        _elevated_call([('delete_folder', dict(folder=path))], f'Delete folder {path}')


def export_xml(name: str, folder: str = ROOT) -> str:
    """The task's full definition as Task Scheduler XML (what the UI's Export writes)."""
    t = _get(name, folder)
    with _com(f'Read XML of {t.Path}'):
        return t.Xml


def _quote(path: str) -> str:
    path = path.strip().strip('"')
    return f'"{path}"' if ' ' in path else path


def register_task(name: str, command: str, arguments: str = '', working_dir: str = '', triggers=(), *,
                  folder: str = ROOT, user: str | None = None, logon: str = 'password', password: str | None = None,
                  run_level: str = 'limited', description: str = '', source: str = '', enabled: bool = True,
                  allow_on_battery: bool = True, multiple_instances: str = 'ignore_new', time_limit_s: int = 0,
                  priority: int = 4, start_when_available: bool = False, restart_count: int = 0,
                  restart_interval_s: int = 60, replace: bool = False, elevate='auto') -> TaskInfo:
    r"""Create a task that runs `command arguments` in `working_dir`; returns it as read back.

    triggers: Trigger objects (at_startup(), at_logon(), daily('08:00'), once(...)) or 'startup' / 'logon';
        empty = run on demand only (run_task).
    folder: task folder, created if missing; a name like r'\Tests\resume_x' sets it too.
    user: run-as account (default: this process's, DOMAIN\user).
    logon: 'password'    - run whether the user is logged on or not, with the account's network access. Windows
                           keeps the password with the task; this tool doesn't store it.
           's4u'         - run whether logged on or not without a password (administrator only); local resources
                           only, no network shares.
           'interactive' - run only while the user is logged on, in their desktop session (windows are visible).
    password: for logon 'password'. None (default): asked for in the Windows password dialog, up to 3 tries.
    run_level: 'limited' or 'highest' (elevated; administrator only).
    priority: 0 (realtime) .. 10 (idle); 4 = normal. Windows' own default is 7 (below normal).
    time_limit_s: stop the task after this long; 0 = never (Windows' own default is 72 h).
    multiple_instances: 'ignore_new' (default), 'parallel', 'queue' or 'stop_existing'.
    restart_count / restart_interval_s: restart a failed task up to this many times (interval >= 60 s).
    replace: overwrite an existing task of the same name (otherwise that is an error).
    source: RegistrationInfo.Source, e.g. a marker so a tool can recognise its own tasks (TaskInfo.source).
    elevate: 'auto' (default) - if this needs administrator rights (needs_admin(), or access denied) and this
                 process isn't elevated, register it in an elevated helper after a UAC prompt; the helper asks for
                 the password in its own Windows dialog, so `password` must be None then.
             True - always through the helper; False - never (access denied instead).
    """
    folder, name = _split(name, folder)
    if logon not in LOGON_TYPES:
        raise ValueError(f'logon {logon!r}: use one of {list(LOGON_TYPES)}')
    if run_level not in RUN_LEVELS:
        raise ValueError(f'run_level {run_level!r}: use one of {list(RUN_LEVELS)}')
    if multiple_instances not in MULTIPLE_INSTANCES:
        raise ValueError(f'multiple_instances {multiple_instances!r}: use one of {list(MULTIPLE_INSTANCES)}')
    if not 0 <= int(priority) <= 10:
        raise ValueError('priority must be 0..10')
    if restart_count and restart_interval_s < 60:
        raise ValueError('restart_interval_s must be at least 60')
    if not command.strip():
        raise ValueError('command is empty')
    triggers = [_as_trigger(t) for t in ([triggers] if isinstance(triggers, (str, Trigger)) else triggers)]
    user = user or current_user()
    path = _join(folder, name)
    settings = dict(command=command, arguments=arguments, working_dir=working_dir, user=user, logon=logon,
                    run_level=run_level, description=description, enabled=enabled, allow_on_battery=allow_on_battery,
                    multiple_instances=multiple_instances, time_limit_s=time_limit_s, priority=priority,
                    start_when_available=start_when_available, restart_count=restart_count,
                    restart_interval_s=restart_interval_s, source=source)

    def elevated():
        if password:
            raise ValueError('An elevated registration asks for the password in its own Windows dialog - leave '
                             'password unset (None)')
        what = '; '.join(str(t) for t in triggers) or 'on demand only'
        _elevated_call([('register_task', dict(name=path, triggers=[_trigger_dict(t) for t in triggers], replace=replace,
                                               **settings))],
                       f'{"Update" if replace else "Add"} task {path} ({what}, {logon}, {run_level})')
        return get_task(path)

    if not replace and task_exists(name, folder):   # before any prompt
        raise TaskSchedulerError(f'Task {path} already exists - pass replace=True to overwrite it', 0x800700B7)
    if _elevating(elevate, needs_admin(triggers, logon, run_level)):
        try:   # create the folder here, not in the helper, so it isn't admin-owned (that makes every later change need admin)
            _get_folder(folder, create=True)
        except TaskSchedulerError:
            pass   # the helper creates it then
        return elevated()
    try:
        s, f = _get_folder(folder, create=True)
        td = _definition(s, path, triggers, **settings)
        ask = logon == 'password' and not password
        for attempt in range(3 if ask else 1):
            pw = (ask_password(user, path, retry=attempt > 0) if ask else password) if logon == 'password' else None
            try:
                with _com(f'Register task {path}'):
                    t = f.RegisterTaskDefinition(name, td, _CREATE_OR_UPDATE if replace else _CREATE, user, pw,
                                                 LOGON_TYPES[logon], '')
                return _info(t)
            except TaskSchedulerError as e:
                if not (ask and e.code == 0x8007052E and attempt < 2):
                    raise
                _notify(f'Wrong password for {user} - asking again (try {attempt + 2} of 3)')
            finally:
                pw = None
    except TaskSchedulerError as e:
        if e.code == 0x80070005 and _elevating(elevate, True) and not password:
            return elevated()
        raise


def _trigger_dict(t: Trigger) -> dict:
    return dict(kind=t.kind, at=t.at.isoformat() if t.at else None, delay_s=t.delay_s, every_days=t.every_days,
                any_user=t.any_user)


def _trigger_from_dict(d: dict) -> Trigger:
    return Trigger(d['kind'], at=_dt.datetime.fromisoformat(d['at']) if d.get('at') else None,
                   delay_s=int(d.get('delay_s', 0)), every_days=int(d.get('every_days', 1)),
                   any_user=bool(d.get('any_user', False)))


def _definition(s, path, triggers, *, command, arguments, working_dir, user, logon, run_level, description, enabled,
                allow_on_battery, multiple_instances, time_limit_s, priority, start_when_available, restart_count,
                restart_interval_s, source=''):
    with _com(f'Build task {path}'):
        td = s.NewTask(0)
        td.RegistrationInfo.Author = user
        td.RegistrationInfo.Description = description
        td.RegistrationInfo.Source = source or ''
        td.Principal.UserId = user
        td.Principal.LogonType = LOGON_TYPES[logon]
        td.Principal.RunLevel = RUN_LEVELS[run_level]
        st = td.Settings
        st.Enabled = bool(enabled)
        st.DisallowStartIfOnBatteries = not allow_on_battery
        st.StopIfGoingOnBatteries = not allow_on_battery
        st.ExecutionTimeLimit = _iso_duration(time_limit_s)
        st.MultipleInstances = MULTIPLE_INSTANCES[multiple_instances]
        st.Priority = int(priority)
        st.StartWhenAvailable = bool(start_when_available)
        if restart_count:
            st.RestartCount = int(restart_count)
            st.RestartInterval = _iso_duration(restart_interval_s)
        for tr in triggers:
            if tr.kind == 'startup':
                ct = td.Triggers.Create(_TRIGGER_BOOT)
            elif tr.kind == 'logon':
                ct = td.Triggers.Create(_TRIGGER_LOGON)
                if not tr.any_user:
                    ct.UserId = user
            else:
                ct = td.Triggers.Create(_TRIGGER_DAILY if tr.kind == 'daily' else _TRIGGER_TIME)
                ct.StartBoundary = f'{tr.at:%Y-%m-%dT%H:%M:%S}'
                if tr.kind == 'daily':
                    ct.DaysInterval = tr.every_days
            if tr.delay_s and tr.kind in ('startup', 'logon'):
                ct.Delay = _iso_duration(tr.delay_s)
        a = td.Actions.Create(_ACTION_EXEC)
        a.Path = _quote(command)
        a.Arguments = arguments or ''
        a.WorkingDirectory = (working_dir or '').strip().strip('"')
    return td
