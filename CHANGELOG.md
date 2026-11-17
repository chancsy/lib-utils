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
- `MathUtils.print_data_stats(calc_stdev=True)` — `AttributeError`: it builds a `self.Dataset()`, but the `Dataset` class had been dropped; restored (see Added)

### Added
- `read_json_file()` — counterpart to the existing `write_json_file()`; returns a caller-supplied `default` when the file doesn't exist instead of raising
- `pyproject.toml` — modern packaging metadata with `extras_require` groups (`requests`, `git`, `crypto`, `pdf`, `slack`, `selenium`, `math`, `win`, `all`)
- `README.md` — package layout, install instructions, usage examples
- `MathUtils.dew_point()` — dew point from temperature and relative humidity (Magnus-Tetens or Sensirion constants)
- `MathUtils.Dataset` — store values and get count / min / max / sum / mean / median / std dev / variance / percentile / quantile (`None` while empty)
- `Electronics.r_star_delta()` — star (Y) ↔ delta (Δ) resistor network conversion; `show_info=True` shows the naming diagram in Jupyter
- `Electronics.voltage_divider(show_info=True)` — shows the circuit diagram in Jupyter
- `BitPatternCheckBox` (`widget_utils`) — 8 labelled checkboxes showing the bits of a byte (MSB first, set bits in bold); read-only by default, or editable with a `cb(change, bit)` callback

### Changed
- `requirements.txt` — rewritten as a flat `>=` mirror of the `pyproject.toml` dependencies (same floors), replacing the stale pip-freeze pins (`cryptography==45.0.7` contradicted pyproject's `>=48.0.1`); added previously missing sections (`ipython` core, `[sql]`, `[cv]`, `[clipboard]`, `[pillow]`, `[widgets]`); dropped transitive `pywin32-ctypes`. `pip-audit` re-run 2026-07-18 on the full resolved set (73 packages incl. transitives): no known vulnerabilities

### Removed
- `setup.py` — the shim (all metadata already lived in `pyproject.toml`) is no longer needed; PEP 660 editable installs work from `pyproject.toml` alone with `setuptools>=68`

## [0.1.0] — initial tracked state

### Added
- `UtilityFunctions` composed from `_internal` mixins: binary, collections, dataframe, demo, filesystem, IPython, lan_monitor, output, runtime, testing, text, threads, time, web
- `TestClass` — test session helper with uptime check and git info print
- Standalone modules: `cryptography_utils`, `electronics_utils`, `log_actions`, `math_utils`, `pdf_utils`, `selenium_utils`, `slack_utils`, `solidworks_pdm_utils`, `sqlite_utils`, `sql_utils`, `ui_utils`, `widget_utils`, `win_automation_utils`
- Runtime optional-dependency check via `module_exists()` / `exit_if_module_missing()`
