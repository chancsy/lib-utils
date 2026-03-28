"""Generic session-wide print() logging to disk.

Captures all ``print()`` output to a timestamped log file by redirecting ``sys.stdout``.
Optionally suppresses console output (``hide_stdout``).

This module is generic and has no knowledge of the equipment logging system.
For equipment-specific file logging (``print_comm``/``print_verbose``), see
``start_file_log()`` and ``start_test_logging()`` in ``ftestlib.equipments``.

Typical usage::

    from utils.log_actions import print_logging_start, print_logging_end

    log_file = print_logging_start('path/to/logs/', hide_stdout=True)
    print('captured to disk')
    print_logging_end()

Standalone file utilities:

- ``new_log()``   — Generate a timestamped log file path.
- ``add_lines()`` — Append a line of text to a file.
"""

import os
import sys
from utils.utilities import UtilityFunctions

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


def add_lines(filepath, text):
    """Append a line of text to a file.

    Args:
        filepath: Path to the target file.
        text: Text to append (a trailing newline is added automatically).
    """
    with open(filepath, 'a') as file:
        file.write(text + '\n')


# ---------------------------------------------------------------------------
# Stdout interceptor (synchronous, no background thread)
# ---------------------------------------------------------------------------

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

        # Write non-empty, non-bare-newline data to the log file
        if data and data != '\n':
            if self._add_datetimestamp:
                line = f'{utils.get_datetimestamp(style=1)}|{data}\n'
            else:
                line = f'{data}\n'
            self._file_handle.write(line)
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

    Attributes:
        log_file (str): Path to the active log file, or empty string if inactive.
        is_active (bool): Whether a logging session is currently running.
    """

    def __init__(self):
        self.log_file = ''
        self.is_active = False
        self._orig_stdout = None
        self._file_handle = None

    def start(self, logfile_directory_path, add_datetimestamp=True, hide_stdout=False):
        """Begin a logging session.

        Args:
            logfile_directory_path: Directory where the log file will be created.
            add_datetimestamp: If True, prefix each ``print()`` line with a datetime stamp.
            hide_stdout: If True, suppress all console output while still writing to disk.

        Returns:
            str: Path to the log file being written to.
        """
        if self.is_active:
            self.stop()

        self.log_file = new_log(logfile_directory_path, prefix='PrintLog', seconds=False)
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


def print_logging_start(logfile_directory_path, add_datetimestamp=True, hide_stdout=False):
    """Begin a logging session that captures ``print()`` output to disk.

    Wrapper around :meth:`PrintLogger.start`.  Multiple calls without a
    ``print_logging_end()`` in between will automatically end the previous session
    first (useful for switching log directories mid-test).

    Args:
        logfile_directory_path: Directory where the timestamped log file will be created.
        add_datetimestamp: Prefix each log line with a datetime stamp (default True).
        hide_stdout: If True, suppress console output while still writing to file.

    Returns:
        str: Path to the log file being written to.
    """
    return _print_logger.start(logfile_directory_path, add_datetimestamp, hide_stdout)


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
