import os
import platform
import re
import socket
import subprocess
import sys
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version


class UtilityRuntimeMixin:
    # Windows: os.getlogin() (OSError without a logon session, e.g. in a service); else getpass.getuser() or None
    def get_logon_username(self):
        if os.name == 'nt':
            return os.getlogin()
        else:
            try:
                import getpass
                return getpass.getuser()
            except Exception:
                return None

    def get_hostname(self):
        return socket.gethostname()

    # platform.platform(), e.g. 'Windows-11-10.0.26200-SP0'
    def os_info(self):
        return platform.platform()

    # platform.system(): 'Windows', 'Linux' or 'Darwin'
    def os_platform(self):
        return platform.system()

    # e.g. 'Windows 11, version 24H2' from the build number; builds not in its table -> 'Unknown Windows version'
    def os_version_win(self):
        platform_name = self.os_platform()
        if platform_name == 'Windows':
            build_map = {
                10240: 'Windows 10, version 1507',
                10586: 'Windows 10, version 1511',
                14393: 'Windows 10, version 1607',
                15063: 'Windows 10, version 1703',
                16299: 'Windows 10, version 1709',
                17134: 'Windows 10, version 1803',
                17763: 'Windows 10, version 1809',
                18362: 'Windows 10, version 1903',
                18363: 'Windows 10, version 1909',
                19041: 'Windows 10, version 2004',
                19042: 'Windows 10, version 20H2',
                19043: 'Windows 10, version 21H1',
                19044: 'Windows 10, version 21H2',
                19045: 'Windows 10, version 22H2',
                22000: 'Windows 11, version 21H2',
                22621: 'Windows 11, version 22H2',
                22631: 'Windows 11, version 23H2',
                26100: 'Windows 11, version 24H2',
            }
            build_number = int(self.os_info().split('.')[-1].split('-')[0])
            return build_map.get(build_number, 'Unknown Windows version')
        return 'Unknown OS version'

    # Hardware serial number (BIOS / DMI, Mac, Raspberry Pi); None if unavailable (Linux DMI usually needs root)
    def get_serial_number(self):
        system = platform.system()
        serial = ''
        try:
            if system == 'Windows':
                serial = self.run_powershell_command('(Get-CimInstance Win32_BIOS).SerialNumber')
            elif system == 'Darwin':
                out = subprocess.check_output(['ioreg', '-c', 'IOPlatformExpertDevice', '-d', '2'],
                                              text=True, errors='replace')
                match = re.search(r'"IOPlatformSerialNumber"\s*=\s*"([^"]+)"', out)
                serial = match.group(1) if match else ''
            else:
                # Linux / other Unix: DMI (PCs and servers; root-only on most distros), then the device
                # tree (Raspberry Pi and other ARM boards), then /proc/cpuinfo's 'Serial' line (older Pi kernels)
                for path in ('/sys/class/dmi/id/product_serial', '/sys/firmware/devicetree/base/serial-number'):
                    try:
                        with open(path, 'rb') as f:
                            serial = f.read().decode(errors='replace').strip('\x00 \t\r\n')
                    except OSError:
                        continue
                    if serial:
                        break
                if not serial:
                    try:
                        with open('/proc/cpuinfo', encoding='utf-8', errors='replace') as f:
                            match = re.search(r'^Serial\s*:\s*(\S+)', f.read(), re.MULTILINE)
                        serial = match.group(1) if match else ''
                    except OSError:
                        pass
        except (OSError, subprocess.SubprocessError):
            serial = ''
        serial = (serial or '').strip()
        # firmware placeholders that aren't real serial numbers
        placeholders = {'', 'to be filled by o.e.m.', 'default string', 'system serial number', 'not specified',
                        'not applicable', 'none', 'n/a', '0123456789'}
        if serial.lower() in placeholders or set(serial) <= {'0'}:
            return None
        return serial

    # platform.processor() (can be '' on Linux)
    def get_cpu_info(self):
        return platform.processor()

    # Days since boot as a float (Windows: PowerShell LastBootUpTime, else `uptime -s`)
    def get_up_time_days(self):
        if os.name == 'nt':
            boot_time_output = self.run_powershell_command('Get-CimInstance Win32_OperatingSystem | select -ExpandProperty LastBootUpTime | Get-Date -UFormat "%Y-%m-%d %H:%M:%S"')
            boot_time = datetime.strptime(boot_time_output, '%Y-%m-%d %H:%M:%S')
        else:
            uptime_output = subprocess.check_output(['uptime', '-s']).decode(errors='replace').strip()
            boot_time = datetime.strptime(uptime_output, '%Y-%m-%d %H:%M:%S')

        current_time = datetime.now()
        difference_in_seconds = (current_time - boot_time).total_seconds()
        difference_in_days = difference_in_seconds / (24 * 3600)
        return difference_in_days

    def get_user_home_directory(self):
        return os.path.expanduser('~')

    # Join path and replace with os specific path separator
    def os_path_join(self, *paths):
        return os.path.join(*paths).replace('\\', os.sep).replace('/', os.sep)

    def in_virtualenv(self):
        return hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)

    def get_python_exe_path(self):
        return os.path.realpath(sys.executable)

    # e.g. '3.12.4'; detailed=True -> the full sys.version string
    def get_python_version(self, detailed=False):
        if detailed:
            return sys.version
        else:
            return platform.python_version()

    # True if the pip *distribution* is installed (e.g. 'pyserial', not 'serial'); prints a pip hint if not
    def module_exists(self, module_name, print_error_on_missing=True):
        try:
            version(module_name)
            return True
        except PackageNotFoundError:
            if print_error_on_missing:
                print(f'{module_name} is not installed. To install, please run:\n  pip install {module_name}')
            return False

    # Installed version of a pip distribution, else the string 'Package not found'
    def get_python_pkg_version(self, pkg_name):
        try:
            return version(pkg_name)
        except ImportError:
            return 'Package not found'

    # prompt a Y/N question via input(); returns True only on an exact 'y'/'Y' reply
    def confirm(self, prompt):
        return input(f'{prompt} (Y/N): ').strip().lower() == 'y'

    # append param to kwargs if not already set, or update value if overwrite argument is true
    def update_kwargs_param(self, kwargs, param_name, param_value, overwrite=False):
        if overwrite:
            kwargs[param_name] = param_value
        else:
            kwargs.setdefault(param_name, param_value)
        return kwargs

    # python-git-info dict (or one field, e.g. 'commit') for the cwd's repo as of gitinfo's first import; None if unavailable
    def get_git_info(self, info=None):
        if not self.module_exists('python-git-info'):
            return
        import gitinfo
        try:
            return gitinfo.get_git_info()[info] if info else gitinfo.get_git_info()
        except Exception:
            return None

    # fetch the latest release info of a github repo
    def get_github_latest_release(self, repo_owner, repo_name):
        if not self.module_exists('requests'):
            return
        import requests
        url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest'
        response = requests.get(url)
        release_info = response.json()
        return release_info

    # get the release binary download url with specified filters
    def get_github_release_download_url(self, release_info, filter_name='browser_download_url', filter_value=''):
        urls = []
        for asset in release_info['assets']:
            if filter_value in asset[filter_name]:
                urls.append(asset['browser_download_url'])
        return urls

    # Emit a system beep at the given frequency and duration.
    # Windows: winsound.Beep() gives precise hardware-level freq/duration control.
    # Linux: the `beep` CLI tool (apt install beep) provides the same control but requires
    #   root/group permissions or the `beep` package; falls back to a terminal bell (\a)
    #   which has no frequency or duration control — it is a single audible alert only.
    def beep(self, freq: int = 1000, duration_ms: int = 1000) -> None:
        if os.name == 'nt':
            import winsound
            winsound.Beep(freq, duration_ms)
        else:
            # TODO To be tested
            try:
                subprocess.run(
                    ['beep', '-f', str(freq), '-l', str(duration_ms)],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except (FileNotFoundError, subprocess.CalledProcessError):
                # fallback: terminal bell — no freq/duration control
                print('\a', end='', flush=True)

    # Emit multiple beeps with a gap between each.
    def beep_multi(self, count: int, gap_ms: int = 100, freq: int = 1000, duration_ms: int = 100) -> None:
        for _ in range(count):
            self.beep(freq, duration_ms)
            self.sleep(gap_ms / 1000)
