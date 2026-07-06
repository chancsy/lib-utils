"""
CSV Graph Plotter - Core Data Engine

Provides:
- CSVDataManager: Load CSV/TXT files with auto-detect delimiter, incremental loading
- StatisticsEngine: Basic stats, Cpk/Cp/Ppk/Pp, rolling windowed stats, control limits
- ConfigManager: Save/load limit configurations as JSON
- FileMonitor: Detect file changes for auto-refresh

Usage Examples
--------------

1. Load a CSV and inspect columns::

    from csv_plotter import CSVDataManager
    mgr = CSVDataManager()
    df = mgr.load_file(r'C:\path\to\data.csv')
    print(mgr.get_all_columns(r'C:\path\to\data.csv'))
    print(mgr.get_numeric_columns(r'C:\path\to\data.csv'))
    print(mgr.detect_timestamp_column(r'C:\path\to\data.csv'))

2. Load a pipe-delimited reliability log (auto-detected)::

    df = mgr.load_file(r'C:\path\to\test_program_1_dut.txt')
    # Loads '|' delimited file transparently — same API as CSV

3. Load only the last 5000 rows of a large file for fast initial load::

    df = mgr.load_file(r'C:\path\to\big_log.csv', max_rows=5000)

4. Incremental load — append new rows appended to an active log::

    mgr.load_file(r'C:\path\to\live_log.csv')   # initial load
    # ... time passes, new rows written to file ...
    new_rows = mgr.load_incremental(r'C:\path\to\live_log.csv')
    print(f'{len(new_rows)} new rows loaded')

5. Compute basic statistics on a column::

    from csv_plotter import StatisticsEngine
    series = mgr.get_numeric_series(r'C:\path\to\data.csv', '#8 Internal Main Board Temperature')
    stats = StatisticsEngine.compute_basic_stats(series)
    # {'count': 1200, 'mean': 45.3, 'std': 2.1, 'min': 38.0, 'max': 52.1, ...}

6. Compute Cpk / Cp / Ppk / Pp::

    cpk = StatisticsEngine.compute_cpk(series, usl=60.0, lsl=20.0)
    cp  = StatisticsEngine.compute_cp(series,  usl=60.0, lsl=20.0)
    ppk = StatisticsEngine.compute_ppk(series, usl=60.0, lsl=20.0)
    # One-sided limits are also supported:
    cpk_usl_only = StatisticsEngine.compute_cpk(series, usl=60.0)

7. Rolling statistics by sample window (last 100 samples)::

    roll = StatisticsEngine.compute_rolling_stats(series, window_size=100)
    # Returns DataFrame with 'rolling_mean' and 'rolling_std' columns

    cpk_rolling = StatisticsEngine.compute_rolling_cpk(
        series, window_size=100, usl=60.0, lsl=20.0)

8. Rolling statistics by time window (last 7 days)::

    ts = mgr.get_numeric_series(r'C:\path\to\data.csv', 'Test Time')  # or any timestamp col
    roll = StatisticsEngine.compute_rolling_stats(
        series, window_size='7D', window_type='time', timestamps=ts)

    cpk_weekly = StatisticsEngine.compute_rolling_cpk(
        series, window_size='7D', usl=60.0, lsl=20.0,
        window_type='time', timestamps=ts)

9. Control limits (UCL/LCL for X-bar chart)::

    limits = StatisticsEngine.compute_control_limits(series)
    # {'center': 45.3, 'ucl': 51.6, 'lcl': 39.0}

10. Save limit configuration to JSON::

    from csv_plotter import ConfigManager
    config = {
        '#8 Internal Main Board Temperature': {
            'usl': 60.0, 'lsl': 20.0,
            'stat_limits': {'cpk_min': 1.33}
        },
        '#0 Input Current': {
            'usl': 21.5, 'lsl': 3.5,
            'stat_limits': {'cpk_min': 1.67}
        },
    }
    ConfigManager.save_config('my_limits.json', config)

11. Load limit configuration from JSON::

    loaded = ConfigManager.load_config('my_limits.json')
    # Filter to only columns present in current data:
    applicable = ConfigManager.apply_config(loaded, mgr.get_all_columns(filepath))

12. Monitor files for changes (for auto-refresh scripts)::

    from csv_plotter import FileMonitor
    mon = FileMonitor()
    mon.register(r'C:\path\to\live_log.csv')
    # ... in a polling loop ...
    if mon.check_modified(r'C:\path\to\live_log.csv'):
        new_rows = mgr.load_incremental(r'C:\path\to\live_log.csv')
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime


# ──────────────────────────────────────────────────────────────────────────────
# CSVDataManager
# ──────────────────────────────────────────────────────────────────────────────

class CSVDataManager:
    """Manages loading and incremental updates of CSV/delimited data files."""

    def __init__(self):
        # {filepath: DataFrame}
        self.dataframes = {}
        # {filepath: byte_offset} for incremental loading
        self._file_offsets = {}
        # {filepath: header_list} to reuse headers on incremental load
        self._file_headers = {}

    def load_file(self, filepath, max_rows=None):
        """Load a CSV/delimited file with auto-detected delimiter.

        Args:
            filepath: Path to CSV or delimited text file.
            max_rows: If set, load only the last N rows (for large files).

        Returns:
            pandas.DataFrame
        """
        filepath = os.path.normpath(filepath)
        df = pd.read_csv(
            filepath,
            sep=None,        # auto-detect delimiter
            engine='python',
            on_bad_lines='skip',
            nrows=None,
        )
        if max_rows and len(df) > max_rows:
            df = df.tail(max_rows).reset_index(drop=True)

        self.dataframes[filepath] = df
        # Record offset for future incremental loads
        self._file_offsets[filepath] = os.path.getsize(filepath)
        self._file_headers[filepath] = list(df.columns)
        return df

    def load_incremental(self, filepath):
        """Load only newly appended lines since last read.

        Returns:
            pandas.DataFrame of new rows (empty DataFrame if no new data).
        """
        filepath = os.path.normpath(filepath)
        if filepath not in self._file_offsets:
            return self.load_file(filepath)

        current_size = os.path.getsize(filepath)
        last_offset = self._file_offsets[filepath]

        if current_size <= last_offset:
            # File hasn't grown (or was truncated — reload fully)
            if current_size < last_offset:
                return self.load_file(filepath)
            return pd.DataFrame(columns=self._file_headers.get(filepath, []))

        # Read only the new bytes
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            f.seek(last_offset)
            new_text = f.read()

        if not new_text.strip():
            self._file_offsets[filepath] = current_size
            return pd.DataFrame(columns=self._file_headers[filepath])

        # Detect delimiter from existing headers
        from io import StringIO
        headers = self._file_headers[filepath]
        # Detect the delimiter by re-reading the first line of the original file
        delimiter = self._detect_delimiter(filepath)
        new_df = pd.read_csv(
            StringIO(new_text),
            sep=delimiter,
            header=None,
            names=headers,
            on_bad_lines='skip',
        )
        # Append to stored DataFrame
        self.dataframes[filepath] = pd.concat(
            [self.dataframes[filepath], new_df], ignore_index=True
        )
        self._file_offsets[filepath] = current_size
        return new_df

    def _detect_delimiter(self, filepath):
        """Detect delimiter from the first line of a file."""
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            first_line = f.readline()
            # Also read header line (second attempt if first line is a comment)
            second_line = f.readline()

        # Count occurrences of common delimiters in first line
        for delim in ['|', '\t', ',', ';']:
            if first_line.count(delim) >= 2:
                return delim
        return ','

    def get_numeric_columns(self, filepath):
        """Return list of columns that can be interpreted as numeric."""
        filepath = os.path.normpath(filepath)
        df = self.dataframes.get(filepath)
        if df is None:
            return []
        numeric_cols = []
        for col in df.columns:
            converted = pd.to_numeric(df[col], errors='coerce')
            if converted.notna().sum() > 0:
                numeric_cols.append(col)
        return numeric_cols

    def get_all_columns(self, filepath):
        """Return all column names for a loaded file."""
        filepath = os.path.normpath(filepath)
        df = self.dataframes.get(filepath)
        if df is None:
            return []
        return list(df.columns)

    def detect_timestamp_column(self, filepath):
        """Heuristic to find the timestamp/datetime column."""
        filepath = os.path.normpath(filepath)
        df = self.dataframes.get(filepath)
        if df is None:
            return None

        timestamp_keywords = ['time', 'date', 'timestamp', 'datetime']
        # First pass: check column names
        for col in df.columns:
            if any(kw in col.lower() for kw in timestamp_keywords):
                try:
                    pd.to_datetime(df[col].head(20), format='mixed')
                    return col
                except Exception:
                    continue

        # Second pass: try parsing each object/string column
        for col in df.select_dtypes(include=['object']).columns:
            try:
                parsed = pd.to_datetime(df[col].head(20), format='mixed')
                if parsed.notna().sum() >= 10:
                    return col
            except Exception:
                continue
        return None

    def get_numeric_series(self, filepath, column):
        """Get a column as numeric Series, coercing errors to NaN."""
        filepath = os.path.normpath(filepath)
        df = self.dataframes.get(filepath)
        if df is None or column not in df.columns:
            return pd.Series(dtype=float)
        return pd.to_numeric(df[column], errors='coerce')

    def remove_file(self, filepath):
        """Remove a file from the manager."""
        filepath = os.path.normpath(filepath)
        self.dataframes.pop(filepath, None)
        self._file_offsets.pop(filepath, None)
        self._file_headers.pop(filepath, None)


# ──────────────────────────────────────────────────────────────────────────────
# StatisticsEngine
# ──────────────────────────────────────────────────────────────────────────────

class StatisticsEngine:
    """Compute basic and SPC statistics on numeric series."""

    @staticmethod
    def compute_basic_stats(series):
        """Compute basic descriptive statistics.

        Returns:
            dict with keys: count, mean, std, min, max, median, range
        """
        s = series.dropna()
        if len(s) == 0:
            return {k: np.nan for k in ['count', 'mean', 'std', 'min', 'max', 'median', 'range']}
        return {
            'count': int(len(s)),
            'mean': float(s.mean()),
            'std': float(s.std(ddof=1)) if len(s) > 1 else 0.0,
            'min': float(s.min()),
            'max': float(s.max()),
            'median': float(s.median()),
            'range': float(s.max() - s.min()),
        }

    @staticmethod
    def compute_cp(series, usl, lsl):
        """Process Capability index: Cp = (USL - LSL) / (6σ)"""
        s = series.dropna()
        if len(s) < 2 or usl is None or lsl is None:
            return np.nan
        sigma = s.std(ddof=1)
        if sigma == 0:
            return np.nan
        return float((usl - lsl) / (6 * sigma))

    @staticmethod
    def compute_cpk(series, usl=None, lsl=None):
        """Process Capability index (centered): Cpk = min((USL-μ)/(3σ), (μ-LSL)/(3σ))

        Can compute with only USL or only LSL.
        """
        s = series.dropna()
        if len(s) < 2:
            return np.nan
        mean = s.mean()
        sigma = s.std(ddof=1)
        if sigma == 0:
            return np.nan

        indices = []
        if usl is not None:
            indices.append((usl - mean) / (3 * sigma))
        if lsl is not None:
            indices.append((mean - lsl) / (3 * sigma))
        if not indices:
            return np.nan
        return float(min(indices))

    @staticmethod
    def compute_ppk(series, usl=None, lsl=None):
        """Process Performance index: Ppk (uses overall std with ddof=0)."""
        s = series.dropna()
        if len(s) < 2:
            return np.nan
        mean = s.mean()
        sigma = s.std(ddof=0)
        if sigma == 0:
            return np.nan

        indices = []
        if usl is not None:
            indices.append((usl - mean) / (3 * sigma))
        if lsl is not None:
            indices.append((mean - lsl) / (3 * sigma))
        if not indices:
            return np.nan
        return float(min(indices))

    @staticmethod
    def compute_pp(series, usl, lsl):
        """Process Performance index: Pp = (USL - LSL) / (6σ) with ddof=0."""
        s = series.dropna()
        if len(s) < 2 or usl is None or lsl is None:
            return np.nan
        sigma = s.std(ddof=0)
        if sigma == 0:
            return np.nan
        return float((usl - lsl) / (6 * sigma))

    @staticmethod
    def compute_control_limits(series):
        """Compute X-bar chart control limits: center, UCL, LCL (±3σ).

        Returns:
            dict with keys: center, ucl, lcl
        """
        s = series.dropna()
        if len(s) < 2:
            return {'center': np.nan, 'ucl': np.nan, 'lcl': np.nan}
        mean = float(s.mean())
        sigma = float(s.std(ddof=1))
        return {
            'center': mean,
            'ucl': mean + 3 * sigma,
            'lcl': mean - 3 * sigma,
        }

    @classmethod
    def compute_rolling_stats(cls, series, window_size, window_type='samples',
                              timestamps=None):
        """Compute rolling statistics over a window.

        Args:
            series: numeric pandas Series
            window_size: int (samples) or str (time offset like '7D', '1H')
            window_type: 'samples' or 'time'
            timestamps: Series of datetime values (required for 'time' window)

        Returns:
            DataFrame with columns: rolling_mean, rolling_std
        """
        s = series.copy()
        s.index = range(len(s))

        if window_type == 'time' and timestamps is not None:
            ts = pd.to_datetime(timestamps, format='mixed', errors='coerce')
            s.index = ts
            s = s.sort_index()
            rolling = s.rolling(window=window_size, min_periods=2)
        else:
            rolling = s.rolling(window=int(window_size), min_periods=2)

        result = pd.DataFrame({
            'rolling_mean': rolling.mean(),
            'rolling_std': rolling.std(ddof=1),
        })
        result.index = range(len(result))
        return result

    @classmethod
    def compute_rolling_cpk(cls, series, window_size, usl=None, lsl=None,
                            window_type='samples', timestamps=None):
        """Compute rolling Cpk over a window.

        Returns:
            pandas Series of rolling Cpk values.
        """
        s = series.copy()

        if window_type == 'time' and timestamps is not None:
            ts = pd.to_datetime(timestamps, format='mixed', errors='coerce')
            s.index = ts
            s = s.sort_index()
            rolling_mean = s.rolling(window=window_size, min_periods=2).mean()
            rolling_std = s.rolling(window=window_size, min_periods=2).std(ddof=1)
        else:
            w = int(window_size)
            rolling_mean = s.rolling(window=w, min_periods=2).mean()
            rolling_std = s.rolling(window=w, min_periods=2).std(ddof=1)

        cpk_values = pd.Series(np.nan, index=rolling_mean.index)
        for i in range(len(rolling_mean)):
            m = rolling_mean.iloc[i]
            sig = rolling_std.iloc[i]
            if pd.isna(m) or pd.isna(sig) or sig == 0:
                continue
            vals = []
            if usl is not None:
                vals.append((usl - m) / (3 * sig))
            if lsl is not None:
                vals.append((m - lsl) / (3 * sig))
            if vals:
                cpk_values.iloc[i] = min(vals)

        cpk_values.index = range(len(cpk_values))
        return cpk_values


# ──────────────────────────────────────────────────────────────────────────────
# ConfigManager
# ──────────────────────────────────────────────────────────────────────────────

class ConfigManager:
    """Save and load limit configurations as JSON files.

    JSON schema:
    {
        "column_name": {
            "usl": float or null,
            "lsl": float or null,
            "stat_limits": {
                "cpk_min": float or null,
                "ppk_min": float or null,
                "mean_min": float or null,
                "mean_max": float or null,
                "std_max": float or null
            }
        },
        ...
    }
    """

    @staticmethod
    def save_config(filepath, config_dict):
        """Save configuration to a JSON file.

        Args:
            filepath: Path for the JSON file.
            config_dict: dict mapping column names to limit definitions.
        """
        # Convert numpy types to Python native types for JSON serialization
        def _convert(obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            return obj

        clean = _convert(config_dict)
        with open(filepath, 'w') as f:
            json.dump(clean, f, indent=2)

    @staticmethod
    def load_config(filepath):
        """Load configuration from a JSON file.

        Returns:
            dict mapping column names to limit definitions.
        """
        with open(filepath, 'r') as f:
            return json.load(f)

    @staticmethod
    def apply_config(config_dict, available_columns):
        """Filter config to only columns present in the data.

        Returns:
            dict with only keys that match available_columns.
        """
        return {k: v for k, v in config_dict.items() if k in available_columns}


# ──────────────────────────────────────────────────────────────────────────────
# FileMonitor
# ──────────────────────────────────────────────────────────────────────────────

class FileMonitor:
    """Monitor files for changes using mtime and file size."""

    def __init__(self):
        # {filepath: (mtime, size)}
        self._file_state = {}

    def register(self, filepath):
        """Register a file and record its current state."""
        filepath = os.path.normpath(filepath)
        try:
            stat = os.stat(filepath)
            self._file_state[filepath] = (stat.st_mtime, stat.st_size)
        except OSError:
            pass

    def check_modified(self, filepath):
        """Check if a file has been modified since last check.

        Returns:
            True if modified, False otherwise.
        """
        filepath = os.path.normpath(filepath)
        try:
            stat = os.stat(filepath)
            current = (stat.st_mtime, stat.st_size)
        except OSError:
            return False

        last = self._file_state.get(filepath)
        if last is None:
            self._file_state[filepath] = current
            return True

        if current != last:
            self._file_state[filepath] = current
            return True
        return False

    def get_changed_files(self):
        """Check all registered files and return list of changed ones."""
        changed = []
        for filepath in list(self._file_state.keys()):
            if self.check_modified(filepath):
                changed.append(filepath)
        return changed

    def unregister(self, filepath):
        """Remove a file from monitoring."""
        filepath = os.path.normpath(filepath)
        self._file_state.pop(filepath, None)
