import sys
from dataclasses import dataclass
import os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions

utils = UtilityFunctions()


def _check_windows_platform():
    # Checked from each class's __init__ (at construction) rather than at module-import
    # time, so merely importing this module - e.g. just to get the plain WindowSize/
    # WindowPos/MousePos/WindowInfo dataclasses below - doesn't require Windows at all.
    if sys.platform != 'win32':
        raise ImportError('win_automation_utils requires Windows')


# --- Data containers ---

@dataclass
class WindowSize:
    width: int
    height: int

# Unified window position (left, top, width, height).
@dataclass
class WindowPos:
    left: int
    top: int
    width: int
    height: int

@dataclass
class MousePos:
    x: int
    y: int

@dataclass
class WindowInfo:
    handle: int
    title: str


class WindowManager:
    """Windows GUI automation: screen, window, and audio control."""

    def __init__(self):
        # Checked here (at construction) rather than at module-import time, so merely
        # importing this module doesn't require Windows or any of these packages - only
        # actually instantiating WindowManager does. Cached on self so the methods below
        # don't need their own import statements.
        _check_windows_platform()
        utils.exit_if_module_missing('pywin32')
        utils.exit_if_module_missing('pygetwindow')
        utils.exit_if_module_missing('pyautogui')
        utils.exit_if_module_missing('pycaw')
        import win32gui
        import pygetwindow as gw
        import pyautogui
        from ctypes import windll
        from pycaw.pycaw import AudioUtilities
        self._win32gui = win32gui
        self._gw = gw
        self._pyautogui = pyautogui
        self._windll = windll
        self._AudioUtilities = AudioUtilities

    # Return the screen resolution.
    def get_screen_size(self) -> WindowSize:
        size = self._pyautogui.size()
        return WindowSize(size.width, size.height)

    # Return the handle of the currently focused window.
    def get_foreground_window_handle(self) -> int:
        return self._win32gui.GetForegroundWindow()

    # Return the title of the currently focused window.
    def get_foreground_window_title(self) -> str:
        return self._win32gui.GetWindowText(self._win32gui.GetForegroundWindow())

    # Bring the window with the given handle to the foreground.
    def focus_window(self, handle: int) -> None:
        try:
            self._win32gui.SetForegroundWindow(handle)
        except Exception:
            print(f'Window {handle} not found')

    # Return all visible windows as a list of WindowInfo.
    def get_all_windows(self) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        def _cb(hwnd, _):
            if self._win32gui.IsWindowVisible(hwnd):
                title = self._win32gui.GetWindowText(hwnd)
                if title:
                    windows.append(WindowInfo(hwnd, title))
        self._win32gui.EnumWindows(_cb, None)
        return windows

    # Return sorted list of all visible window titles.
    def get_all_window_titles(self) -> list[str]:
        return sorted(w.title for w in self.get_all_windows())

    # Return position of the window matching name (and optionally handle).
    def _get_windows_exact(self, title: str):
        # pygetwindow.getWindowsWithTitle does substring matching; filter to exact title.
        return [w for w in self._gw.getWindowsWithTitle(title) if w.title == title]

    def get_window_pos(self, name: str, handle: int = 0) -> WindowPos | None:
        matches = self._get_windows_exact(name)
        if not matches:
            print(f"No window found with title '{name}'")
            return None

        window = None
        if len(matches) == 1:
            w = matches[0]
            if handle and w._hWnd != handle:
                print(f"Unable to match specified window handle '{handle}', please check.")
                return None
            window = w
        else:
            if not handle:
                print('Multiple windows found, defaulting to first.')
                window = matches[0]
            else:
                for w in matches:
                    if w._hWnd == handle:
                        window = w
                        break
                if window is None:
                    print(f"Unable to match specified window handle '{handle}', please check.")
                    return None

        return WindowPos(window.left, window.top, window.width, window.height)

    # Set Windows process DPI awareness to per-monitor mode.
    def declare_dpi_aware(self) -> None:
        self._windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE

    def capture_window(self, title: str) -> 'np.ndarray | None':
        """
        Capture a window's client area (excludes title bar and window borders) and return
        a BGR numpy array (cv2-compatible).  Uses GetClientRect + ClientToScreen to locate
        the content region.  Does NOT change DPI awareness — mss and win32 both operate in
        whatever coordinate mode the process already has, keeping them consistent.
        Requires: mss, opencv-python, numpy (not enforced at module level).
        """
        # mss/opencv-python/numpy are a further-optional layer on top of WindowManager's
        # own required deps (not checked in __init__, per the docstring above), so they
        # stay as local per-call imports rather than being cached on self.
        try:
            import mss as _mss
            import numpy as _np
            import cv2 as _cv2
        except ImportError as e:
            print(f'capture_window requires mss, opencv-python, numpy: {e}')
            return None

        matches = self._get_windows_exact(title)
        if not matches:
            print(f'capture_window: window "{title}" not found.')
            return None

        hwnd = matches[0]._hWnd
        # Client area coordinates — excludes title bar and window borders
        client_rect = self._win32gui.GetClientRect(hwnd)  # (0, 0, width, height) in client coords
        pt = self._win32gui.ClientToScreen(hwnd, (0, 0))  # client top-left in screen coords
        monitor = {
            'left':   pt[0],
            'top':    pt[1],
            'width':  client_rect[2],
            'height': client_rect[3],
        }
        print(f'  [capture_window] hwnd={hwnd}  client={client_rect[2]}x{client_rect[3]}'
              f'  screen_pos=({pt[0]},{pt[1]})')

        with _mss.mss() as sct:
            raw = sct.grab(monitor)
        return _cv2.cvtColor(_np.array(raw), _cv2.COLOR_BGRA2BGR)

    lib_demo_params = [
        {'key': 'a', 'name': 'Get Screen Size', 'function': 'get_screen_size', 'inputs': []},
        {'key': 'b', 'name': 'Get Foreground Window Handle', 'function': 'get_foreground_window_handle', 'inputs': []},
        {'key': 'c', 'name': 'Get Foreground Window Title', 'function': 'get_foreground_window_title', 'inputs': []},
        {'key': 'd', 'name': 'Get All Windows', 'function': 'get_all_windows', 'inputs': []},
        {'key': 'e', 'name': 'Get All Window Titles', 'function': 'get_all_window_titles', 'inputs': []},
        {'key': 'f', 'name': 'Get Window Position', 'function': 'get_window_pos', 'inputs': [
            {'label': 'Window title', 'name': 'name', 'type': str, 'default': '', 'width': '180px'},
            {'label': 'Handle', 'name': 'handle', 'type': int, 'default': 0, 'width': '80px'},
        ]},
        {'key': 'g', 'name': 'Focus Window', 'function': 'focus_window', 'inputs': [
            {'label': 'Handle', 'name': 'handle', 'type': int, 'default': 0, 'width': '80px'},
        ]},
        {'key': 'h', 'name': 'Get System Volume', 'function': 'get_system_volume', 'inputs': []},
        {'key': 'i', 'name': 'Set System Volume', 'function': 'set_system_volume', 'inputs': [
            {'label': 'Volume (0.0-1.0)', 'name': 'volume', 'type': float, 'default': 0.2, 'width': '90px'},
        ]},
        {'key': 'j', 'name': 'Capture Window', 'function': 'capture_window', 'inputs': [
            {'label': 'Window title', 'name': 'title', 'type': str, 'default': 'scrcpy', 'width': '180px'},
        ]},
    ]

    # Return the current master volume level (0.0 – 1.0).
    def get_system_volume(self) -> float:
        return self._AudioUtilities.GetSpeakers().EndpointVolume.GetMasterVolumeLevelScalar()

    # Set the master volume level (0.0 – 1.0).
    def set_system_volume(self, volume: float) -> None:
        assert 0.0 <= volume <= 1.0, 'Volume must be between 0.0 and 1.0'
        self._AudioUtilities.GetSpeakers().EndpointVolume.SetMasterVolumeLevelScalar(volume, None)


