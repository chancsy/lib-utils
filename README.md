# lib-utils

Personal Python utility library with helper funtions, wrappers, for engineering and game automation,

## Installation

### As a submodule (recommended — live edits reflected immediately)

```bash
git submodule add <repo-url> lib-utils
pip install -e lib-utils
```

### Direct from GitHub (no clone needed)

```bash
pip install git+https://github.com/<user>/lib-utils.git@<tag>
```

### With optional extras

```bash
pip install -e "lib-utils[crypto]"
pip install -e "lib-utils[pdf,slack]"
pip install -e "lib-utils[all]"        # all extras except win
pip install -e "lib-utils[all,win]"    # include Windows automation
pip install -e "lib-utils[tools]"      # the tools under utils/tools (Windows): pywin32, ipywidgets
```

## Package layout

```
utils/
├── __init__.py             # re-exports UtilityFunctions via wildcard import
├── utilities.py            # UtilityFunctions class (all _internal mixins composed here)
├── _internal/              # core mixins — always available, no optional deps
│   ├── util_binary.py      # struct packing, bit ops, hex/base64 helpers
│   ├── util_collections.py # list/dict helpers
│   ├── util_dataframe.py   # pandas DataFrame helpers          [requires: pandas]
│   ├── util_demo.py        # interactive CLI/widget demo runner
│   ├── util_filesystem.py  # file/directory helpers
│   ├── util_ipython.py     # IPython display helpers           [requires: IPython]
│   ├── util_lan_monitor.py # LAN heartbeat client/server
│   ├── util_output.py      # print helpers, TeeStringIO
│   ├── util_runtime.py     # OS/env/package introspection
│   ├── util_testing.py     # test utilities
│   ├── util_text.py        # string/text helpers
│   ├── util_threads.py     # StoppableThread
│   ├── util_time.py        # timing, timestamps, IntervalTimer
│   └── util_web.py         # urllib download helpers, webhook
├── standalone/             # optional modules — import explicitly, check deps at load time
│   ├── clipboard_utils.py      [requires: pyperclip]
│   ├── cryptography_utils.py   [requires: cryptography]
│   ├── electronics_utils.py    [requires: eseries, sympy]
│   ├── elevate_utils.py        [requires: pywin32] (Windows) — on-demand UAC: a module's listed calls run in a short-lived elevated helper, one prompt per batch; Windows password dialog
│   ├── log_actions.py          [stdlib only]
│   ├── math_utils.py           [requires: numpy, sympy]
│   ├── pdf_utils.py            [requires: pikepdf]
│   ├── selenium_utils.py       [requires: selenium, webdriver_manager]
│   ├── slack_utils.py          [requires: slack_sdk]
│   ├── solidworks_pdm_utils.py [requires: pywin32] (Windows only — SolidWorks PDM must be installed)
│   ├── sql_utils.py            [requires: pyodbc]
│   ├── sqlite_utils.py         [stdlib only]
│   ├── ui_utils.py             [stdlib only — tkinter]
│   ├── widget_utils.py         [requires: ipywidgets, IPython] (Jupyter only)
│   ├── win_automation_utils.py [requires: pywin32, pygetwindow, pyautogui, pynput, pycaw] (Windows only)
│   └── win_service_utils.py    [requires: pywin32] (Windows) — Python Windows services: install / uninstall (UAC on demand), start / stop, restart on crash, pre-shutdown time, non-admin control; ServiceBase
└── tools/                  # apps, not the core library: a UI plus its API each — run directly or import to orchestrate; need the [tools] extra (region_setup: [cv])
    ├── env_path_editor/        [UI: ipywidgets] (Windows) — view/check/edit the User and System PATH, with backup
    │   └── env_path_editor.py        # py:percent UI; API in __init__.py (e.g. update_user_path)
    ├── launcher.py             [UI: ipywidgets] — one button per tool folder with a tool.toml (name, entry, description); embedded by work_dir/tools_launcher.py
    ├── portable_apps_manager/[requires: requests, truststore, ipywidgets; 7-Zip for .7z assets] (Windows) — deploy/track/update portable apps from GitHub releases or download URLs
    │   ├── portable_apps_manager.py  # py:percent UI; registry is <root>/portable_apps.ini, install manifests in <root>/portable_apps.manifests/
    │   └── apps_catalog.ini          # shared recipes: how each app is best tracked (Add → From catalog)
    ├── region_setup.py         [requires: opencv-python, numpy, tkinter] — ADB screen region selector
    └── task_scheduler/         [requires: pywin32; UI: ipywidgets] (Windows) — add/list/enable/disable/run/stop/remove scheduled tasks
        ├── task_scheduler.py         # py:percent UI; API in __init__.py (e.g. add_python_script)
        └── _elevated.py              # the calls the elevated helper (standalone/elevate_utils) may make: a UAC prompt only for changes that need administrator rights
```

## Usage

