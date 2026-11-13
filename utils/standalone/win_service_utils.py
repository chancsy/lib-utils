r"""Windows services in Python (pywin32, Windows only): install / uninstall, start / stop, query, restart on crash,
non-admin start / stop for one account, "Log on as a service", the pre-shutdown time, and ServiceBase - a service
class that runs main() until stopped, with an optional pre-shutdown step.

    from utils.standalone import win_service_utils as ws
    ws.install('MyService', r'C:\...\my_service.MyService', 'My service', user=ws.current_user(),
               start='auto', preshutdown_timeout_s=60)       # UAC prompt, then the Windows password dialog
    ws.start('MyService'); ws.stop('MyService'); ws.query('MyService').state   # no prompt for the installing user
    ws.uninstall('MyService')                                  # UAC prompt

    class MyService(ws.ServiceBase):
        _svc_name_ = 'MyService'
        _svc_display_name_ = 'My service'
        def main(self):                  # the service's work, until stop_event is set
            while not self.stop_event.wait(5):
                ...
        def on_preshutdown(self):        # Windows is shutting down / restarting; main() is stopped afterwards
            ...

A Python service runs in pywin32's pythonservice.exe. install() copies it next to this venv's python.exe (there it
finds the venv's pyvenv.cfg and packages) and gives the service a PATH with the base Python folder and
pywin32_system32, since pythonservice.exe needs python3XY.dll and pywintypes3XY.dll before Python starts.

Installing, uninstalling and changing a service need administrator rights. With elevate='auto' (the default) those
calls run in an elevated helper after a UAC prompt (utils.standalone.elevate_utils), so Jupyter / Python stays
non-elevated; start / stop go there only when refused with access denied; set_notify(fn) gets a 'UAC prompt: ...'
notice just before a prompt. elevate=False raises the access denied error instead.
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
import time
import traceback
import winreg
from dataclasses import dataclass

import pywintypes
import servicemanager
import win32api
import win32con
import win32security
import win32service
import win32serviceutil

from . import elevate_utils as _elevate
from .elevate_utils import current_user, is_admin  # noqa: F401 - part of this module's API

START_TYPES = {'auto': win32service.SERVICE_AUTO_START, 'delayed': win32service.SERVICE_AUTO_START,
               'manual': win32service.SERVICE_DEMAND_START, 'disabled': win32service.SERVICE_DISABLED}
_START_NAMES = {win32service.SERVICE_BOOT_START: 'boot', win32service.SERVICE_SYSTEM_START: 'system',
                win32service.SERVICE_AUTO_START: 'auto', win32service.SERVICE_DEMAND_START: 'manual',
                win32service.SERVICE_DISABLED: 'disabled'}
_STATES = {1: 'stopped', 2: 'start pending', 3: 'stop pending', 4: 'running', 5: 'continue pending',
           6: 'pause pending', 7: 'paused'}
# What allow_user_control() grants: start, stop, query and read the service (not change or delete it)
USER_CONTROL_RIGHTS = (win32service.SERVICE_START | win32service.SERVICE_STOP | win32service.SERVICE_QUERY_STATUS
                       | win32service.SERVICE_QUERY_CONFIG | win32service.SERVICE_INTERROGATE
                       | win32service.SERVICE_USER_DEFINED_CONTROL | win32con.READ_CONTROL)
_SERVICES_KEY = r'SYSTEM\CurrentControlSet\Services'

_HINTS = {
    5: 'access denied - installing, uninstalling or changing a service needs administrator rights; '
       'starting / stopping it too, unless allow_user_control() was given for this account',
    1060: 'no such service',
    1069: 'the service could not log on - wrong password, or the account lacks "Log on as a service"',
    1073: 'the service already exists',
    1053: 'the service did not respond in time',
    1056: 'already running',
    1062: 'not running',
    1072: 'marked for deletion - close services.msc / other handles to it, then try again',
}


class ServiceError(Exception):
    """A service call failed; `code` is the Win32 error (e.g. 5 access denied, 1060 no such service)."""

    def __init__(self, msg: str, code: int | None = None):
        super().__init__(msg)
        self.code = code


def _fail(what: str, e: pywintypes.error):
    text = _HINTS.get(e.winerror) or e.strerror
    raise ServiceError(f'{what}: {text} ({e.winerror})', e.winerror) from None


# --- elevation ----------------------------------------------------------------------------------------------------

def _print_notice(msg: str):
    print(msg, flush=True)


_notify = _print_notice


def set_notify(fn) -> None:
    """Where 'UAC prompt: ...' notices go just before a prompt is shown (default: print; None: nowhere)."""
    global _notify
    _notify = fn or (lambda msg: None)


def _elevating(elevate) -> bool:
    if elevate not in (True, False, 'auto'):
        raise ValueError(f'elevate {elevate!r}: use "auto", True or False')
    return elevate is not False and not is_admin()


def _helper(requests: list[tuple[str, dict]], description: str):
    """One UAC prompt for a batch of [(op, kwargs), ...] run in the elevated helper."""
    _notify(f"UAC prompt: {description} - answer it on this PC's screen")
    _elevated_call(requests, description)


@dataclass
class ServiceInfo:
    name: str
    display_name: str
    state: str                # 'running', 'stopped', ...
    pid: int | None
    start: str                # 'auto', 'delayed', 'manual', 'disabled'
    user: str                 # account it runs as, e.g. 'LocalSystem' or 'DOMAIN\user'
    command: str
    description: str
    exit_code: int            # Win32 exit code of the last stop (0 = fine)
    service_exit_code: int


# --- host exe -----------------------------------------------------------------------------------------------------

def host_exe() -> str:
    """pythonservice.exe next to this interpreter (the venv's Scripts folder), copied there from pywin32 if missing or
    different. Next to python.exe, it finds the venv's pyvenv.cfg and so the venv's packages."""
    src = os.path.join(os.path.dirname(win32service.__file__), 'pythonservice.exe')
    dst = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), 'pythonservice.exe')
    if not os.path.isfile(src):
        raise ServiceError(f'pywin32 pythonservice.exe not found: {src}')
    if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(src) \
            or os.path.getmtime(dst) < os.path.getmtime(src):
        shutil.copy2(src, dst)
    return dst


def dll_dirs() -> list[str]:
    """Folders pythonservice.exe needs on PATH: the one with python3XY.dll, and pywin32_system32."""
    return [os.path.dirname(win32api.GetModuleFileName(sys.dllhandle)), os.path.dirname(pywintypes.__file__)]


def _system_path() -> str:
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                        r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment') as k:
        value, kind = winreg.QueryValueEx(k, 'Path')
    return winreg.ExpandEnvironmentStrings(value) if kind == winreg.REG_EXPAND_SZ else value


def _set_environment(name: str, env: dict[str, str]):
    """The service's own environment variables (registry value Environment, REG_MULTI_SZ)."""
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf'{_SERVICES_KEY}\{name}', 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, 'Environment', 0, winreg.REG_MULTI_SZ, [f'{n}={v}' for n, v in env.items()])


