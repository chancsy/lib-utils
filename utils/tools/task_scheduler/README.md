# Task Scheduler

Add, list, enable / disable, run, stop and remove Windows scheduled tasks from Jupyter or Python. Use it, for example, to start a monitor at boot, or to resume a test script after a restart. It covers the basic settings; for anything else, **Show XML** / `export_xml()` gives a task's full definition.

Jupyter and Python stay **non-elevated**. A change that needs administrator rights runs in a short-lived elevated helper after a **UAC prompt**, and only that change.

Requires pywin32; the UI also needs ipywidgets. Windows only.

## Files

| File | What |
|---|---|
| `__init__.py` | API summary and `add_python_script()` |
| `_winsched.py` | Task Scheduler COM API (`Schedule.Service`): register, list, change, delete; triggers; errors |
| `_elevated.py` | The calls the elevated helper may make for this tool (`OPS`, `run_op`); the helper is the shared `utils/standalone/elevate_utils.py` |
| `task_scheduler.py` | UI (jupytext py:percent); `show_gui(folder)` returns the widget |
| `tool.toml` | Manifest for the lib-utils tools launcher |

## UI

Run `task_scheduler.py` as a notebook, open it from the lib-utils tools launcher, or:

```python
from utils.tools.task_scheduler.task_scheduler import show_gui
display(show_gui())
```

- **Task table** of one folder: State, Triggers, Runs as, Last run, Last result (e.g. `success`, `exit code 3`, `logon failure`), Next run, Action.
- **Buttons:**
  - Enable / Disable / Run now / Stop;
  - Remove (click twice);
  - Show XML;
  - Load into form (copies a task into the form, to change it and update it);
  - Delete folder (empty folders only, click twice).

  All selected tasks go in one call, so the ones that need administrator rights share one UAC prompt.
- **Add / update form:** program or `.py` script (with the python.exe to run it), arguments, start-in folder, trigger and delay / time, security option, run-as user, priority, time limit, enabled, run on battery, highest privileges, replace.
- **Log:** a "UAC prompt: ..." line appears just before each prompt, so you know what the prompt is for.

## API

```python
from utils.tools import task_scheduler as ts

ts.add_python_script(r'C:\...\restart_mon.py', name='RestartMon', triggers=[ts.at_startup()])
ts.register_task('Name', r'C:\Tools\tool.exe', '--arg', r'C:\Tools', [ts.daily('08:00')], logon='interactive')
ts.list_tasks()                                   # TaskInfo per task in the root folder
ts.enable_task('RestartMon'); ts.disable_task('RestartMon'); ts.run_task('RestartMon'); ts.stop_task('RestartMon')
ts.disable_task(['a', 'b'], folder='\\Tests')     # a list: at most one UAC prompt for all of them
ts.delete_task('RestartMon', missing_ok=True)
ts.delete_folder('\\Tests')                       # an empty task folder
ts.export_xml('RestartMon')                       # full XML definition
```