class InputSimulator:
    """Mouse movement and click simulation with optional input blocking.

    Args:
        win_manager: WindowManager instance used for focus save/restore in
                     mouse_click(). A default instance is created if not provided.
    """

    def __init__(self, win_manager: WindowManager = None) -> None:
        # Checked here (at construction) rather than at module-import time, so merely
        # importing this module doesn't require Windows or pynput - only actually
        # instantiating InputSimulator does. Constructing a default WindowManager (when
        # win_manager isn't provided) triggers its own checks for its own dependencies.
        _check_windows_platform()
        utils.exit_if_module_missing('pynput')
        from pynput import mouse as _pynput_mouse
        from pynput.mouse import Button
        from ctypes import windll
        self._mouse_ctrl = _pynput_mouse.Controller()
        self._btn_left = Button.left
        self._windll = windll
        self._win = win_manager or WindowManager()

    # Return the current mouse cursor position.
    def get_mouse_pos(self) -> MousePos:
        x, y = self._mouse_ctrl.position
        return MousePos(x, y)

    # Block all keyboard and mouse input (Windows only).
    def block_input(self) -> None:
        self._windll.user32.BlockInput(True)

    # Re-enable keyboard and mouse input (Windows only).
    def allow_input(self) -> None:
        self._windll.user32.BlockInput(False)

    # Move the mouse cursor to the given position.
    def mouse_move(self, pos: MousePos) -> None:
        self._mouse_ctrl.position = (pos.x, pos.y)

    lib_demo_params = [
        {'key': 'a', 'name': 'Get Mouse Position', 'function': 'get_mouse_pos', 'inputs': [],
         'fill_targets': {
             'Move Mouse.x': lambda r: r.x, 'Move Mouse.y': lambda r: r.y,
             'Mouse Click.x': lambda r: r.x, 'Mouse Click.y': lambda r: r.y,
         }},
        {'key': 'b', 'name': 'Move Mouse', 'function': lambda self, x, y: self.mouse_move(MousePos(x, y)), 'inputs': [
            {'label': 'X', 'name': 'x', 'type': int, 'default': 100, 'width': '70px'},
            {'label': 'Y', 'name': 'y', 'type': int, 'default': 100, 'width': '70px'},
        ]},
        {'key': 'c', 'name': 'Mouse Click',
         'function': lambda self, x, y, delay_s_during, delay_s_after, blocking: self.mouse_click(MousePos(x, y), delay_s_during=delay_s_during, delay_s_after=delay_s_after, blocking=blocking),
         'inputs': [
            {'label': 'X', 'name': 'x', 'type': int, 'default': 100, 'width': '70px'},
            {'label': 'Y', 'name': 'y', 'type': int, 'default': 100, 'width': '70px'},
            {'label': 'Delay During (s)', 'name': 'delay_s_during', 'type': float, 'default': 0.01, 'width': '50px'},
            {'label': 'Delay After (s)', 'name': 'delay_s_after', 'type': float, 'default': 0.01, 'width': '50px'},
            {'label': 'Block Input', 'name': 'blocking', 'type': bool, 'default': True},
        ]},
    ]

    # Perform a left mouse click at pos with optional blocking and focus/position restore.
    def mouse_click(
        self,
        pos: MousePos,
        delay_s_during: float = 0.01,
        delay_s_after: float = 0.01,
        target_window_handle: int = 0,
        blocking: bool = True,
        restore_pos: bool = True,
        restore_focus: bool = True,
    ) -> None:
        if blocking:
            self.block_input()

        orig_handle = self._win.get_foreground_window_handle() if restore_focus else None
        orig_pos = self._mouse_ctrl.position if restore_pos else None

        if target_window_handle:
            self._win.focus_window(target_window_handle)

        self._mouse_ctrl.position = (pos.x, pos.y)
        self._mouse_ctrl.press(self._btn_left)
        utils.sleep(delay_s_during)
        self._mouse_ctrl.release(self._btn_left)
        utils.sleep(delay_s_after)

        if restore_pos and orig_pos is not None:
            self._mouse_ctrl.position = orig_pos
        if restore_focus and orig_handle is not None:
            self._win.focus_window(orig_handle)
        if blocking:
            self.allow_input()


if __name__ == '__main__':
    demo_target = utils.get_user_input('Select demo target (window/input): ', str, 'window')
    if demo_target and demo_target.strip().lower().startswith('i'):
        utils.demo(InputSimulator())
    else:
        utils.demo(WindowManager())
