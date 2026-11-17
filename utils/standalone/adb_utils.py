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
import time
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
        # stdin=DEVNULL: `adb shell` reads stdin, and would otherwise swallow the caller's console
        # input (keys typed during the call, or piped answers to a later input())
        process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, _ = process.communicate()
        if binary:
            return stdout
        return stdout.decode('utf-8', errors='replace').strip()

    # Serials of connected devices in 'device' state (unauthorized / offline ones skipped)
    def get_devices(self):
        output = self._run('devices')
        lines = output.splitlines()
        serials = []
        for line in lines[1:]:  # skip header "List of devices attached"
            parts = line.split()
            if len(parts) >= 2 and parts[1] == 'device':
                serials.append(parts[0])
        return serials

    # Send every later adb call to this serial (None: adb's only connected device)
    def set_device(self, serial):
        self.device = serial

    # --- Wireless (Wi-Fi) adb ---

    # adb server-level command (no -s); stdout + stderr text, as connect / pair report errors on either
    def _run_host(self, *args, timeout=20):
        try:
            r = subprocess.run([self.adb_path, *args], stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return f'timed out after {timeout}s'
        return (r.stdout + r.stderr).decode('utf-8', errors='replace').strip()

    @staticmethod
    def is_wireless(serial):
        """True for a Wi-Fi serial: 'host:port', or an mDNS one ('adb-<id>._adb-tls-connect._tcp')."""
        return bool(serial) and (':' in serial or '._adb-tls-connect.' in serial)

    def connect(self, address, port=5555, wait=5.0):
        """Connect to a device over Wi-Fi; returns its serial ('host:port') once it's usable, else None.

        address: 'host' or 'host:port' (port defaults to 5555, the `adb tcpip` port). Android 11+
        Wireless debugging uses the random port shown on its screen (pair first, see pair()).
        Waits up to `wait` seconds for the device to leave the offline / unauthorized state.
        """
        if ':' not in address:
            address = f'{address}:{port}'
        out = self._run_host('connect', address, timeout=10)
        if not out.startswith(('connected to', 'already connected to')):
            print(f'connect: {out}')
            return None
        t0 = time.perf_counter()
        while True:
            if address in self.get_devices():
                return address
            if time.perf_counter() - t0 >= wait:
                print(f'connect: {address} connected but not ready (unauthorized? accept the prompt on the device)')
                return None
            time.sleep(0.5)

    def disconnect(self, address=None):
        """Disconnect a Wi-Fi device ('host:port'), or every Wi-Fi device when None; returns adb's message."""
        return self._run_host('disconnect', *([address] if address else []))

    def pair(self, address, code):
        """Android 11+ Wireless debugging: pair with the 'host:port' and 6-digit code from the
        "Pair device with pairing code" dialog. Once per PC; then connect() to the port shown on the
        Wireless debugging screen (not the pairing port). Returns True on success."""
        out = self._run_host('pair', address, str(code))
        ok = 'Successfully paired' in out
        if not ok:
            print(f'pair: {out}')
        return ok

    def mdns_services(self):
        """Devices advertised over mDNS: list of (name, service, 'host:port').

        '_adb-tls-connect._tcp' entries are Wireless debugging devices ready for connect()
        (only devices already paired with this PC will accept)."""
        services = []
        for line in self._run_host('mdns', 'services').splitlines()[1:]:  # skip "List of discovered mdns services"
            parts = line.split()
            if len(parts) >= 3 and ':' in parts[-1]:
                services.append((parts[0], parts[1], parts[-1]))
        return services

    def get_wifi_ip(self):
        """The current device's Wi-Fi IPv4 address, or None (Wi-Fi off / not found)."""
        out = self._run('shell', 'ip', '-f', 'inet', 'addr', 'show', 'wlan0')
        m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', out)
        if not m:  # interface not named wlan0: take the source address of the default route
            m = re.search(r'src (\d+\.\d+\.\d+\.\d+)', self._run('shell', 'ip', 'route'))
        return m.group(1) if m else None

    def switch_to_wifi(self, port=5555):
        """Move the current USB device to Wi-Fi: `adb tcpip <port>`, then connect() to its Wi-Fi IP.

        Works on any Android version; lasts until the device reboots. Returns the new serial
        ('ip:port', also set as the current device) or None. The USB cable can then be unplugged.
        """
        ip = self.get_wifi_ip()
        if ip is None:
            print('switch_to_wifi: no Wi-Fi IP found - is the device on Wi-Fi?')
            return None
        out = self._run('tcpip', str(port))
        if 'restarting' not in out:
            print(f'switch_to_wifi: tcpip failed: {out}')
            return None
        time.sleep(2.0)  # adbd restarts in TCP mode
        serial = self.connect(ip, port)
        if serial:
            self.set_device(serial)
        return serial

    def get_hardware_serial(self):
        """The device's own serial (ro.serialno) - the same over USB and Wi-Fi, unlike the adb
        serial ('host:port' over Wi-Fi). Falls back to the adb serial if the property is empty.
        Cached per adb serial (it never changes for one), so repeated calls cost no adb round trip."""
        cache = self.__dict__.setdefault('_hw_serials', {})
        if self.device not in cache:
            out = self._run('shell', 'getprop', 'ro.serialno').strip()
            if not out:
                return self.device   # not cached: may be a transient failure
            cache[self.device] = out
        return cache[self.device]

    def pick_device(self, devices=None):
        """Choose a device among `devices` (default: get_devices()) and set it as current; returns
        its serial, or None if there are none.

        USB before Wi-Fi (lower latency), else adb's order. A paired Wireless debugging device is
        listed twice once adb auto-connects it ('host:port' and 'adb-<id>._adb-tls-connect._tcp'),
        so this warns only when the serials belong to different devices (by get_hardware_serial()).
        """
        devices = self.get_devices() if devices is None else list(devices)
        if not devices:
            return None
        if len(devices) > 1:
            hw = set()
            for s in devices:
                self.set_device(s)
                hw.add(self.get_hardware_serial())
            pick = sorted(devices, key=self.is_wireless)[0]   # stable: USB first
            if len(hw) > 1:
                print(f'Several devices attached: {devices} - using {pick} '
                      '(unplug the others, or connect to one explicitly).')
        else:
            pick = devices[0]
        self.set_device(pick)
        return pick

    def reconnect_wireless(self, saved=None):
        """Reconnect a Wi-Fi device: `saved` ('host:port', e.g. from your config) first, then each
        Wireless debugging device advertised over mDNS (its port changes every time Wireless
        debugging is turned on; only devices paired with this PC accept). Sets and returns the
        serial, or None. Store the returned address if it differs from `saved`."""
        if saved:
            print(f'Reconnecting over Wi-Fi to {saved}...')
            serial = self.connect(saved)
            if serial:
                self.set_device(serial)
                return serial
        for name, service, address in self.mdns_services():
            if not service.startswith('_adb-tls-connect'):
                continue
            print(f'Trying Wireless debugging device {name} at {address}...')
            serial = self.connect(address)
            if serial:
                self.set_device(serial)
                return serial
        return None

    # Android SDK level as int (e.g. 34); None if unparsable
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

    # Focused 'package/activity' from dumpsys; None if not found (e.g. screen locked)
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

    # (width, height) in px from `wm size`; None if unparsable
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

    # Screen as a BGR numpy image (cv2); None on failure
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

    # take_screenshot + cv2.imwrite(path); returns the image (None on failure)
    def save_screenshot(self, path='screenshot.png'):
        img = self.take_screenshot()
        if img is not None:
            self._cv2.imwrite(path, img)
            print(f'Screenshot saved to {path}')
        return img

    # Tap near (x, y) with a random +-jitter_px offset, clamped to the screen
    def tap(self, x, y, jitter_px=10):
        screen = self.get_screen_size()
        tx = x + random.randint(-jitter_px, jitter_px)
        ty = y + random.randint(-jitter_px, jitter_px)
        if screen:
            tx = max(0, min(tx, screen[0] - 1))
            ty = max(0, min(ty, screen[1] - 1))
        self._run('shell', 'input', 'tap', str(tx), str(ty))

    # Tap a random point in the box (x1, y1)-(x2, y2), margin (fraction) away from its edges
    def tap_in_region(self, x1, y1, x2, y2, margin=0.25):
        dx = (x2 - x1) * margin
        dy = (y2 - y1) * margin
        tx = random.randint(int(x1 + dx), int(x2 - dx))
        ty = random.randint(int(y1 + dy), int(y2 - dy))
        self._run('shell', 'input', 'tap', str(tx), str(ty))

    # Tap a random point in a region given as screen fractions (x1, y1, x2, y2), as RegionSetupTool
    # saves them; size = (w, h) in device pixels to scale by, default get_screen_size() (one adb call).
    # Scale by the device size, not by a scrcpy frame's, which is usually smaller.
    def tap_in_fraction_region(self, region, size=None, margin=0.25):
        size = size or self.get_screen_size()
        if not size:
            raise RuntimeError('tap_in_fraction_region: device screen size unknown')
        w, h = size
        x1, y1, x2, y2 = region
        self.tap_in_region(int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h), margin=margin)

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        self._run('shell', 'input', 'swipe',
                  str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    # video container extensions; used to exclude videos when only photos are wanted —
    # excluding by video (a small, stable set) is more robust than including by photo
    # extension, since phone cameras produce many/growing photo formats (heic, dng, ...)
    video_exts = {'.mp4', '.mov', '.3gp', '.mkv', '.webm', '.m4v', '.avi'}

    # Device paths of the newest count files in remote_dir (ls -t); [] if none or no access
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

    # adb pull each path into dest_dir (~ expanded) -> local paths; move=True deletes them on the device
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

    # Pull the newest count files of remote_dir -> local paths ([] if none)
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

    # Pull the newest count photos / videos from the first common DCIM folder that has any
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
        {'key': 'k', 'name': 'Switch USB Device to Wi-Fi', 'function': 'switch_to_wifi', 'inputs': [
            {'label': 'Port', 'name': 'port', 'type': int, 'default': 5555},
        ]},
        {'key': 'l', 'name': 'Connect over Wi-Fi', 'function': 'connect', 'inputs': [
            {'label': 'host[:port]', 'name': 'address', 'type': str, 'default': '192.168.1.2:5555', 'width': '180px'},
        ]},
        {'key': 'm', 'name': 'Pair (Android 11+)', 'function': 'pair', 'inputs': [
            {'label': 'host:port', 'name': 'address', 'type': str, 'default': '192.168.1.2:37000', 'width': '180px'},
            {'label': 'Code', 'name': 'code', 'type': str, 'default': '', 'width': '90px'},
        ]},
        {'key': 'n', 'name': 'mDNS Services', 'function': 'mdns_services', 'inputs': []},
        {'key': 'o', 'name': 'Disconnect Wi-Fi', 'function': 'disconnect', 'inputs': []},
        {'key': 'p', 'name': 'Pick Device (USB first, duplicates merged)', 'function': 'pick_device', 'inputs': []},
        {'key': 'r', 'name': 'Reconnect Wi-Fi (saved, then mDNS)', 'function': 'reconnect_wireless', 'inputs': [
            {'label': 'Saved host:port', 'name': 'saved', 'type': str, 'default': '', 'width': '180px'},
        ]},
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
