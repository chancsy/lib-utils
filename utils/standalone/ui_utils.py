import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions

utils = UtilityFunctions()

import tkinter as tk
from tkinter import filedialog, simpledialog


def _win32_force_foreground(hwnd: int) -> None:
    """Bypass Windows focus-stealing prevention via AttachThreadInput.

    When Python runs as a Jupyter kernel (background process), the OS blocks
    SetForegroundWindow unless our thread is attached to the foreground thread.
    GetAncestor(GA_ROOT) resolves the outer frame HWND: winfo_id() on Tk/Toplevel
    returns the inner client HWND, which SetForegroundWindow silently rejects.
    See also: WindowManager.force_foreground_window in win_automation_utils.py.
    """
    try:
        import ctypes
        GA_ROOT = 2
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong  # thread IDs are unsigned
        kernel32.GetCurrentThreadId.restype = ctypes.c_ulong
        frame_hwnd = user32.GetAncestor(hwnd, GA_ROOT) or hwnd   # outer frame, not inner client
        fg_hwnd = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
        cur_tid = kernel32.GetCurrentThreadId()
        if fg_tid and fg_tid != cur_tid:
            user32.AttachThreadInput(cur_tid, fg_tid, True)
            user32.BringWindowToTop(frame_hwnd)
            user32.SetForegroundWindow(frame_hwnd)
            user32.AttachThreadInput(cur_tid, fg_tid, False)
        else:
            user32.SetForegroundWindow(frame_hwnd)
    except Exception:
        pass