def _get_environment(name: str) -> dict[str, str]:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf'{_SERVICES_KEY}\{name}') as k:
            values, _ = winreg.QueryValueEx(k, 'Environment')
    except OSError:
        return {}
    return dict(v.split('=', 1) for v in values if '=' in v)


# --- handles ------------------------------------------------------------------------------------------------------

def _scm(access=win32service.SC_MANAGER_CONNECT):
    try:
        return win32service.OpenSCManager(None, None, access)
    except pywintypes.error as e:
        _fail('Open the Service Control Manager', e)


def _open(name: str, access: int, what: str):
    hscm = _scm()
    try:
        return win32service.OpenService(hscm, name, access)
    except pywintypes.error as e:
        _fail(f'{what} {name}', e)
    finally:
        win32service.CloseServiceHandle(hscm)


class _Handle:
    def __init__(self, name, access, what):
        self.h = _open(name, access, what)

    def __enter__(self):
        return self.h

    def __exit__(self, *exc):
        win32service.CloseServiceHandle(self.h)


# --- account ------------------------------------------------------------------------------------------------------

def _sid(account: str):
    try:
        return win32security.LookupAccountName(None, account)[0]
    except pywintypes.error as e:
        _fail(f'Look up account {account}', e)


def check_password(user: str, password: str) -> bool:
    r"""True if `password` is right for `user` (DOMAIN\user); a network logon, so no logon right is needed."""
    domain, _, name = user.rpartition('\\')
    try:
        h = win32security.LogonUser(name, domain or None, password, win32con.LOGON32_LOGON_NETWORK,
                                    win32con.LOGON32_PROVIDER_DEFAULT)
    except pywintypes.error as e:
        if e.winerror == 1326:
            return False
        _fail(f'Check the password of {user}', e)
    h.Close()
    return True


