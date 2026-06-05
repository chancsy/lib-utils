import os
import platform
import socket
import subprocess
import sys
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version


class UtilityRuntimeMixin:
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

    def os_info(self):
        return platform.platform()

    def os_platform(self):
        return platform.system()

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

    def get_serial_number(self):
        return platform.node()

    def get_cpu_info(self):
        return platform.processor()

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

    def get_python_version(self, detailed=False):
        if detailed:
            return sys.version
        else:
            return platform.python_version()

    def module_exists(self, module_name, print_error_on_missing=True):
        try:
            version(module_name)
            return True
        except PackageNotFoundError:
            if print_error_on_missing:
                print(f'{module_name} is not installed. To install, please run:\n  pip install {module_name}')
            return False

    def get_python_pkg_version(self, pkg_name):
        try:
            return version(pkg_name)
        except ImportError:
            return 'Package not found'

    # append param to kwargs if not already set, or update value if overwrite argument is true
    def update_kwargs_param(self, kwargs, param_name, param_value, overwrite=False):
        if overwrite:
            kwargs[param_name] = param_value
        else:
            kwargs.setdefault(param_name, param_value)
        return kwargs

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
        releast_info = response.json()
        return releast_info

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