class _TkWindow:
    """Context manager: transparent Tk root forced to OS foreground so child dialogs appear focused.

    Root is positioned so native file dialogs (~1000x650) open centered on screen.
    _schedule_center polls for Toplevel children (simpledialog), centers each one using its
    actual pixel dimensions once visible, then forces it to OS foreground.
    _seen is cleared when no children are present so Tk's reused widget path names
    (e.g. .!toplevel) do not cause a second sequential dialog to be skipped.
    """

    def __init__(self):
        self.root = None
        self._seen = set()
        self._center_job = None

    def __enter__(self) -> tk.Tk:
        self.root = tk.Tk()
        self._sw = self.root.winfo_screenwidth()
        self._sh = self.root.winfo_screenheight()
        x = max(0, (self._sw - 1000) // 2)
        y = max(0, (self._sh - 650) // 2)
        self.root.geometry(f'1x1+{x}+{y}')
        self.root.attributes('-alpha', 0)
        self.root.attributes('-topmost', True)
        self.root.update()   # ensure HWND is valid before Win32 call
        _win32_force_foreground(self.root.winfo_id())
        self._schedule_center()
        return self.root

    def _schedule_center(self) -> None:
        """Center and focus each new Toplevel child using its actual dimensions; runs until context exits."""
        if not self.root:
            return
        try:
            children = self.root.winfo_children()
            if not children:
                self._seen.clear()  # reset so next dialog (Tk may reuse .!toplevel path) gets centred
            for child in children:
                cid = str(child)
                if cid in self._seen:
                    continue
                child.update_idletasks()
                w, h = child.winfo_width(), child.winfo_height()
                if w > 1 and h > 1:
                    child.geometry(f'+{(self._sw - w) // 2}+{(self._sh - h) // 2}')
                    _win32_force_foreground(child.winfo_id())
                    self._seen.add(cid)
            self._center_job = self.root.after(5, self._schedule_center)
        except Exception:
            pass

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.root:
            if self._center_job:
                try:
                    self.root.after_cancel(self._center_job)
                except Exception:
                    pass
            self.root.destroy()
            self.root = None


class UIUtils:
    """Tkinter-based GUI dialogs for file selection and password prompts."""

    # Open a file-picker dialog; returns path string or tuple of strings when allow_multiple=True.
    def open_filedialog(
        self,
        allow_multiple: bool = False,
        filetypes: tuple = (('All files', '*.*'),),
    ) -> str | tuple[str, ...]:
        with _TkWindow() as root:
            if allow_multiple:
                return filedialog.askopenfilenames(parent=root, filetypes=filetypes)
            return filedialog.askopenfilename(parent=root, filetypes=filetypes)

    # Open a save-as dialog; returns the chosen path string, or '' if cancelled.
    def save_as_filedialog(
        self,
        filetypes: tuple = (('All files', '*.*'),),
        initialfile: str = '',
    ) -> str:
        with _TkWindow() as root:
            return filedialog.asksaveasfilename(parent=root, filetypes=filetypes, initialfile=initialfile)

    # Prompt for a typed value via a GUI dialog; returns converted value or None if cancelled.
    def prompt_user_input(
        self,
        input_type: str = 'string',
        prompt_msg: str = '',
    ) -> str | int | float | None:
        dialog_map = {
            'string':  simpledialog.askstring,
            'integer': simpledialog.askinteger,
            'float':   simpledialog.askfloat,
        }
        assert input_type in dialog_map, f'Valid input types: {list(dialog_map)}'
        with _TkWindow() as root:
            return dialog_map[input_type](title='Input', prompt=prompt_msg or 'Enter value:', parent=root)

    # Prompt for a password via a GUI dialog; returns password string or None if too short / cancelled.
    def prompt_user_password(self, min_password_len: int = 8) -> str | None:
        with _TkWindow() as root:
            user_pass = simpledialog.askstring(title='Password', prompt='Enter password:', show='*', parent=root)
        if not user_pass or len(user_pass) < min_password_len:
            print(f'Password length less than {min_password_len}.')
            return None
        return user_pass

    # Prompt for a password twice; returns password only if both entries match and meet length.
    def prompt_user_password_twice_matching(self, min_password_len: int = 8) -> str | None:
        with _TkWindow() as root:
            user_pass1 = simpledialog.askstring(title='Password', prompt='Enter password:', show='*', parent=root)
            if not user_pass1 or len(user_pass1) < min_password_len:
                print(f'Password length less than {min_password_len}.')
                return None

        with _TkWindow() as root:
            user_pass2 = simpledialog.askstring(title='Password', prompt='Enter password again:', show='*', parent=root)

        if user_pass1 != user_pass2:
            print('Passwords do not match.')
            return None
        return user_pass1

    lib_demo_params = [
        {'key': 'a', 'name': 'Open file dialog (single)', 'function': 'open_filedialog', 'inputs': []},
        {'key': 'b', 'name': 'Open file dialog (multiple)', 'function': lambda self: self.open_filedialog(allow_multiple=True), 'inputs': []},
        {'key': 'c', 'name': 'Save as dialog', 'function': 'save_as_filedialog', 'inputs': [
            {'label': 'Initial file', 'name': 'initialfile', 'type': str, 'default': '', 'width': '150px'},
        ]},
        {'key': 'd', 'name': 'Prompt user input', 'function': 'prompt_user_input', 'inputs': [
            {'label': 'Input type', 'name': 'input_type', 'options': ['string', 'integer', 'float'], 'default': 'string', 'width': '90px'},
            {'label': 'Prompt', 'name': 'prompt_msg', 'type': str, 'default': 'Enter value: ', 'width': '150px'},
        ]},
        {'key': 'e', 'name': 'Prompt user password', 'function': 'prompt_user_password', 'inputs': [
            {'label': 'Min len', 'name': 'min_password_len', 'type': int, 'default': 1, 'width': '60px'},
        ]},
        {'key': 'f', 'name': 'Prompt user password (matching)', 'function': 'prompt_user_password_twice_matching', 'inputs': [
            {'label': 'Min len', 'name': 'min_password_len', 'type': int, 'default': 1, 'width': '60px'},
        ]},
    ]


if __name__ == '__main__':
    ui = UIUtils()
    utils.demo(ui)