def has_logon_as_service(account: str) -> bool:
    """True if `account` itself holds "Log on as a service" (rights through a group or a domain policy don't show)."""
    policy = win32security.LsaOpenPolicy(None, win32security.POLICY_LOOKUP_NAMES)
    try:
        rights = win32security.LsaEnumerateAccountRights(policy, _sid(account))
    except pywintypes.error as e:
        if e.winerror == 2:              # no rights at all
            return False
        if e.winerror == 5:
            raise ServiceError(f'Read the rights of {account}: access denied - reading account rights can need '
                               'administrator rights (5)', 5) from None
        _fail(f'Read the rights of {account}', e)
    finally:
        win32security.LsaClose(policy)
    return win32security.SE_SERVICE_LOGON_NAME in rights


def ask_password(user: str, name: str, retry: bool = False) -> str:
    """The Windows password dialog for `user` (user name fixed, nothing saved); ServiceError 1223 if cancelled."""
    try:
        return _elevate.ask_password(user, 'Windows service', f'Password of {user}, to run the service {name} as '
                                     'this account. Windows keeps it with the service.', retry)
    except _elevate.ElevationError as e:
        raise ServiceError(str(e), e.code) from None


def _ask_checked_password(user: str, name: str) -> str:
    """The password dialog, up to 3 tries, each checked with a logon; ServiceError 1326 after the third wrong one."""
    for attempt in range(3):
        password = ask_password(user, name, retry=attempt > 0)
        if check_password(user, password):
            return password
        if attempt < 2:
            _notify(f'Wrong password for {user} - asking again (try {attempt + 2} of 3)')
    raise ServiceError(f'Install {name}: wrong password for {user} three times - nothing installed (1326)', 1326)


def grant_logon_as_service(account: str, elevate='auto') -> None:
    """Give `account` "Log on as a service" (services.msc does this itself when an account is set there; an
    install through the API doesn't). A domain policy that sets this right may replace it at the next refresh."""
    if _elevating(elevate):
        return _helper([('grant_logon_as_service', dict(account=account))],
                       f'Grant "Log on as a service" to {account}')
    try:
        policy = win32security.LsaOpenPolicy(None, win32security.POLICY_ALL_ACCESS)
    except pywintypes.error as e:
        _fail('Open the local security policy', e)
    try:
        win32security.LsaAddAccountRights(policy, _sid(account), [win32security.SE_SERVICE_LOGON_NAME])
    except pywintypes.error as e:
        _fail(f'Grant "Log on as a service" to {account}', e)
    finally:
        win32security.LsaClose(policy)


# --- install / uninstall ------------------------------------------------------------------------------------------

