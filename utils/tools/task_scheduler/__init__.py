r"""Task Scheduler - add, list, enable / disable, run / stop and remove Windows scheduled tasks, e.g. to start a
monitor at boot or resume a test script after a restart. Basic settings only; export_xml() shows the full definition.

UI: task_scheduler.py (jupytext py:percent; run it in Jupyter, or call show_gui()).

API (requires pywin32; a TaskSchedulerError says what failed and why, e.g. access denied or a wrong password):
    add_python_script(r'C:\...\restart_mon.py', name='RestartMon', triggers=[at_startup()])
                                    # this interpreter (e.g. the venv's python.exe), in the script's folder;
                                    # UAC prompt + Windows password dialog (at startup needs administrator rights)
    register_task('Name', r'C:\Tools\tool.exe', '--arg', r'C:\Tools', [daily('08:00')], logon='interactive')
    list_tasks()                    # TaskInfo for each task in the root folder: state, triggers, last run / result
    enable_task('RestartMon'); disable_task('RestartMon'); run_task('RestartMon'); stop_task('RestartMon')
    delete_task('RestartMon', missing_ok=True)
    disable_task(['a', 'b'], folder='\\Tests')   # a list of tasks: at most one UAC prompt for all of them
    delete_folder('\\Tests')                     # an empty task folder
    export_xml('RestartMon')        # full XML definition

Triggers: at_startup(delay_s=0), at_logon(delay_s=0, any_user=False), daily('08:00', every_days=1),
once('2026-11-10 18:00'); none = run on demand only.

Logon ('Run whether user is logged on or not' in the Task Scheduler UI):
    'password'    (default) runs whether logged on or not, with the account's network access. The password is asked
                  for in the Windows password dialog (or passed as password=...) each time a task is registered;
                  Windows keeps it with the task, this tool doesn't store it.
    'interactive' runs only while the user is logged on, in their desktop session - for scripts with windows/plots.
    's4u'         runs whether logged on or not without a password; local resources only (administrator only).

Administrator rights: an at-startup trigger, an at-log-on trigger for any user, logon 's4u', run level 'highest',
changing (e.g. enabling / disabling) a task registered with administrator rights - even your own - deleting anything
in a folder created with them, and other users' tasks need them. Running such a task (run_task) doesn't, and neither
does deleting it from a folder created without them. Jupyter / Python stays non-elevated: with elevate='auto' (the default)
just that one call runs in an elevated helper after a UAC prompt (_elevated.py); elevate=False gives access denied
(0x80070005) instead. needs_admin(triggers, logon, run_level) tells in advance. Just before a prompt a notice says
what it is for ('UAC prompt: Disable \\Tests\\a'; print by default, set_notify(fn) to send it elsewhere); the
prompt's "Show more details" shows the same description.
"""
from __future__ import annotations

import os
import sys

from ._winsched import (LOGON_TYPES, MULTIPLE_INSTANCES, ROOT, RUN_LEVELS, TaskInfo, TaskSchedulerError, Trigger,
                        ask_password, at_logon, at_startup, current_user, daily, delete_folder, delete_task,
                        disable_task, enable_task, export_xml, get_task, is_admin, list_folders, list_tasks, needs_admin,
                        once, register_task, result_text, run_task, set_enabled, set_notify, stop_task, task_exists)
from ._winsched import _quote


def default_python() -> str:
    """The interpreter running this code (in Jupyter: the kernel's, e.g. the venv's python.exe)."""
    return sys.executable


def add_python_script(script: str, name: str | None = None, args: str = '', triggers=(at_startup(),), *,
                      python: str | None = None, working_dir: str | None = None, **kwargs) -> TaskInfo:
    r"""Register a task that runs `python script args` in `working_dir` (default: the script's folder).

    name: task name (default: the script's file name without .py); may include a folder, r'\Tests\resume_x'.
    triggers: default at startup (needs administrator rights: a UAC prompt with elevate='auto'); see register_task
        for the rest (logon, password, replace, priority, elevate, ...).
    """
    script = os.path.abspath(script)
    if not os.path.isfile(script):
        raise FileNotFoundError(f'Script not found: {script}')
    python = python or default_python()
    if not os.path.isfile(python.strip('"')):
        raise FileNotFoundError(f'Python not found: {python}')
    arguments = _quote(script) + (f' {args}' if args else '')
    name = name or os.path.splitext(os.path.basename(script))[0]
    return register_task(name, python, arguments, working_dir or os.path.dirname(script), triggers, **kwargs)
