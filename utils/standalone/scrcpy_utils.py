"""scrcpy (Android screen mirroring) helpers: find scrcpy and the adb to pair with it, launch or
attach to its window, and grab frames from that window - a fast alternative to `adb screencap`.

    from utils.standalone.scrcpy_utils import find_scrcpy, resolve_adb, launch_scrcpy
    from utils.standalone.adb_utils import AdbUtils
    adb = AdbUtils(adb_path=resolve_adb())            # --adb-path > adb bundled with scrcpy > 'adb' on PATH
    adb.set_device(adb.get_devices()[0])
    cap = launch_scrcpy('my_tool', serial=adb.device, adb_path=adb.adb_path)
    img = cap.take_screenshot()                       # BGR numpy array, window client-area size
    cap.stop()                                        # only closes scrcpy if launch_scrcpy started it

Frames come at the mirror window's size, not the device resolution: keep regions as fractions of
the screen and scale them by `AdbUtils.get_screen_size()` before tapping.
Capture is Windows-only (WindowManager: pygetwindow + win32gui); needs mss, opencv-python, numpy.
"""
import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()

import os
import shutil
import subprocess
import time

SCRCPY_EXE = 'scrcpy.exe' if sys.platform == 'win32' else 'scrcpy'
ADB_EXE = 'adb.exe' if sys.platform == 'win32' else 'adb'


def find_scrcpy(exe: str | None = None) -> str | None:
    """Full path of scrcpy: `exe` if it exists (a file, or a folder holding scrcpy), else `scrcpy` on PATH.

    A given `exe` that doesn't exist (e.g. a stale configured path) prints a warning and falls back to PATH.
    Returns None if scrcpy isn't found.
    """
    if exe:
        path = _os.path.join(exe, SCRCPY_EXE) if _os.path.isdir(exe) else exe
        found = shutil.which(path)
        if found:
            return _os.path.abspath(found)
        print(f'scrcpy not found at "{exe}" - looking on PATH instead.')
    found = shutil.which('scrcpy')
    return _os.path.abspath(found) if found else None


def scrcpy_adb(scrcpy_exe: str | None = None) -> str | None:
    """The adb bundled next to scrcpy (the Windows release ships one), or None.

    `scrcpy_exe`: path of scrcpy; found with find_scrcpy() when not given.
    """
    exe = scrcpy_exe or find_scrcpy()
    if not exe:
        return None
    adb = _os.path.join(_os.path.dirname(exe), ADB_EXE)
    return adb if _os.path.isfile(adb) else None


def resolve_adb(adb_path: str | None = None, scrcpy_exe: str | None = None) -> str:
    """The adb to use: `adb_path` if given (always wins) > the adb bundled with scrcpy > 'adb' on PATH.

    Using scrcpy's own adb keeps the tool and scrcpy on one adb client version, so neither restarts
    the other's adb server. `scrcpy_exe` is passed to find_scrcpy() (None = look on PATH).
    """
    if adb_path:
        return adb_path
    return scrcpy_adb(find_scrcpy(scrcpy_exe)) or 'adb'


def _window_open(wm, title: str) -> bool:
    # Exact-title check without WindowManager.get_window_pos's "No window found" print on every poll
    return any(w.title == title for w in wm._gw.getWindowsWithTitle(title))


class ScrcpyCapture:
    """Grabs frames from a scrcpy mirror window via mss; drop-in for AdbUtils.take_screenshot().

    take_screenshot() returns a BGR numpy array of the window's client area (title bar and borders
    excluded) at the window's own size - no resize. `process` is the scrcpy Popen when we launched it.
    """

    def __init__(self, window_title: str = 'scrcpy', process: subprocess.Popen | None = None):
        self.window_title = window_title
        self._process = process
        self._wm = None

    @property
    def launched_by_us(self) -> bool:
        """True if launch_scrcpy started this scrcpy (stop() will close it)."""
        return self._process is not None

    def _get_wm(self):
        if self._wm is None:
            from .win_automation_utils import WindowManager
            self._wm = WindowManager()
        return self._wm

    def is_running(self) -> bool:
        """True if the scrcpy window is open."""
        return _window_open(self._get_wm(), self.window_title)

    def stop(self) -> None:
        """Close scrcpy if we launched it; no-op for a window that was already open."""
        if self._process is not None:
            self._process.terminate()
            self._process = None

    def take_screenshot(self):
        """BGR numpy array of the window's client area, or None if the window isn't found."""
        img = self._get_wm().capture_window(self.window_title)
        if img is None:
            print(f'ScrcpyCapture: window "{self.window_title}" not found.')
        return img