def install(name: str, class_string: str, display_name: str = '', description: str = '', *,
            user: str | None = None, password: str | None = None, start: str = 'auto',
            env: dict[str, str] | None = None, restart_after_s: int | None = 60,
            preshutdown_timeout_s: int | None = None, allow_user: str | None = '',
            grant_logon_right: bool = True, elevate='auto') -> ServiceInfo:
    r"""Install a Python service class (administrator rights: a UAC prompt with elevate='auto').

    class_string: r'C:\path\module.ClassName' - the module file without .py, then the class (pythonservice.exe adds
        the module's folder to sys.path and imports it); win32serviceutil.GetServiceClassString(cls) gives it.
    user: the account to run as (DOMAIN\user); None = LocalSystem.
    password: None = the Windows password dialog asks for it (3 tries, each checked); an elevated install always
        asks there, so it refuses a password argument.
    start: 'auto', 'delayed' (auto, about 2 minutes after boot), 'manual' or 'disabled'.
    env: extra environment variables; PATH always gets the DLL folders (dll_dirs()) in front of the system PATH.
    restart_after_s: restart this long after a crash or a non-zero exit (None: don't).
    preshutdown_timeout_s: how long Windows waits for the service's pre-shutdown work (None: Windows' default).
    allow_user: account allowed to start / stop / query it without administrator rights ('' = `user`, or this
        process's account for LocalSystem; None = nobody).
    grant_logon_right: give `user` "Log on as a service" first.
    """
    if start not in START_TYPES:
        raise ValueError(f'start {start!r}: use one of {", ".join(START_TYPES)}')
    if password is not None and not user:
        raise ValueError('a password without a user: pass user=r"DOMAIN\\user" (no user = LocalSystem)')
    if exists(name):    # before any prompt
        raise ServiceError(f'Install service {name}: {_HINTS[1073]} (1073)', 1073)
    if _elevating(elevate):
        if password:
            raise ValueError('An elevated install asks for the password in its own Windows dialog - leave password '
                             'unset (None)')
        host_exe()      # copy pythonservice.exe here, not in the helper, so the copy isn't admin-owned
        _helper([('install', dict(name=name, class_string=class_string, display_name=display_name,
                                  description=description, user=user, start=start, env=env,
                                  restart_after_s=restart_after_s, preshutdown_timeout_s=preshutdown_timeout_s,
                                  allow_user=allow_user if allow_user != '' else (user or current_user()),
                                  grant_logon_right=grant_logon_right))],
                f'Install service {name} ({class_string}, as {user or "LocalSystem"}, start {start})')
        return query(name)
    if user and password is None:
        password = _ask_checked_password(user, name)
    exe = host_exe()
    if user and grant_logon_right and not has_logon_as_service(user):
        grant_logon_as_service(user, elevate=False)
    try:
        win32serviceutil.InstallService(class_string, name, display_name or name, startType=START_TYPES[start],
                                        userName=user, password=password, exeName=exe,
                                        description=description or None,
                                        delayedstart=True if start == 'delayed' else None)
    except pywintypes.error as e:
        _fail(f'Install service {name}', e)
    finally:
        password = None
    path = os.pathsep.join(dll_dirs() + [_system_path()])
    _set_environment(name, {**(env or {}), 'PATH': path})
    if restart_after_s is not None:
        set_recovery(name, restart_after_s, elevate=False)
    if preshutdown_timeout_s is not None:
        set_preshutdown_timeout(name, preshutdown_timeout_s, elevate=False)
    if allow_user is not None:
        allow_user_control(name, allow_user or user or current_user(), elevate=False)
    return query(name)


def uninstall(name: str, timeout_s: float = 30, missing_ok: bool = False, elevate='auto') -> None:
    """Stop the service if it runs, then remove it (administrator rights: a UAC prompt with elevate='auto')."""
    if not exists(name):
        if missing_ok:
            return
        raise ServiceError(f'Uninstall {name}: {_HINTS[1060]} (1060)', 1060)
    if _elevating(elevate):
        return _helper([('uninstall', dict(name=name, timeout_s=timeout_s, missing_ok=True))],
                       f'Uninstall service {name}')
    if query(name).state != 'stopped':
        stop(name, timeout_s, elevate=False)
    try:
        win32serviceutil.RemoveService(name)
    except pywintypes.error as e:
        _fail(f'Uninstall {name}', e)


# --- start / stop / query -----------------------------------------------------------------------------------------

def exists(name: str) -> bool:
    hscm = _scm()
    try:
        win32service.CloseServiceHandle(win32service.OpenService(hscm, name, win32service.SERVICE_QUERY_STATUS))
        return True
    except pywintypes.error as e:
        if e.winerror == 1060:
            return False
        _fail(f'Open {name}', e)
    finally:
        win32service.CloseServiceHandle(hscm)


def _wait(name: str, state: str, timeout_s: float) -> ServiceInfo:
    end = time.monotonic() + timeout_s
    while True:
        info = query(name)
        if info.state == state or time.monotonic() > end:
            return info
        time.sleep(0.5)


