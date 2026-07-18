import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()
utils.exit_if_module_missing('numpy')

import os
import re
import subprocess
import random
import numpy as np


class AdbUtils:
    def __init__(self, adb_path=None):
        # Checked here (at construction) rather than at module-import time, so merely
        # importing this module doesn't require opencv-python - only actually
        # instantiating AdbUtils does. Cached on self so take_screenshot/save_screenshot
        # don't need their own import statements.
        utils.exit_if_module_missing('opencv-python')
        import cv2
        self._cv2 = cv2
        adb_path = adb_path or 'adb'
        # CreateProcess on Windows needs the actual .exe, not its containing folder
        if os.path.isdir(adb_path):
            adb_path = os.path.join(adb_path, 'adb.exe')
        self.adb_path = adb_path
        self.device = None  # active device serial; None = let adb pick the only connected device

    def _run(self, *args, binary=False):
        cmd = [self.adb_path]
        if self.device:
            cmd += ['-s', self.device]
        cmd += list(args)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, _ = process.communicate()
        if binary:
            return stdout
        return stdout.decode('utf-8', errors='replace').strip()

    def get_devices(self):
        output = self._run('devices')
        lines = output.splitlines()
        serials = []
        for line in lines[1:]:  # skip header "List of devices attached"
            parts = line.split()
            if len(parts) >= 2 and parts[1] == 'device':
                serials.append(parts[0])
        return serials

    def set_device(self, serial):
        self.device = serial

    def get_api_level(self):
        output = self._run('shell', 'getprop', 'ro.build.version.sdk')
        try:
            return int(output.strip())
        except ValueError:
            print(f'get_api_level: could not parse api level from "{output}"')
            return None

    def _run_cmd(self, cmd):
        return self._run(*cmd.split())

    # each entry: (command string, line filter keywords, api levels it has been confirmed on)
    # add new sources here as they're verified on-device, and note the api level so
    # get_current_activity_name keeps trying only what's plausible before falling back
    _activity_sources = [
        ('shell dumpsys window', ('mCurrentFocus', 'mFocusedApp', 'mObscuringWindow'), 'confirmed API 36'),
        ('shell dumpsys window windows', ('mCurrentFocus', 'mFocusedApp', 'mObscuringWindow'), 'older API'),
        ('shell dumpsys activity activities', ('mResumedActivity',), 'fallback, untested range'),
    ]

    def get_current_activity_name(self):
        for cmd, keys, _tested in self._activity_sources:
            out_lines = self._run_cmd(cmd).splitlines()
            # walk keywords in priority order (mCurrentFocus before mObscuringWindow, etc.) — some
            # keywords' lines (e.g. mObscuringWindow's wallpaper/systemui window) have no pkg/activity
            # to extract, so taking the single "last matching line" could skip a good one earlier
            for keyword in keys:
                for line in out_lines:
                    if keyword not in line:
                        continue
                    if 'null' in line:
                        print('get_current_activity_name: active activity not found, is the screen unlocked?')
                        return None
                    match = re.search(r'[\w.]+/[\w.]+', line)
                    if match:
                        return match.group(0)
        print(f'get_current_activity_name: no focused window info found (api level {self.get_api_level()})')
        return None

    def get_screen_size(self):
        output = self._run('shell', 'wm', 'size')
        # output: "Physical size: 1080x2340"
        try:
            size_str = output.split(':')[-1].strip()
            w, h = size_str.split('x')
            return int(w), int(h)
        except Exception as e:
            print(f'Error parsing screen size from "{output}": {e}')
            return None

    def take_screenshot(self):
        png_bytes = self._run('exec-out', 'screencap', '-p', binary=True)
        if not png_bytes:
            print('take_screenshot: no data received from adb')
            return None
        arr = np.frombuffer(png_bytes, dtype=np.uint8)
        img = self._cv2.imdecode(arr, self._cv2.IMREAD_COLOR)
        if img is None:
            print('take_screenshot: cv2.imdecode failed — bad PNG data')
        return img

    def save_screenshot(self, path='screenshot.png'):
        img = self.take_screenshot()
        if img is not None:
            self._cv2.imwrite(path, img)
            print(f'Screenshot saved to {path}')
        return img

    def tap(self, x, y, jitter_px=10):
        screen = self.get_screen_size()
        tx = x + random.randint(-jitter_px, jitter_px)
        ty = y + random.randint(-jitter_px, jitter_px)
        if screen:
            tx = max(0, min(tx, screen[0] - 1))
            ty = max(0, min(ty, screen[1] - 1))
        self._run('shell', 'input', 'tap', str(tx), str(ty))

    def tap_in_region(self, x1, y1, x2, y2, margin=0.25):
        dx = (x2 - x1) * margin
        dy = (y2 - y1) * margin
        tx = random.randint(int(x1 + dx), int(x2 - dx))
        ty = random.randint(int(y1 + dy), int(y2 - dy))
        self._run('shell', 'input', 'tap', str(tx), str(ty))

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        self._run('shell', 'input', 'swipe',
                  str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    # video container extensions; used to exclude videos when only photos are wanted —
    # excluding by video (a small, stable set) is more robust than including by photo
    # extension, since phone cameras produce many/growing photo formats (heic, dng, ...)
    video_exts = {'.mp4', '.mov', '.3gp', '.mkv', '.webm', '.m4v', '.avi'}

    def list_latest_files(self, remote_dir, count=1, exclude_exts=None):
        # 'ls -t -1' relies on the device's toolbox/coreutils ls supporting these flags (true for modern Android)
        output = self._run('shell', 'ls', '-t', '-1', remote_dir)
        if not output or 'No such file' in output or 'Permission denied' in output:
            return []
        names = [line.strip() for line in output.splitlines() if line.strip()]
        if exclude_exts:
            names = [name for name in names if os.path.splitext(name)[1].lower() not in exclude_exts]
        remote_dir = remote_dir.rstrip('/')
        return [f'{remote_dir}/{name}' for name in names[:count]]

    def pull_files(self, remote_paths, dest_dir, move=False):
        dest_dir = os.path.expanduser(dest_dir)
        os.makedirs(dest_dir, exist_ok=True)
        pulled = []
        for remote_path in remote_paths:
            self._run('pull', remote_path, dest_dir)
            local_path = os.path.join(dest_dir, os.path.basename(remote_path))
            if os.path.exists(local_path):
                pulled.append(local_path)
                if move:
                    self._run('shell', 'rm', remote_path)
            else:
                print(f'pull_files: failed to pull {remote_path}')
        return pulled

    def pull_latest_files(self, remote_dir, dest_dir='~', count=1, move=False, exclude_exts=None):
        remote_paths = self.list_latest_files(remote_dir, count, exclude_exts=exclude_exts)
        if not remote_paths:
            print(f'pull_latest_files: no files found in {remote_dir}')
            return []
        return self.pull_files(remote_paths, dest_dir, move=move)

    # common Android camera output directories, checked in order until one yields files
    common_dcim_paths = [
        '/sdcard/DCIM/Camera',
        '/storage/emulated/0/DCIM/Camera',
        '/sdcard/DCIM/100ANDRO',
        '/storage/emulated/0/Pictures',
    ]

    def pull_latest_media_files(self, dest_dir='~', count=1, move=False, dcim_paths=None, photos_only=False):
        exclude_exts = self.video_exts if photos_only else None
        for remote_dir in dcim_paths or self.common_dcim_paths:
            pulled = self.pull_latest_files(remote_dir, dest_dir, count=count, move=move, exclude_exts=exclude_exts)
            if pulled:
                return pulled
        print('pull_latest_media_files: no files found in any common DCIM directory')
        return []

    lib_demo_params = [
        {'key': 'a', 'name': 'Get Devices', 'function': 'get_devices', 'inputs': []},
        {'key': 'b', 'name': 'Get Screen Size', 'function': 'get_screen_size', 'inputs': []},
        {'key': 'i', 'name': 'Get Current Activity Name', 'function': 'get_current_activity_name', 'inputs': []},
        {'key': 'j', 'name': 'Get API Level', 'function': 'get_api_level', 'inputs': []},
        {'key': 'c', 'name': 'Save Screenshot', 'function': 'save_screenshot', 'inputs': [
            {'label': 'Output path', 'name': 'path', 'type': str, 'default': 'screenshot.png', 'width': '200px'},
        ]},
        {'key': 'd', 'name': 'Tap', 'function': 'tap', 'inputs': [
            {'label': 'X', 'name': 'x', 'type': int, 'default': 540},
            {'label': 'Y', 'name': 'y', 'type': int, 'default': 960},
            {'label': 'Jitter px', 'name': 'jitter_px', 'type': int, 'default': 10},
        ]},
        {'key': 'e', 'name': 'Tap in Region', 'function': 'tap_in_region', 'inputs': [
            {'label': 'X1', 'name': 'x1', 'type': int, 'default': 100},
            {'label': 'Y1', 'name': 'y1', 'type': int, 'default': 100},
            {'label': 'X2', 'name': 'x2', 'type': int, 'default': 980},
            {'label': 'Y2', 'name': 'y2', 'type': int, 'default': 200},
            {'label': 'Margin', 'name': 'margin', 'type': float, 'default': 0.25},
        ]},
        {'key': 'f', 'name': 'Swipe', 'function': 'swipe', 'inputs': [
            {'label': 'X1', 'name': 'x1', 'type': int, 'default': 540},
            {'label': 'Y1', 'name': 'y1', 'type': int, 'default': 800},
            {'label': 'X2', 'name': 'x2', 'type': int, 'default': 540},
            {'label': 'Y2', 'name': 'y2', 'type': int, 'default': 400},
            {'label': 'Duration ms', 'name': 'duration_ms', 'type': int, 'default': 300},
        ]},
        {'key': 'g', 'name': 'Pull Latest Files', 'function': 'pull_latest_files', 'inputs': [
            {'label': 'Remote dir', 'name': 'remote_dir', 'type': str, 'default': '/sdcard/DCIM/Camera', 'width': '250px'},
            {'label': 'Dest dir', 'name': 'dest_dir', 'type': str, 'default': '~', 'width': '200px'},
            {'label': 'Count', 'name': 'count', 'type': int, 'default': 1},
            {'label': 'Move (delete from device)', 'name': 'move', 'type': bool, 'default': False},
        ]},
        {'key': 'h', 'name': 'Pull Latest Media Files', 'function': 'pull_latest_media_files', 'inputs': [
            {'label': 'Dest dir', 'name': 'dest_dir', 'type': str, 'default': '~', 'width': '200px'},
            {'label': 'Count', 'name': 'count', 'type': int, 'default': 1},
            {'label': 'Move (delete from device)', 'name': 'move', 'type': bool, 'default': False},
            {'label': 'Photos only (exclude videos)', 'name': 'photos_only', 'type': bool, 'default': False},
        ]},
    ]


if __name__ == '__main__':
    adb = AdbUtils()
    utils.demo(adb)