def launch_scrcpy(window_title: str = 'scrcpy', exe: str | None = None, serial: str | None = None,
                  adb_path: str | None = None, video_bitrate: str = '16M', extra_args: list[str] | None = None,
                  launch_timeout: float = 10.0, settle: float = 2.0) -> ScrcpyCapture:
    """Attach to the scrcpy window titled `window_title`, or launch scrcpy with that title; returns a ScrcpyCapture.

    exe:            scrcpy path (file or folder); None = find on PATH (see find_scrcpy)
    serial:         device serial passed as `-s` (needed when several devices are connected)
    adb_path:       adb for scrcpy to use (set as the ADB environment variable) - pass the tool's own
                    adb so both share one adb client; None = scrcpy's default (its bundled adb)
    video_bitrate:  `--video-bit-rate`
    extra_args:     further scrcpy arguments
    launch_timeout: seconds to wait for the window; settle: extra wait after it appears, as the
                    window opens before the first video frame is decoded
    Raises FileNotFoundError if scrcpy isn't found, RuntimeError if it exits during launch
    (device unauthorized / not found).
    """
    utils.exit_if_module_missing('mss')
    from .win_automation_utils import WindowManager
    wm = WindowManager()
    if _window_open(wm, window_title):
        print(f'scrcpy window "{window_title}" already open.')
        return ScrcpyCapture(window_title)

    scrcpy = find_scrcpy(exe)
    if scrcpy is None:
        raise FileNotFoundError('scrcpy not found: put its folder on PATH or pass exe= (a file or folder).')
    cmd = [scrcpy,
           '--window-title', window_title,   # predictable title for window lookup
           '--always-on-top',                # keep the window above other apps so mss captures it
           '--no-audio',
           '--video-bit-rate', video_bitrate]
    if serial:
        cmd += ['-s', serial]
    cmd += list(extra_args or [])
    env = None
    if adb_path:
        env = dict(os.environ, ADB=shutil.which(adb_path) or adb_path)
    print(f'Launching scrcpy: {scrcpy} (bitrate={video_bitrate}'
          + (f', adb={env["ADB"]}' if env else '') + ')...')
    proc = subprocess.Popen(cmd, env=env)

    t0 = time.perf_counter()
    while time.perf_counter() - t0 < launch_timeout:
        time.sleep(0.5)
        if proc.poll() is not None:
            raise RuntimeError(f'scrcpy exited during launch (code {proc.returncode}) - '
                               'is the device connected and USB debugging authorized?')
        if _window_open(wm, window_title):
            print(f'  scrcpy window appeared ({time.perf_counter() - t0:.1f}s) - waiting for video...')
            time.sleep(settle)
            print('  scrcpy ready.')
            break
    else:
        print(f'  Warning: scrcpy window did not appear within {launch_timeout}s - capture may fail.')
    return ScrcpyCapture(window_title, process=proc)


if __name__ == '__main__':
    # Smoke test: launch/attach, grab one frame, save it, close scrcpy if we started it
    import cv2
    print('scrcpy:', find_scrcpy(), '| adb:', resolve_adb())
    cap = launch_scrcpy('scrcpy_utils_test', adb_path=resolve_adb())
    img = cap.take_screenshot()
    if img is not None:
        cv2.imwrite('scrcpy_utils_test.png', img)
        print(f'Frame {img.shape[1]}x{img.shape[0]} -> scrcpy_utils_test.png')
    cap.stop()
