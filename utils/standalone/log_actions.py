"""Generic session-wide print() logging to disk.

Captures all ``print()`` output to a timestamped log file by redirecting ``sys.stdout``.
Optionally suppresses console output (``hide_stdout``).

Typical usage::

    from utils.standalone.log_actions import print_logging_start, print_logging_end

    log_file = print_logging_start('path/to/logs/', hide_stdout=True)
    print('captured to disk')
    print_logging_end()

Standalone file utilities:

- ``new_log()``   — Generate a timestamped log file path.
- ``latest_log()`` — The newest date-named log in a folder.
- ``add_lines()`` — Append a line of text to a file.
"""

import os
import re
import sys
from ..utilities import UtilityFunctions

utils = UtilityFunctions()


# ---------------------------------------------------------------------------
# Standalone file utility functions
# ---------------------------------------------------------------------------

def new_log(outputdir_path='.', prefix='', seconds=True):
    """Generate a timestamped log file path, creating the directory if needed.

    Args:
        outputdir_path: Directory where the log file will be created.
        prefix: Optional prefix prepended to the filename (e.g. ``'PrintLog'``).
        seconds: If True, include time-with-seconds in the timestamp;
                 if False, use date-only stamp.

    Returns:
        Full path to the new log file (file is not created yet).
    """
    if not os.path.exists(outputdir_path):
        os.makedirs(outputdir_path)
    time_stamp = utils.get_datetimestamp(style=2) if seconds else utils.get_datestamp(style=0)
    filename_prefix = f'{prefix}_' if prefix else ''
    return os.path.join(outputdir_path, f'{filename_prefix}{time_stamp}.log')


def latest_log(outputdir_path, prefix=''):
    """The newest date-named log in a folder, as ``new_log(seconds=False)`` names them.

    Only ``<prefix>_YYYY-MM-DD.log`` counts, so e.g. ``PrintLog_2026-10-27_Combined.log``
    is never picked.

    Args:
        outputdir_path: Folder to look in.
        prefix: Filename prefix (e.g. ``'PrintLog'``).

    Returns:
        Full path of the newest such file, or None if there is none (or no folder).
    """
    if not os.path.isdir(outputdir_path):
        return None
    name_re = re.compile(rf'{re.escape(prefix + "_" if prefix else "")}\d{{4}}-\d{{2}}-\d{{2}}\.log', re.IGNORECASE)
    names = sorted(n for n in os.listdir(outputdir_path) if name_re.fullmatch(n))
    return os.path.join(outputdir_path, names[-1]) if names else None


def add_lines(filepath, text):
    """Append a line of text to a file.

    Args:
        filepath: Path to the target file.
        text: Text to append (a trailing newline is added automatically).
    """
    with open(filepath, 'a', encoding='utf-8') as file:
        file.write(text + '\n')


# ---------------------------------------------------------------------------
# Stdout interceptor (synchronous, no background thread)
# ---------------------------------------------------------------------------

_ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*m')


class _StdoutInterceptor:
    """Wraps the original ``sys.stdout`` to intercept ``print()`` calls.

    Each non-empty write is synchronously appended to the log file (with optional
    datetime prefix) and conditionally forwarded to the real console stream.

    Args:
        stream: The original ``sys.stdout`` to optionally forward writes to.
        file_handle: Open file handle for synchronous log writes.
        add_datetimestamp: Prefix each log line with a datetime stamp.
        hide_stdout: If True, do not forward writes to the console stream.
    """

    def __init__(self, stream, file_handle, add_datetimestamp=True, hide_stdout=False):
        self.stream = stream
        self._file_handle = file_handle
        self._add_datetimestamp = add_datetimestamp
        self._hide_stdout = hide_stdout

    def write(self, data):
        """Write data to the log file and optionally to the console."""
        # Forward to console unless hidden
        if not self._hide_stdout:
            self.stream.write(data)
            self.stream.flush()

        # Write to log file line by line (ANSI codes stripped, blank lines skipped)
        clean = _ANSI_ESCAPE_RE.sub('', data)
        for line in clean.splitlines():
            if not line:
                continue
            if self._add_datetimestamp:
                self._file_handle.write(f'{utils.get_datetimestamp(style=1)}|{line}\n')
            else:
                self._file_handle.write(f'{line}\n')
        self._file_handle.flush()

    def flush(self):
        """Flush both the console stream and log file."""
        self.stream.flush()
        if self._file_handle and not self._file_handle.closed:
            self._file_handle.flush()