def _control(name: str, op: str, fn, elevate, timeout_s: float):
    """fn() in this process; refused with access denied (and elevate 'auto'), the same call in the helper.
    elevate=True: straight to the helper."""
    if elevate is True and not is_admin():
        return _helper([(op, dict(name=name, timeout_s=timeout_s))], f'{op.capitalize()} service {name}')
    try:
        fn()
    except ServiceError as e:
        if e.code != 5 or not _elevating(elevate):
            raise
        _helper([(op, dict(name=name, timeout_s=timeout_s))], f'{op.capitalize()} service {name}')


def start(name: str, timeout_s: float = 30, elevate='auto') -> ServiceInfo:
    """Start the service and wait until it runs (or stops again, e.g. a logon failure). Without start permission
    (allow_user_control) and elevate='auto': a UAC prompt."""
    def go():
        with _Handle(name, win32service.SERVICE_START, 'Start') as h:
            try:
                win32service.StartService(h, None)
            except pywintypes.error as e:
                if e.winerror != 1056:
                    _fail(f'Start {name}', e)
    _control(name, 'start', go, elevate, timeout_s)
    end = time.monotonic() + timeout_s
    while True:
        info = query(name)
        if info.state in ('running', 'stopped') or time.monotonic() > end:
            break
        time.sleep(0.5)
    if info.state == 'stopped':
        raise ServiceError(f'Start {name}: it stopped again (exit code {info.exit_code}, service exit code '
                           f'{info.service_exit_code}); see its log / the System event log', info.exit_code)
    return info


def stop(name: str, timeout_s: float = 30, elevate='auto') -> ServiceInfo:
    """Stop the service and wait until it has stopped. Without stop permission (allow_user_control) and
    elevate='auto': a UAC prompt."""
    def go():
        with _Handle(name, win32service.SERVICE_STOP, 'Stop') as h:
            try:
                win32service.ControlService(h, win32service.SERVICE_CONTROL_STOP)
            except pywintypes.error as e:
                if e.winerror != 1062:
                    _fail(f'Stop {name}', e)
    _control(name, 'stop', go, elevate, timeout_s)
    info = _wait(name, 'stopped', timeout_s)
    if info.state != 'stopped':
        raise ServiceError(f'Stop {name}: still {info.state} after {timeout_s:.0f} s')
    return info


def query(name: str) -> ServiceInfo:
    with _Handle(name, win32service.SERVICE_QUERY_STATUS | win32service.SERVICE_QUERY_CONFIG, 'Query') as h:
        try:
            st = win32service.QueryServiceStatusEx(h)
            cfg = win32service.QueryServiceConfig(h)
            try:
                desc = win32service.QueryServiceConfig2(h, win32service.SERVICE_CONFIG_DESCRIPTION) or ''
                delayed = win32service.QueryServiceConfig2(h, win32service.SERVICE_CONFIG_DELAYED_AUTO_START_INFO)
            except pywintypes.error:
                desc, delayed = '', False
        except pywintypes.error as e:
            _fail(f'Query {name}', e)
    start_name = _START_NAMES.get(cfg[1], str(cfg[1]))
    if start_name == 'auto' and delayed:
        start_name = 'delayed'
    return ServiceInfo(name=name, display_name=cfg[8], state=_STATES.get(st['CurrentState'], str(st['CurrentState'])),
                       pid=st['ProcessId'] or None, start=start_name, user=cfg[7], command=cfg[3], description=desc,
                       exit_code=st['Win32ExitCode'], service_exit_code=st['ServiceSpecificExitCode'])


def environment(name: str) -> dict[str, str]:
    """The service's own environment variables, as install() set them."""
    return _get_environment(name)


# --- settings -----------------------------------------------------------------------------------------------------

def set_recovery(name: str, restart_after_s: int = 60, reset_after_s: int = 86400, times: int = 3,
                 elevate='auto') -> None:
    """Restart the service `restart_after_s` after a crash, or after it stops with a non-zero exit code; up to
    `times` restarts, counted again after `reset_after_s` without one."""
    actions = {'ResetPeriod': reset_after_s, 'RebootMsg': None, 'Command': None,
               'Actions': [(win32service.SC_ACTION_RESTART, restart_after_s * 1000)] * times}
    if _elevating(elevate):
        return _helper([('set_recovery', dict(name=name, restart_after_s=restart_after_s, reset_after_s=reset_after_s,
                                              times=times))], f'Set recovery of service {name}')
    with _Handle(name, win32service.SERVICE_CHANGE_CONFIG | win32service.SERVICE_START, 'Set recovery of') as h:
        try:
            win32service.ChangeServiceConfig2(h, win32service.SERVICE_CONFIG_FAILURE_ACTIONS, actions)
            win32service.ChangeServiceConfig2(h, win32service.SERVICE_CONFIG_FAILURE_ACTIONS_FLAG, True)
        except pywintypes.error as e:
            _fail(f'Set recovery of {name}', e)


