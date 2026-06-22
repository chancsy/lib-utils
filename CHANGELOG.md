# Changelog

All notable changes to this project will be documented here.

## [Unreleased]

### Fixed
- `find_smallest_gte()` — removed stray debug `print(v, value)` in the linear scan path
- `dec_to_hex_str()` — `NameError` when `byte_size=0` (hex_str was conditionally assigned then always read)
- `send_webhook()` — status code check had `201` duplicated; corrected to `200 or 201 or 202`
- `get_rows()` / `insert()` / `create_table()` etc. — SQL identifier injection: table and column names now validated and double-quoted via `_sql_id()`
- `win_automation_utils` — `ImportError` on non-Windows platforms
- `EquationSolver` — `eval()` exposed Python builtins; restricted to `{'__builtins__': {}}` so only sympy symbols are in scope (windll imported unconditionally); now raises a clear `ImportError` on non-Windows at import time

### Added
- `pyproject.toml` — modern packaging metadata with `extras_require` groups (`requests`, `git`, `crypto`, `pdf`, `slack`, `selenium`, `math`, `win`, `all`)
- `setup.py` — reduced to a minimal shim; all metadata lives in `pyproject.toml`
- `README.md` — package layout, install instructions, usage examples

## [0.1.0] — initial tracked state

### Added
- `UtilityFunctions` composed from `_internal` mixins: binary, collections, dataframe, demo, filesystem, IPython, lan_monitor, output, runtime, testing, text, threads, time, web
- `TestClass` — test session helper with uptime check and git info print
- Standalone modules: `cryptography_utils`, `electronics_utils`, `log_actions`, `math_utils`, `pdf_utils`, `selenium_utils`, `slack_utils`, `solidworks_pdm_utils`, `sqlite_utils`, `sql_utils`, `ui_utils`, `widget_utils`, `win_automation_utils`
- Runtime optional-dependency check via `module_exists()` / `exit_if_module_missing()`
