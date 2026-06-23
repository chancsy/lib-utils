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
│   ├── util_ipython.py     # IPython display helpers           [optional: IPython]
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
│   └── win_automation_utils.py [requires: pywin32, pygetwindow, pyautogui, pynput, pycaw] (Windows only)
└── tools/                  # interactive tools — run directly or import to orchestrate
    └── region_setup.py         [requires: opencv-python, numpy, tkinter] — ADB screen region selector
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
from utils.standalone.widget_utils import Widgets, MultiSelectMoveButtons, TabbedTextareaPanel, WidgetStdout, build_lib_demo_widget  # Jupyter only
from utils.standalone.win_automation_utils import WindowManager, InputSimulator, WindowPos, WindowSize, MousePos, WindowInfo  # Windows only

# Tools — import to orchestrate, or run directly
from utils.tools.region_setup import RegionSetupTool
```

## Optional dependency check

Standalone modules call `utils.exit_if_module_missing()` at import time and print an install hint if a required package is absent:

```
slack_sdk is not installed. To install, please run:
  pip install slack_sdk
```

## Requirements

- Python >= 3.10
- Core: `numpy>=2.3`, `pandas>=2.3`
- Optional: see [pyproject.toml](pyproject.toml) `[project.optional-dependencies]`

## Interactive demo

`demo.py` is a [Jupytext](https://jupytext.readthedocs.io) light-format Python file (cells delimited by `# %%`). Open it directly in VS Code with the Jupyter extension or run it as a plain script.

**What it does:**

- Auto-discovers every class with a `lib_demo_params`, `lib_demo`, or `demo` method across `utils._internal` and `utils.standalone`
- Skips modules whose optional dependencies are not installed (shows a skipped list with the reason)
- Presents a numbered menu — enter a number to launch that module's demo
- In Jupyter: renders an interactive widget UI (`build_lib_demo_widget`) for classes with `lib_demo_params`
- In a plain terminal: falls back to `utils.demo()` CLI mode

## Security audit (`pip-audit`)

Last run: 2026-06-22 against `requirements.txt`.

| Package | Installed | CVE / ID | Status |
|---|---|---|---|
| `cryptography` | 49.0.0 | PYSEC-2026-36, GHSA-537c-gmf6-5ccf, CVE-2026-26007, PYSEC-2026-35 | Fixed — upgraded to 49.0.0 |
| `requests` | 2.32.5 | CVE-2026-25645 | Low severity; not affected by the vulnerable code path |

## Development

```bash
git clone <repo-url>
pip install -e ".[all,win]"   # editable install with all extras
or
pip install -e ".[all,win]" --config-settings editable_mode=compat   # needed for Jupyter
```
