import sys
import os
import subprocess
import platform
# from importlib.util import find_spec
import pkg_resources
import string
import re
import struct
import time
from enum import Enum
from datetime import datetime, timedelta
import calendar
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import urllib.parse
from html.parser import HTMLParser
import threading
import socket
import base64
# TODO import non-standard lib: requests, python-git-info

import pandas as pd
# from utilities import UtilityFunctions
# from utilities import * # to include all functions
# utils = UtilityFunctions()
# utils.exit_if_module_missing('selenium')
# if not utils.module_exists('selenium'):
#     return

try:
    from IPython.display import display, clear_output, HTML
    from IPython import get_ipython
except ImportError:
    pass

# class DataType(Enum):
#     UINT8 = 0
#     UINT16 = 1
#     UINT32 = 2
#     INT8 = 3
#     INT16 = 4
#     INT32 = 5
#     FLOAT = float
#     BYTEARRAY = bytearray

class UtilityFunctions:
    def __init__(self):
        # binary data utils init
        self._generate_convertion_functions()

        if self.in_ipython():
            self.ipython = get_ipython()

    def do_nothing(self, *args, **kwargs):
        pass

    def module_exists(self, module_name, print_error_on_missing=True):
        try:
            pkg_resources.get_distribution(module_name)
            return True
        except pkg_resources.DistributionNotFound:
            if print_error_on_missing:
                print(f'{module_name} is not installed. To install, please run:\n  pip install {module_name}')
            return False

    def exit_if_module_missing(self, module_name):
        if not self.module_exists(module_name):
            sys.exit(1)

    def run_powershell_command(self, command):
        process=subprocess.Popen(["powershell","& {" + command+ "}"], stdout=subprocess.PIPE)
        stdout_value = process.communicate()[0].decode("utf-8").strip()
        return stdout_value

    def wait_user_enter_key(self, msg=None):
        input(msg or 'Press enter to continue...')

    ############################################################################
    # IPython related
    ############################################################################
    def in_ipython(self, print_warning=False):
        if 'ipykernel' in sys.modules:
            return True
        if print_warning:
            print('Not in IPython environment')
        return False

    def ipython_print_default_expr(self):
        if self.in_ipython(print_warning=True):
            from IPython.core.interactiveshell import InteractiveShell
            InteractiveShell.ast_node_interactivity = "last_expr"

    def ipython_print_all_exprs(self):
        if self.in_ipython(print_warning=True):
            from IPython.core.interactiveshell import InteractiveShell
            InteractiveShell.ast_node_interactivity = "all"

    def ipython_run_magic_command(self, magic_name, line):
        if self.in_ipython(print_warning=True):
            self.ipython.run_line_magic(magic_name, line)

    def ipython_auto_reload_modules(self, print_warning=True):
        self.ipython_run_magic_command('reload_ext', 'autoreload')
        self.ipython_run_magic_command('autoreload', '2')
        if print_warning:
            print('Auto reload is enabled. Not recommended for production code. Be careful with side effects.')

    def exit_if_not_in_ipython(self):
        if not self.in_ipython():
            print('This script is intended to be run in IPython environment')
            sys.exit(1)

    # exit silently without rasing exception
    def exit_silent(self, message=""):
        class StopExecution(Exception):
            def _render_traceback_(self):
                pass
        if message:
            print(message)
        if self.in_ipython():
            raise StopExecution
        else:
            sys.exit(1)

    ############################################################################
    # time/date related functions
    ############################################################################
    def get_current_time(self):
        return time.time()

    def get_current_datetime(self):
        return datetime.now()

    def is_TimePassed(self, start_time, duration):
        return time.time() - start_time >= duration

    def wait_TimePassed(self, start_time, duration, tick_s=0.01):
        while not self.is_TimePassed(start_time, duration):
            time.sleep(0.01)

    def sleep(self, duration_s=1):
        t_start = time.time()
        self.wait_TimePassed(t_start, duration_s)

    def sleep_progress(self, duration):
        t_start = time.time()
        for n in range(duration):
            self.wait_TimePassed(t_start, n+1)
            # print(f"Time left: {duration - (n+1)} seconds") # TODO change to print progress
            self.print_time_left(n+1, duration)

    def get_last_day_of_month(self, year):
        return [datetime(year, month, calendar.monthrange(year, month)[1]) for month in range(1, 13)]

    def get_date(self, time_now, date_delim=''):
        return time_now.strftime(f'%Y{date_delim}%m{date_delim}%d')

    def get_timestamp(self, time_now=None, style=None, time_delim='', show_ms=False, ms_delim='', ms_digits=3):
        if time_now is None:
            time_now = self.get_current_datetime()
        style_map = {
            None: (time_delim, show_ms, ms_delim),
            0: (':', False, '.'),
            1: (':', True, '.'),
        }
        time_delim, show_ms, ms_delim = style_map.get(style, (time_delim, show_ms, ms_delim))
        if show_ms:
            milliseconds = round(time_now.microsecond / 1000)
            if milliseconds == 1000:
                time_now = time_now.replace(microsecond=0)
                milliseconds = 0
                time_now += timedelta(seconds=1) # Add 1 second if milliseconds is 1000
            milliseconds_str = str(milliseconds).zfill(ms_digits)
            return time_now.strftime(f'%H{time_delim}%M{time_delim}%S{ms_delim}{milliseconds_str}')
        return time_now.strftime(f'%H{time_delim}%M{time_delim}%S')

    def get_datestamp(self, time_now=None, style=None, date_delim=''):
        if time_now is None:
            time_now = self.get_current_datetime()
        style_map = {
            None: date_delim,
            0: '-',
        }
        date_delim = style_map.get(style, date_delim)
        return self.get_date(time_now, date_delim)

    def get_datetimestamp(self, time_now=None, style=None, date_delim='', date_time_delim='', time_delim='', show_ms=False, ms_delim='', ms_digits=3):
        if time_now is None:
            time_now = self.get_current_datetime()
        style_map = {
            None: (date_delim, date_time_delim, time_delim, show_ms, ms_delim),
            0: ('-', ' ', ':', False, '.'),
            1: ('-', ' ', ':', True, '.'),
        }
        date_delim, date_time_delim, time_delim, show_ms, ms_delim = style_map.get(style, (date_delim, date_time_delim, time_delim, show_ms, ms_delim))

        date_part = self.get_datestamp(time_now=time_now, style=style, date_delim=date_delim)
        time_part = self.get_timestamp(time_now=time_now, style=style, show_ms=show_ms, time_delim=time_delim, ms_delim=ms_delim, ms_digits=ms_digits)
        return f'{date_part}{date_time_delim}{time_part}'

    def extract_date_from_string(self, string):
        """
        Extracts the date information from a given string and returns it as a datetime object.
        The string is expected to contain a year, month, and optionally a day in the format YYYYMM or YYYYMMDD.
        """
        # pattern = r'\b(\d{4})(\d{2})(\d{2})?\b'
        pattern = r'\D((?:19|20)\d{2})(\d{2})(\d{2})?\D|\D((?:19|20)\d{2})H([12])\D?'
        match = re.search(pattern, string)
        if match:
            if match.group(4) and match.group(5):
                year = match.group(4)
                half = match.group(5)
                month = '01' if half == '1' else '07'
                day = '01'
            else:
                year, month, day = match.groups()[:3]
                if day is None:
                    day = '01'  # Default to the first day of the month if day is not provided
            try:
                date_obj = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
                return date_obj
            except ValueError:
                return None
        return None

    def get_datetime_difference(self, start_time, end_time, output_format='seconds'):
        if isinstance(start_time, datetime) and isinstance(end_time, datetime):
            diff = end_time - start_time
            if diff.total_seconds() < 0:
                return None
            if output_format == 'seconds':
                return diff.total_seconds()
            elif output_format == 'minutes':
                return diff.total_seconds() / 60
            elif output_format == 'hours':
                return diff.total_seconds() / 3600
            elif output_format == 'days':
                return diff.total_seconds() / (24 * 3600)
        return None

    class IntervalTimer:
        def __init__(self, interval_sec, eco_mode=True):
            # eco_mode:
            #   True - use less CPU but less accurate timing
            #   False - use more CPU but more accurate timing
            self.interval_sec = interval_sec
            self.eco_mode = eco_mode
            self.time_start = time.time()
            self.idx = 0

        def wait(self):
            while (time.time() - self.time_start) < (self.idx * self.interval_sec):
                if self.eco_mode:
                    time.sleep(0.01)
                else:
                    pass
            self.idx += 1

    ############################################################################
    # OS & hardware related functions
    ############################################################################
    def get_logon_username(self):
        if os.name == 'nt': # Windows
            return os.getlogin()
        else: # Unix/Linux
            try:
                import getpass
                return getpass.getuser()
            except:
                return None

    def get_hostname(self):
        return socket.gethostname()

    def os_info(self):
        return platform.platform()

    def get_serial_number(self):
        # return self.utils.run_powershell_command('wmic bios get serialnumber')
        return platform.node()

    def get_cpu_info(self):
        return platform.processor()

    def get_up_time_days(self):
        if os.name == 'nt': # Windows
            boot_time_output = self.run_powershell_command('Get-CimInstance Win32_OperatingSystem | select -ExpandProperty LastBootUpTime') # Get PC boot time by running PowerShell command
            boot_time = datetime.strptime(boot_time_output, '%A, %B %d, %Y %I:%M:%S %p') # Parse the boot time
        else: # Unix/Linux
            uptime_output = subprocess.check_output(['uptime', '-s']).decode().strip() # Get system boot time
            boot_time = datetime.strptime(uptime_output, '%Y-%m-%d %H:%M:%S') # Parse the boot time

        current_time = datetime.now() # Get the current time
        difference_in_seconds = (current_time - boot_time).total_seconds() # Calculate the difference in seconds
        difference_in_days = difference_in_seconds / (24 * 3600) # Convert the difference to days with decimals
        return difference_in_days

    ############################################################################
    # Python related
    ############################################################################
    # check if in python virtual environment
    def in_virtualenv(self):
        return hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)

    def get_python_exe_path(self):
        return os.path.realpath(sys.executable)

    def get_python_version(self, detailed=False):
        if detailed:
            return sys.version
        else:
            import platform
            return platform.python_version()

    def get_python_pkg_version(self, pkg_name):
        try:
            from importlib.metadata import version
            return version(pkg_name)
        except ImportError:
            return 'Package not found'

    # def get_kwargs_param(self, param_name, **kwargs):
    #     if param_name in kwargs:
    #         return kwargs[param_name]
    #     return None
    # Just use dict get:
    # kwargs.get(param_name, None)

    # append param to kwargs if not already set, or update value if overwrite argument is true
    def update_kwargs_param(self, kwargs, param_name, param_value, overwrite=False):
        if overwrite:
            kwargs[param_name] = param_value
        else:
            kwargs.setdefault(param_name, param_value)
        return kwargs

    ############################################################################
    # Git/Github related
    ############################################################################
    def get_git_commit_hash(self):
        if not self.module_exists('python-git-info'):
            return
        import gitinfo
        try:
            return gitinfo.get_git_info()['commit']
        except:
            return None

    # fetch the latest release files of a github repo
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
        # release_info = self.get_github_latest_release(repo_owner, repo_name)
        urls = []
        for asset in release_info['assets']:
            # print(asset)
            if filter_value in asset[filter_name]:
                # print(asset[filter_name])
                urls.append(asset['browser_download_url'])
        return urls

    ############################################################################
    # stdout related
    ############################################################################
    def print_same_line(self, msg):
        print('\r\033[K'+msg, end='')

    def print_progress(self, n, total):
        progress = (n+1)/total*100
        if progress >= 100:
            progress = 100
        self.print_same_line("Progress: "+"{:.1f}".format(progress)+ " %")
        if progress == 100:
            print('\r')

    def print_time_left(self, n, total):
        self.print_same_line(f'Waiting for {total}s... ({total-n}s)')
        if n >= total:
            print('\r')

    ############################################################################
    # strings related
    ############################################################################
    def remove_non_ascii(self, a_str):
        ascii_chars = set(string.printable)
        return ''.join(x for x in a_str if x in ascii_chars)

    def contains_non_ascii(self, string):
        return any(ord(char) > 127 for char in string)

    def contains_digits(self, string):
        return any(char.isdigit() for char in string)

    def contains_uppercase(self, string):
        return any(x.isupper() for x in string)

    def contains_lowercase(self, string):
        return any(x.islower() for x in string)

    def pad_char(self, text, char='-', length=80):
        if len(text) <= length-4:
            return f' {text} '.center(length, char)
        return text

    # convert string to float, return None if fail to convert
    def str2float(self, val):
        try:
            return float(val)
        except ValueError:
            return None

    # convert string to int, return None if fail to convert, also accept string with decimals
    def str2int(self, val):
        try:
            return int(float(val))
        except ValueError:
            return None

    # natural sort key for sorting strings with numbers
    def natural_sort_key(self, text):
        return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', text)]

    def capitalize_title(self, title):
        exceptions = {'of', 'the', 'and', 'in', 'on', 'at', 'to', 'for', 'with', 'a', 'an'}
        words = title.split()
        capitalized_words = [word.capitalize() if word.lower() not in exceptions else word.lower() for word in words]
        # Ensure the first word is always capitalized
        if capitalized_words:
            capitalized_words[0] = capitalized_words[0].capitalize()
        return ' '.join(capitalized_words)

    # Generates an HTML anchor tag.
    def generate_html_link(self, text, new_window=True):
        if new_window:
            return '<a target="_blank" href="{}">{}</a>'.format(text, text)
        else:
            return '<a href="{}">{}</a>'.format(text, text)

    def extract_lines_between_strings(self, file_path, string1, string2, include_matching_string_line=False):
        lines_between = []
        inside_range = False

        with open(file_path, 'r') as file:
            for line in file:
                if string1 in line:
                    inside_range = True
                    if include_matching_string_line:
                        lines_between.append(line)
                    continue
                if string2 in line and inside_range:
                    if include_matching_string_line:
                        lines_between.append(line)
                    break
                if inside_range:
                    lines_between.append(line)

        return lines_between

    ############################################################################
    # list, dict related
    ############################################################################
    def get_unique_elements(self, input_list, sorted=True):
        unique_list = list(set(input_list))
        if sorted:
            unique_list.sort()
        return unique_list

    def list_to_csv(self, data, delim=','):
        # return delim.join([str(x) for x in data])
        return delim.join(map(str, data))

    def dict_lookup(self, dict, lookup_key, lookup_value, return_key):
        for d in dict:
            if d.get(lookup_key) == lookup_value:
                return d.get(return_key)
        return None

    ############################################################################
    # data, dataframe related
    ############################################################################
    # Check for duplicate column names and rename them to ensure uniqueness
    def unique_names(self, names):
        names = list(names)
        seen = {}
        for i, col in enumerate(names):
            if col in seen:
                seen[col] += 1
                names[i] = f"{col}_{seen[col]}"
            else:
                seen[col] = 0
        return names

    def array_to_df(self, array, has_header=True):
        if has_header:
            df = pd.DataFrame(array[1:], columns=array[0])
        else:
            df = pd.DataFrame(array)
        return df

    def df_unique_columns(self, df):
        # df = df_orig.copy()
        unique_header = self.unique_names(df.columns)
        # df.rename(columns=dict(zip(df.columns, unique_header)), inplace=True)
        df.columns = unique_header
        return df

    def df_to_numeric(self, df):
        # Create new header with unique column names
        df = self.df_unique_columns(df)

        # Convert columns to numeric types where possible
        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col])
            except (TypeError, ValueError) as e:
                print(f"Error converting column '{col}' to numeric: {e}")
        return df

    ############################################################################
    # Web related
    ############################################################################
    class URLExtractor:
        def __init__(self, base_url, ext):
            self.base_url = base_url
            self.ext = ext
            self.urls = []
            self.html_parser = HTMLParser()
            self.html_parser.handle_starttag = self.handle_starttag

        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                for attr in attrs:
                    if attr[0] == 'href' and attr[1].endswith(self.ext):
                        self.urls.append(urllib.parse.urljoin(self.base_url, attr[1]))

        def feed(self, data):
            self.html_parser.feed(data)

    def fetch_content(self, url):
        with urllib.request.urlopen(url) as response:
            return response.read().decode()

    def extract_urls(self, url, ext='', params={}):
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}" if params else url
        response = self.fetch_content(full_url)
        base_url = "{0.scheme}://{0.netloc}/".format(urllib.parse.urlsplit(url))
        parser = self.URLExtractor(base_url, ext)
        parser.feed(response)
        return parser.urls

    def list_files_http(self, url, recursive=False, ignore_first_link=False, ext=''):
        filelist = []
        dirlist = []
        links = self.extract_urls(url)
        if ignore_first_link:
            links = links[1:]
        for link in links:
            if link.endswith('/'):
                dirlist.append(link)
                if recursive:
                    filelist_child, dirlist_child = self.list_files_http(url=link, recursive=True, ignore_first_link=ignore_first_link, ext=ext)
                    filelist.extend(filelist_child)
                    dirlist.extend(dirlist_child)
            elif link.endswith(ext):
                filelist.append(link)
        return filelist, dirlist

    def download_file(self, url, download_dir='.', overwrite=False):
        try:
            filename = urllib.parse.unquote(url.split('/')[-1])
            file_path = os.path.join(download_dir, filename)
            if os.path.exists(file_path) and not overwrite:
                print(f"File '{filename}' already exists. Skipping download.")
                return
            urllib.request.urlretrieve(url, file_path)
            print(f"Downloaded '{filename}'")
        except Exception as e:
            print(f"Error downloading {url}: {e}")

    def download_files(self, urls, download_dir='.', overwrite=False, parallel_download=True, max_workers=5):
        # Create download directory if not exists
        self.create_directory(download_dir)

        if not parallel_download:
            for url in urls:
                self.download_file(url, download_dir, overwrite)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for url in urls:
                    executor.submit(self.download_file, url, download_dir, overwrite)

    def post_to_teams(self, webhook_url, text):
        text_conditioned_for_teams = str(text).replace('\n', '\n\n')
        jsonData = {
            "text": text_conditioned_for_teams
        }
        return self.send_webhook(webhook_url, jsonData)

    def send_webhook(self, webhook_url, json_data):
        if not self.module_exists('requests'):
            return
        import requests

        response = requests.post(webhook_url, json=json_data, verify=False)
        if not (response.status_code==201 or response.status_code==201 or response.status_code==202):
            print(f'{response} - Please check')
        return response

    ############################################################################
    # Network related
    ############################################################################
    def get_public_ip(self):
        if not self.module_exists('requests'):
            return
        import requests
        response = requests.get('https://api.ipify.org?format=json')
        data = response.json()
        ip = data['ip']
        return ip

    def get_location_from_ip(self, ip):
        if not self.module_exists('requests'):
            return
        import requests
        response = requests.get('https://ipinfo.io/'+ip+'/json')
        data = response.json()
        city = data['city']
        country = data['country']
        return city, country

    ############################################################################
    # Files/Directories related
    ############################################################################
    def create_directory(self, path):
        if os.path.exists(path):
            if os.path.isfile(path):
                raise FileExistsError(f"A file with the name '{path}' already exists.")
        os.makedirs(path, exist_ok=True)

    def remove_directory(self, path, force=False):
        if os.path.exists(path):
            if os.path.isfile(path):
                raise FileNotFoundError(f"Cannot remove '{path}' because it is a file.")
            if force:
                self.shutil.rmtree(path)
            else:
                os.rmdir(path)
        else:
            raise FileNotFoundError(f"Directory '{path}' does not exist.")

    # def create_file(self, path, content=None):
    #     if os.path.exists(path):
    #         if os.path.isdir(path):
    #             raise FileExistsError(f"A directory with the name '{path}' already exists.")
    #     with open(path, 'w') as file:
    #         if content is not None:
    #             file.write(content)

    def remove_file(self, path):
        if os.path.exists(path):
            if os.path.isdir(path):
                raise FileNotFoundError(f"Cannot remove '{path}' because it is a directory.")
            os.remove(path)
        else:
            raise FileNotFoundError(f"File '{path}' does not exist.")

    # get file content
    def read_file(self, path):
        with open(path, 'r') as file:
            return file.read()

    # write content to file
    def write_file(self, path, content, overwrite=False):
        mode = 'w' if overwrite else 'a'
        with open(path, mode) as file:
            file.write(content)

    # list files in a directory, with optional filters
    def list_files(self, directory, ext='', recursive=False):
        filelist = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(ext.lower()):
                    filelist.append(os.path.join(root, file))
            if not recursive:
                break

        # # Sort the filelist by modification date and time
        # filelist.sort(key=lambda x: os.path.getmtime(x))

        return filelist

    ############################################################################
    # Binary data related
    ############################################################################
    data_type_properties = {
        'uint8': (0, 255, int, 1),
        'uint16': (0, 65535, int, 2),
        'uint32': (0, 4294967295, int, 4),
        'int8': (-128, 127, int, 1),
        'int16': (-32768, 32767, int, 2),
        'int32': (-2147483648, 2147483647, int, 4),
        'float': (None, None, float, 4)
    }

    def is_data_type_valid(self, data_type, value):
        if data_type not in self.data_type_properties:
            return False
        min_val, max_val, expected_type, _ = self.data_type_properties[data_type]
        if not isinstance(value, expected_type):
            return False
        if min_val is not None and (value < min_val or value > max_val):
            return False
        return True

    def get_data_type_length(self, data_type):
        return self.data_type_properties.get(data_type, (None, None, None, 0))[3]

    def _get_format(self, data_type, endian):
        formats = {
            'double': 'd',
            'float': 'f',
            'uint32': 'I',
            'int32': 'i',
            'uint16': 'H',
            'int16': 'h',
            'uint8': 'B'
        }
        return f'>{formats[data_type]}' if endian == 'BE' else f'<{formats[data_type]}'

    def _check_length(self, num_bytes, expected_length):
        if len(num_bytes) != expected_length:
            raise ValueError(f'Requires a buffer of {expected_length} bytes, buffer is {len(num_bytes)} bytes long.')

    def _generate_convertion_functions(self):
        data_types = {
            'double': 8,
            'float': 4,
            'uint32': 4,
            'int32': 4,
            'uint16': 2,
            'int16': 2,
            'uint8': 1
        }

        def _create_to_bytes_function(data_type):
            def to_bytes(num, endian='BE'):
                return struct.pack(self._get_format(data_type, endian), num)
            return to_bytes

        def _create_from_bytes_function(data_type, length):
            def from_bytes(num_bytes, endian='BE'):
                self._check_length(num_bytes, length)
                return struct.unpack(self._get_format(data_type, endian), num_bytes)[0]
            return from_bytes

        for data_type, length in data_types.items():
            setattr(self, f'{data_type}_to_bytes', _create_to_bytes_function(data_type))
            setattr(self, f'bytes_to_{data_type}', _create_from_bytes_function(data_type, length))

        # list of the functions created:
        # double_to_bytes, bytes_to_double
        # float_to_bytes, bytes_to_float
        # uint32_to_bytes, bytes_to_uint32
        # int32_to_bytes, bytes_to_int32
        # uint16_to_bytes, bytes_to_uint16
        # int16_to_bytes, bytes_to_int16
        # uint8_to_bytes, bytes_to_uint8

    # Convert float to binary32 (single precision) format (caution - lose precision)
    def float_to_single(self, x):
        return struct.unpack('f', struct.pack('f', x))[0]

    # Convert float to binary16 (half precision) format (caution - lose precision)
    def float_to_half(self, x):
        return struct.unpack('e', struct.pack('e', x))[0]

    def get_bit(self, value, bit_index):
        return value & (1 << bit_index)

    def get_normalized_bit(self, value, bit_index):
        return (value >> bit_index) & 1

    def set_bit(self, value, bit_index):
        return value | (1 << bit_index)

    def clear_bit(self, value, bit_index):
        return value & ~(1 << bit_index)

    def toggle_bit(self, value, bit_index):
        return value ^ (1 << bit_index)

    def bytes_to_hex_str(self, bytes, prefix='', delim=''):
        return delim.join([f'{prefix}{x:02X}' for x in bytes])

    def hex_str_to_bytes(self, hex_string, delim=''):
        hex_string = hex_string.replace(delim, '')
        return bytes.fromhex(hex_string)

    def string_to_bytes(self, string):
        return string.encode()

    def bytes_to_string(self, bytes):
        return bytes.decode()

    def crc32_jamcrc(self,data_bytes):
        import zlib
        crc32 = zlib.crc32(data_bytes)
        crc32_jamcrc = 2**32-1 - crc32
        return self.uint32_to_bytes(crc32_jamcrc, endian='LE')

    def XOR_checksum(self,bytes):
        checksum = 0
        for byte in bytes:
            checksum ^= byte
        return checksum

    def float_to_str_sf(self, num, sf):
        format_string = "{:." + str(sf) + "g}"
        return format_string.format(num)

    ############################################################################
    # Image related
    ############################################################################
    def img_to_base64(self, img_path):
        with open(img_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()

    def display_img_from_base64(self, img_base64):
        return HTML(f'<img src="data:image/png;base64,{img_base64}">')

    ############################################################################
    # Threading related
    ############################################################################
    # Stoppable thread
    class StoppableThread(threading.Thread):
        """Thread class with a stop() method. The thread itself has to check
        regularly for the stopped() condition."""
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._stop_event = threading.Event()

        def stop(self):
            self._stop_event.set()

        def stop_flag(self):
            return self._stop_event.is_set()

    ############################################################################
    # Test related
    ############################################################################
    def print_test_environment(self, pkg_list=[]):
        print(self.pad_char('Test Environment'))
        print(
            f'PC Info: '
            f'Name={self.get_hostname()}, '
            f'SN={self.get_serial_number()}, '
            f'OS={self.os_info()}, '
            f'Up Time={self.get_up_time_days():.1f}days'
            )
        python_version_info = f'Python={self.get_python_version()}'
        jupyterlab_info = f', Jupyterlab={self.get_python_pkg_version("jupyterlab")}' if self.in_ipython() else ''
        print(f'Python Info: {python_version_info + jupyterlab_info}')

        pkg_versions = ', '.join([f'{pkg}={self.get_python_pkg_version(pkg)}' for pkg in pkg_list])
        if pkg_versions:
            print(f'Packages Info: {pkg_versions}')

class TestClass(UtilityFunctions):
    def __init__(self, test_name):
        if not test_name:
            test_name = f'Test_{self.get_datetimestamp(date_time_delim="_")}'
        self.test_name = test_name

    def exit_if_up_time_exceeds(self, pc_up_time_days):
        up_time = self.get_up_time_days()
        if up_time >= pc_up_time_days:
            print('Test PC has been running for too long. Please restart the PC before running the test.')
            sys.exit(1)

    def print_test_info(self, print_test_env=True, print_git_info=True, pkg_list=[]):
        if print_test_env:
            self.print_test_environment(pkg_list=pkg_list)
        if print_git_info:
            git_commit_hash = self.get_git_commit_hash()
            if git_commit_hash:
                print(f'Git Commit Hash: {git_commit_hash}')
        print(f'Test Name: {self.test_name}')