def set_preshutdown_timeout(name: str, seconds: int, elevate='auto') -> None:
    """How long Windows waits for the service's pre-shutdown work before going on with the shutdown."""
    if _elevating(elevate):
        return _helper([('set_preshutdown_timeout', dict(name=name, seconds=seconds))],
                       f'Set the pre-shutdown time of service {name} to {seconds} s')
    with _Handle(name, win32service.SERVICE_CHANGE_CONFIG, 'Set the pre-shutdown time of') as h:
        try:
            win32service.ChangeServiceConfig2(h, win32service.SERVICE_CONFIG_PRESHUTDOWN_INFO, int(seconds * 1000))
        except pywintypes.error as e:
            _fail(f'Set the pre-shutdown time of {name}', e)


def preshutdown_timeout_s(name: str) -> float | None:
    with _Handle(name, win32service.SERVICE_QUERY_CONFIG, 'Query') as h:
        try:
            return win32service.QueryServiceConfig2(h, win32service.SERVICE_CONFIG_PRESHUTDOWN_INFO) / 1000
        except pywintypes.error:
            return None


def allow_user_control(name: str, account: str, rights: int = USER_CONTROL_RIGHTS, elevate='auto') -> None:
    """Let `account` start, stop and query the service without administrator rights (an entry in its DACL)."""
    if _elevating(elevate):
        return _helper([('allow_user_control', dict(name=name, account=account, rights=rights))],
                       f'Let {account} start / stop service {name}')
    sid = _sid(account)
    with _Handle(name, win32con.READ_CONTROL | win32con.WRITE_DAC, 'Change permissions of') as h:
        try:
            sd = win32service.QueryServiceObjectSecurity(h, win32security.DACL_SECURITY_INFORMATION)
            dacl = sd.GetSecurityDescriptorDacl()
            for i in range(dacl.GetAceCount()):
                (ace_type, _), mask, ace_sid = dacl.GetAce(i)
                if ace_type == win32security.ACCESS_ALLOWED_ACE_TYPE and ace_sid == sid and mask & rights == rights:
                    return
            dacl.AddAccessAllowedAce(win32security.ACL_REVISION, rights, sid)
            sd.SetSecurityDescriptorDacl(1, dacl, 0)
            win32service.SetServiceObjectSecurity(h, win32security.DACL_SECURITY_INFORMATION, sd)
        except pywintypes.error as e:
            _fail(f'Change permissions of {name}', e)


# --- ServiceBase ---------------------------------------------------------------------------------------------------