```python
from utils import UtilityFunctions
utils = UtilityFunctions()

# Core helpers (always available)
utils.get_datetimestamp()
utils.interpolate(12, [4, 20], [0, 100])   # → 50.0
utils.uint16_to_bytes(1234, endian='BE')

# Standalone modules — import explicitly
from utils.standalone.clipboard_utils import Clipboard
from utils.standalone.cryptography_utils import Cryptography
from utils.standalone.electronics_utils import Electronics
from utils.standalone.log_actions import PrintLogger, print_logging_start, print_logging_end, new_log, add_lines
from utils.standalone.math_utils import MathUtils, EquationSolver, IntegerLimits
from utils.standalone.pdf_utils import PdfUtils
from utils.standalone.selenium_utils import SeleniumUtils
from utils.standalone.slack_utils import SlackUtils
from utils.standalone.solidworks_pdm_utils import SolidWorksPDM          # Windows only
from utils.standalone.sql_utils import SQL
from utils.standalone.sqlite_utils import SQLite
from utils.standalone.ui_utils import UIUtils
from utils.standalone.widget_utils import Widgets, MultiSelectMoveButtons, TabbedTextareaPanel, WidgetStdout, FileBrowser, build_lib_demo_widget  # Jupyter only
from utils.standalone.win_automation_utils import WindowManager, InputSimulator, WindowPos, WindowSize, MousePos, WindowInfo  # Windows only
from utils.standalone import win_service_utils as ws                     # Windows only: ws.install(...), ws.start(...), ws.ServiceBase
from utils.standalone import elevate_utils                               # Windows only: elevate_utils.call(module, requests, description)

# Tools — import to orchestrate, or run directly
from utils.tools.region_setup import RegionSetupTool
from utils.tools.launcher import show_gui, discover_tools                        # all tools with a tool.toml
from utils.tools.env_path_editor.env_path_editor import show_gui                # Jupyter: display(show_gui())
from utils.tools.env_path_editor import update_user_path, add_user_path, in_path  # no UI
from utils.tools.portable_apps_manager.portable_apps_manager import show_gui    # Jupyter: display(show_gui())
from utils.tools.portable_apps_manager import AppsConfig, check, prepare, finish  # same steps, no UI
from utils.tools.task_scheduler.task_scheduler import show_gui                  # Jupyter: display(show_gui())
from utils.tools.task_scheduler import add_python_script, at_startup, list_tasks, enable_task, disable_task, delete_task  # no UI
```

## Optional dependency check

Standalone modules call `utils.exit_if_module_missing()` at import time and print an install hint if a required package is absent:

```
slack_sdk is not installed. To install, please run:
  pip install slack_sdk
```

## Requirements

- Python >= 3.11
- Core: `numpy>=2.3`, `pandas>=2.3`, `ipython>=9.15.0`
- Optional: see [pyproject.toml](pyproject.toml) `[project.optional-dependencies]`

`IPython` is declared as a core dependency (not optional) because `utils/_internal/util_ipython.py`
is mixed into `UtilityFunctions`, which nearly every module in this library instantiates
unconditionally at module scope. Note that `util_ipython.py` itself still guards its `IPython`
import in a `try/except ImportError` and degrades to no-op stubs if it's ever missing anyway
(so `in_ipython()`/`display()`/etc. never hard-crash) — the core-dependency declaration exists
so a plain `pip install lib-utils` is guaranteed to have working IPython display/notebook
features out of the box, rather than relying on it being pulled in transitively by something
else (e.g. `jupyterlab`) in a consuming project's own requirements.

## Interactive demo

`demo.py` is a [Jupytext](https://jupytext.readthedocs.io) light-format Python file (cells delimited by `# %%`). Open it directly in VS Code with the Jupyter extension or run it as a plain script.

**What it does:**

- Auto-discovers every class with a `lib_demo_params`, `lib_demo`, or `demo` method across `utils._internal` and `utils.standalone`
- Skips modules whose optional dependencies are not installed (shows a skipped list with the reason)
- Presents a numbered menu — enter a number to launch that module's demo
- In Jupyter: renders an interactive widget UI (`build_lib_demo_widget`) for classes with `lib_demo_params`
- In a plain terminal: falls back to `utils.demo()` CLI mode

## Security audit (`pip-audit`)

Last run: 2026-07-18. Method: resolve `requirements.txt` in a clean venv
(`pip install --dry-run -r requirements.txt --report`), then `pip-audit --no-deps` the full
resolved set — 73 packages including transitive dependencies (Windows, Python 3.14).

**No known vulnerabilities found.** The `>=` floors also audit clean: `cryptography>=48.0.1`
resolves past PYSEC-2026-36 / CVE-2026-26007 (fixed by 48.0.1, previously flagged on 45.x),
and `requests>=2.32` resolves to 2.34.x, past CVE-2026-25645.

## Development

```bash
git clone <repo-url>
pip install -e ".[all,win]"   # editable install with all extras
or
pip install -e ".[all,win]" --config-settings editable_mode=compat   # needed for Jupyter
```