- **`add_python_script(script, name, args, triggers, python=..., working_dir=...)`** runs the script with this interpreter (in Jupyter, the kernel's, e.g. the venv's python.exe), in the script's folder.
- **`register_task(...)`** takes:
  - `folder` (created if missing; a name like `r'\Tests\x'` sets it too);
  - `user`, `logon`, `password`, `run_level`;
  - `priority`, `time_limit_s`, `allow_on_battery`, `multiple_instances`, `start_when_available`, `restart_count` / `restart_interval_s`;
  - `description`;
  - `source` (a marker, read back as `TaskInfo.source`, so a tool can recognise its own tasks; see work_dir's Test Tasks);
  - `replace`, `elevate`.
- **Triggers:** `at_startup(delay_s=0)`, `at_logon(delay_s=0, any_user=False)`, `daily('08:00', every_days=1)`, `once('2026-11-10 18:00')`. With no trigger, the task runs on demand only.
- **Errors:** `TaskSchedulerError` says what failed and why (access denied, logon failure, not found, ...). `.code` holds the HRESULT.
- **Helpers:** `needs_admin(triggers, logon, run_level)`, `is_admin()`, `current_user()`, `result_text(code)`, `set_notify(fn)` (where the "UAC prompt: ..." notices go; default `print`).

### Defaults

The defaults suit monitors and test scripts, and differ from Windows' own:

| Setting | Default here | Windows' default |
|---|---|---|
| Time limit | none | 72 h |
| Priority | 4 (normal) | 7 (below normal) |
| Run on battery | allowed | not allowed |
| Second instance while one runs | ignored | ignored |

## Security options (`logon`)

| `logon` | Task Scheduler's wording | Notes |
|---|---|---|
| `password` (default) | Run whether user is logged on or not | Runs in the background, with no windows or plots, and has the account's network access. The password is needed every time the task is added or updated: the Windows password dialog asks for it (user name fixed, nothing saved, up to 3 tries), or a script passes `password=`. Windows stores it with the task; this tool never stores, prints or logs it. |
| `interactive` | Run only when user is logged on | Runs in the user's desktop session, so windows are visible. No password. |
| `s4u` | Run whether user is logged on or not, "Do not store password" | Local resources only, no network shares. Needs administrator rights. |

## Administrator rights and the UAC prompt

**What needs administrator rights:**
- an at-startup trigger (Windows refuses it before even checking the password);
- an at-log-on trigger for any user;
- logon `s4u`;
- run level `highest`;
- **changing a task that was registered with administrator rights, even your own,** e.g. enabling or disabling it;
- deleting a task or folder in a folder that was created with administrator rights;
- other users' tasks.

Running a task registered with administrator rights (`run_task`) doesn't need them. Neither does deleting it, when its folder was created without them. Neither does anything with your own at-log-on, daily, once or on-demand tasks, nor creating a folder.

`elevate` (on every call that changes something):
- **`'auto'` (default):**
  - registration goes to the elevated helper when `needs_admin()` says so and the process isn't elevated;
  - other calls are tried normally, and the tasks refused with access denied then go to the helper together.
- **`True`:** always the helper.
- **`False`:** never; the access denied error is raised instead.

**The elevated helper** (the shared [`utils/standalone/elevate_utils.py`](../../standalone/elevate_utils.py), also used by `win_service_utils`; `_elevated.py` lists the calls it may make for this tool):
- **Start:** it runs with the same interpreter (pythonw.exe if present, so no console window), via "run as administrator", which shows the UAC prompt.
- **One prompt per batch.**
- **Command line:**
  - a plain description of the change, e.g. `Disable \Tests\a, \Tests\b`, followed by the module whose calls it makes (`utils.tools.task_scheduler._elevated`) and the request as readable JSON (`"op": "register_task"`, `"logon": "password"`, the command, ...);
  - the prompt's "Show more details" shows all of it under "Program location";
  - it is fixed once the prompt is shown;
  - it never holds a password: for logon `password` the helper asks for it in its own password dialog. So an elevated registration refuses a `password=` argument.
- **Result:** comes back as the helper's exit code. The non-elevated side and the elevated side share no files.
- **Allowed calls:** only registering, enabling / disabling, running, stopping and deleting tasks, and deleting folders.
- **Waiting:**
  - **while the UAC prompt is open,** the call waits as long as it takes, because Windows only starts the helper after Yes;
  - **after Yes,** it waits up to 10 minutes for the helper to finish, i.e. for the password dialog to be answered and the change to be made. After that it stops waiting and says "No answer from the elevated helper within 600 s"; the change still happens if the password is entered later.
- **Declined:** a declined UAC prompt or a cancelled password dialog gives `TaskSchedulerError` code 1223, "nothing changed".

**Folders:** an elevated registration creates its folder first without elevation, so the folder isn't admin-owned. Then tasks in it can be deleted without administrator rights; in an admin-created folder, deleting them needs administrator rights too.

**The UAC prompt** shows "Verified publisher: Python Software Foundation", and as the program name the file description of the venv's `pythonw.exe`, e.g. "Built: Release_v3.12.3_20240409.01". Windows takes both from the exe.

The elevated helper runs Python and this package from the venv, which the non-elevated user can write to. Elevating any user-installed Python has that property.

## Notes

- **The UAC prompt and the password dialog appear on the screen of the PC that runs Jupyter,** not in the browser, and the UI waits for them. The UAC prompt covers the whole screen; a script should pause before it.
- **A wrong password is retried:** the dialog asks again ("Wrong password - try again") up to 3 times, with a notice each time ("asking again (try 2 of 3)"). After the third it gives up with "logon failure", and nothing is registered.
- **COM is initialised on each calling thread.** Jupyter widget callbacks can run on a different thread from the one that built the UI.
- **Resuming a test after a restart is the script's job** (a checkpoint, then continuing from it). This tool only starts the script.