class ServiceBase(win32serviceutil.ServiceFramework):
    _svc_name_ = ''
    _svc_display_name_ = ''
    accept_preshutdown = True        # ask Windows for the pre-shutdown notice
    stop_wait_hint_s = 30            # how long a stop may take before Windows thinks the service hangs

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = threading.Event()
        self.stop_reason = ''
        self._status_lock = threading.Lock()

    # --- override these ---

    def main(self):
        """The service's work; return when `stop_event` is set."""
        self.stop_event.wait()

    def on_preshutdown(self):
        """Called in its own thread when Windows announces a shutdown / restart, before `stop_event` is set."""

    def log_error(self, text: str):
        """Write to the Application event log (source = the service name)."""
        servicemanager.LogErrorMsg(text)

    # --- pywin32 plumbing ---

    def GetAcceptedControls(self):
        accepted = super().GetAcceptedControls()
        if self.accept_preshutdown:
            accepted |= win32service.SERVICE_ACCEPT_PRESHUTDOWN
        return accepted

    def _report(self, state, wait_hint_s: float = 0):
        with self._status_lock:
            self.ReportServiceStatus(state, waitHint=int(wait_hint_s * 1000))

    def _request_stop(self, reason: str):
        if not self.stop_reason:
            self.stop_reason = reason
        self._report(win32service.SERVICE_STOP_PENDING, self.stop_wait_hint_s)
        self.stop_event.set()

    def SvcStop(self):
        self._request_stop('stop')

    def SvcShutdown(self):
        self._request_stop('shutdown')

    def SvcOtherEx(self, control, event_type, data):
        if control == win32service.SERVICE_CONTROL_PRESHUTDOWN:
            if not self.stop_reason:
                self.stop_reason = 'preshutdown'
                threading.Thread(target=self._preshutdown, name='preshutdown', daemon=True).start()
            return
        return super().SvcOtherEx(control, event_type, data)

    def _preshutdown(self):
        done = threading.Event()

        def keep_alive():            # STOP_PENDING with a rising checkpoint tells Windows we're still working
            while not done.wait(2):
                self._report(win32service.SERVICE_STOP_PENDING, 10)

        self._report(win32service.SERVICE_STOP_PENDING, 10)
        threading.Thread(target=keep_alive, name='preshutdown keep-alive', daemon=True).start()
        try:
            self.on_preshutdown()
        except Exception:
            self.log_error(f'{self._svc_name_} pre-shutdown failed:\n{traceback.format_exc()}')
        finally:
            done.set()
            self._report(win32service.SERVICE_STOP_PENDING, self.stop_wait_hint_s)
            self.stop_event.set()

    def SvcDoRun(self):
        servicemanager.LogInfoMsg(f'{self._svc_name_} started')
        try:
            self.main()
        except Exception:
            self.log_error(f'{self._svc_name_} stopped with an error:\n{traceback.format_exc()}')
            raise
        servicemanager.LogInfoMsg(f'{self._svc_name_} stopped ({self.stop_reason or "main() returned"})')


def run_in_console(cls, seconds: float | None = None):
    """Run a ServiceBase subclass's main() in this process, without the Service Control Manager (development):
    Ctrl+C or `seconds` stops it. Pre-shutdown never happens here."""
    svc = cls.__new__(cls)
    svc.ssh = None                   # ReportServiceStatus is a no-op without a status handle
    svc.checkPoint = 0
    svc.stop_event = threading.Event()
    svc.stop_reason = ''
    svc._status_lock = threading.Lock()
    if seconds is not None:
        threading.Timer(seconds, svc._request_stop, args=('stop',)).start()
    t = threading.Thread(target=svc.main, name='main')
    t.start()
    try:
        while t.is_alive():
            t.join(0.5)
    except KeyboardInterrupt:
        svc._request_stop('stop')
        t.join()
    return svc


# --- the elevated side (utils.standalone.elevate_utils runs these after the UAC prompt) ----------------------------

OPS = ('install', 'uninstall', 'start', 'stop', 'set_recovery', 'set_preshutdown_timeout', 'allow_user_control',
       'grant_logon_as_service')    # the only calls the elevated helper accepts; they run with elevate=False
ELEVATED_TIMEOUT_S = 600


def run_op(op: str, kwargs: dict) -> None:
    """One call, in the elevated helper."""
    globals()[op](**kwargs, elevate=False)


def _elevated_call(requests: list[tuple[str, dict]], description: str, timeout_s: float = ELEVATED_TIMEOUT_S,
                   _verb: str = 'runas') -> None:
    """Run [(op, kwargs), ...] in one elevated helper; ServiceError if the UAC prompt is declined or a call fails.
    The request never holds a password: install() with a user account asks for it in the helper's own dialog.
    _verb='open' runs the helper without elevation (tests of the plumbing only)."""
    try:
        _elevate.call(__name__, requests, description, timeout_s, _verb)
    except _elevate.ElevationError as e:
        if e.code in (_elevate.CANCELLED, _elevate.UNEXPECTED, _elevate.TIMEOUT) or e.code is None:
            raise ServiceError(str(e), None if e.code == _elevate.TIMEOUT else e.code) from None
        try:
            text = _HINTS.get(e.code) or win32api.FormatMessage(e.code).strip()
        except Exception:
            text = 'failed'
        more = ' (the ones before it were done)' if len(requests) > 1 else ''
        raise ServiceError(f'{description} (elevated): {text} ({e.code}){more}', e.code) from None