# ---------------------------------------------------------------------------
# PrintLogger — class-based session logging manager
# ---------------------------------------------------------------------------

class PrintLogger:
    """Manages a logging session that captures ``print()`` output to a timestamped
    log file on disk via stdout redirection.

    Features:

    - **Synchronous file writes** — no background thread, no polling delay.
    - **``hide_stdout``** support via a stdout wrapper that conditionally suppresses
      console output while still writing to the log file.
    - Calling ``start()`` while a session is active automatically ends the previous
      session first (useful for switching log directories mid-test).
    - ``resume=True`` continues an earlier file instead of starting today's, so a test
      that switches folders, or restarts, keeps one file per folder across days.

    Attributes:
        log_file (str): Path to the active log file, or empty string if inactive.
        is_active (bool): Whether a logging session is currently running.
    """

    def __init__(self):
        self.log_file = ''
        self.is_active = False
        self._orig_stdout = None
        self._file_handle = None
        self._dir_files = {}  # folder (normalised) -> the file this logger last wrote there

    def start(self, logfile_directory_path, add_datetimestamp=True, hide_stdout=False, resume=False):
        """Begin a logging session.

        Args:
            logfile_directory_path: Directory where the log file will be created.
            add_datetimestamp: If True, prefix each ``print()`` line with a datetime stamp.
            hide_stdout: If True, suppress all console output while still writing to disk.
            resume: False (default): log to ``PrintLog_<today>.log`` (appended to if it exists).
                True: continue the file this process last logged to in that folder; if none,
                the newest ``PrintLog_YYYY-MM-DD.log`` there; if none, today's new file.

        Returns:
            str: Path to the log file being written to.
        """
        if self.is_active:
            self.stop()

        folder = os.path.normcase(os.path.abspath(logfile_directory_path))
        log_file = None
        if resume:
            log_file = self._dir_files.get(folder) or latest_log(logfile_directory_path, prefix='PrintLog')
        if log_file is None:
            log_file = new_log(logfile_directory_path, prefix='PrintLog', seconds=False)
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        self.log_file = log_file
        self._dir_files[folder] = log_file
        self._file_handle = open(self.log_file, 'a', encoding='utf-8')

        self._orig_stdout = sys.stdout
        sys.stdout = _StdoutInterceptor(
            stream=self._orig_stdout,
            file_handle=self._file_handle,
            add_datetimestamp=add_datetimestamp,
            hide_stdout=hide_stdout,
        )

        self.is_active = True
        return self.log_file

    def stop(self):
        """End the current logging session and restore normal stdout.

        Safe to call even if no session is active (no-op).
        """
        if not self.is_active:
            return

        if self._orig_stdout is not None:
            sys.stdout = self._orig_stdout
            self._orig_stdout = None

        if self._file_handle is not None:
            self._file_handle.flush()
            self._file_handle.close()
            self._file_handle = None

        self.is_active = False


# ---------------------------------------------------------------------------
# Module-level singleton and backward-compatible API
# ---------------------------------------------------------------------------

_print_logger = PrintLogger()
"""Module-level ``PrintLogger`` instance used by the convenience functions below."""


def print_logging_start(logfile_directory_path, add_datetimestamp=True, hide_stdout=False, resume=False):
    """Begin a logging session that captures ``print()`` output to disk.

    Wrapper around :meth:`PrintLogger.start`.  Multiple calls without a
    ``print_logging_end()`` in between will automatically end the previous session
    first (useful for switching log directories mid-test).

    Args:
        logfile_directory_path: Directory where the timestamped log file will be created.
        add_datetimestamp: Prefix each log line with a datetime stamp (default True).
        hide_stdout: If True, suppress console output while still writing to file.
        resume: True to continue the earlier file in that folder instead of today's
            (see :meth:`PrintLogger.start`).

    Returns:
        str: Path to the log file being written to.
    """
    return _print_logger.start(logfile_directory_path, add_datetimestamp, hide_stdout, resume)


def print_logging_end():
    """End the current logging session and restore normal stdout.

    Safe to call even if no session is active (no-op in that case).
    """
    _print_logger.stop()


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def log_demo():
    """Demonstrate print logging: start a session, print some lines, then verify the log file."""
    print(f'{__name__} demo:')
    log = print_logging_start(logfile_directory_path='.', hide_stdout=True)
    print('test1')
    print('test2')
    print('test3')
    print_logging_end()
    print(log)
    print(utils.read_file(log))
    utils.remove_file(log)
