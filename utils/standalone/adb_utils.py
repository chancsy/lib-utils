import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()
utils.exit_if_module_missing('opencv-python')
utils.exit_if_module_missing('numpy')

import subprocess
import random
import numpy as np
import cv2


class AdbUtils:
    def __init__(self, adb_path=None):
        self.adb_path = adb_path or 'adb'
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
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            print('take_screenshot: cv2.imdecode failed — bad PNG data')
        return img

    def save_screenshot(self, path='screenshot.png'):
        img = self.take_screenshot()
        if img is not None:
            cv2.imwrite(path, img)
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

    lib_demo_params = [
        {'key': 'a', 'name': 'Get Devices', 'function': 'get_devices', 'inputs': []},
        {'key': 'b', 'name': 'Get Screen Size', 'function': 'get_screen_size', 'inputs': []},
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
    ]


if __name__ == '__main__':
    adb = AdbUtils()
    utils.demo(adb)
