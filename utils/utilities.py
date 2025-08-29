import sys
import os
import subprocess
import platform
from importlib.metadata import PackageNotFoundError, version
import string
import re
import struct
import time
from enum import Enum
from datetime import datetime, timedelta
import calendar
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    _sys_exit_overridden = False # Class-level flag to track if the message has been shown

    def __init__(self):
        # binary data utils init
        self._generate_conversion_functions()
        self.override_sys_exit_in_ipython()
        self.ipython = get_ipython() if self.in_ipython() else None

        # Progress line tracking
        self._progress_line_active = False

    def do_nothing(self, *args, **kwargs):
        pass

    def exit_if_module_missing(self, module_name):
        if not self.module_exists(module_name):
            sys.exit(1)

    def run_powershell_command(self, command):
        process=subprocess.Popen(["powershell","& {" + command+ "}"], stdout=subprocess.PIPE)
        stdout_value = process.communicate()[0].decode("utf-8", errors='replace').strip()
        return stdout_value

    def wait_user_enter_key(self, msg=None):
        input(msg or 'Press enter to continue...')

    # get user input int/float/str, display 'default_val' if show_default_value is True
    # if 'default_val' is provided and user entered blank, 'default_val' will be returned (default_val must not be None, can be '')
    # if 'allow_empty' is True, user can enter blank, function will return default_val (default_val can be anything including None)
    def get_user_input(self, msg, data_type, default_val=None, show_default_value=True, allow_empty=False):
        default_string = ''
        if default_val != None and show_default_value:
            default_string = f', default={str(default_val)}'
        user_input = input(f'{msg} ({data_type.__name__}{default_string}): ')

        # str data type
        if data_type == str:
            if user_input:
                return user_input
            if default_val is not None:
                return default_val
            if not allow_empty:
                print('Invalid input, expected non-empty input')
            return None

        if data_type == bool:
            if user_input.lower() in ['true', '1', 'yes']:
                return True
            elif user_input.lower() in ['false', '0', 'no']:
                return False
            if default_val is not None:
                return default_val
            if not allow_empty:
                print('Invalid input, expected boolean value (true/false, 1/0, yes/no)')
            return None

        # other data types
        val = default_val if not user_input else user_input

        if val is None:
            if not allow_empty:
                print('Invalid input, expected non-empty input')
            return None

        try:
            return data_type(val)
        except (ValueError, TypeError):
            print(f'Invalid input, expected {data_type.__name__}')
            return None

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
        if not self.in_ipython(print_warning=True):
            return None
        self.ipython_run_magic_command('reload_ext', 'autoreload')
        self.ipython_run_magic_command('autoreload', '2')
        if print_warning:
            print('Auto reload is enabled. Not recommended for production code. Be careful with side effects.')
        return True

    def ipython_reset_namespace(self):
        if not self.in_ipython(print_warning=True):
            return None
        self.ipython_run_magic_command('reset', '-f')
        print('IPython namespace is reset.')
        return True

    def exit_if_not_in_ipython(self):
        if not self.in_ipython():
            print('This script is intended to be run in IPython environment')
            sys.exit(1)

    # exit silently without rasing exception
    def exit_silent(self, message=""):
        class StopExecution(Exception):
            def _render_traceback_(self):
                pass
        if self.in_ipython():
            if message:
                print(message)
            raise StopExecution
        else:
            sys.exit(message)

    def override_sys_exit_in_ipython(self):
        if self.in_ipython() and not UtilityFunctions._sys_exit_overridden:
            sys.exit = self.exit_silent
            print('sys.exit() is overridden to exit silently in IPython environment.')
            UtilityFunctions._sys_exit_overridden = True

    def display_filelink(self, link, prefix=''):
        display(FileLink(link, result_html_prefix=prefix))

    def clear_output(self):
        if self.in_ipython():
            clear_output()

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
            None: (time_delim, show_ms, ms_delim), # 105813
            0: (':', False, '.'), # 10:58:13
            1: (':', True, '.'),  # 10:58:13.123
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
            None: date_delim, # 20250514
            0: '-', # 2023-10-01
        }
        date_delim = style_map.get(style, date_delim)
        return self.get_date(time_now, date_delim)

    def get_datetimestamp(self, time_now=None, style=None, date_delim='', date_time_delim='', time_delim='', show_ms=False, ms_delim='', ms_digits=3):
        if time_now is None:
            time_now = self.get_current_datetime()
        style_map = {
            None: (date_delim, date_time_delim, time_delim, show_ms, ms_delim), # 20250514110003
            0: ('-', ' ', ':', False, '.'), # 2025-05-14 10:59:34
            1: ('-', ' ', ':', True, '.'),  # 2025-05-14 10:59:34.123
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

    # Usage:
    # timer = IntervalTimer(1)  # 1 second interval
    # while True:
    #     # user codes
    #     timer.wait()  # Wait for the next interval
    class IntervalTimer:
        def __init__(self, interval_sec, eco_mode=True):
            # eco_mode:
            #   True - use less CPU but less accurate timing
            #   False - use more CPU but more accurate timing
            self.interval_sec = interval_sec
            self.eco_mode = eco_mode
            self.time_start = time.time()
            self.idx = 1

        def wait(self):
            while (time.time() - self.time_start) < (self.idx * self.interval_sec):
                if self.eco_mode:
                    time.sleep(0.01)
                else:
                    pass
            self.idx += 1

    # Usage:
    # timer = ThreadedTimer(5.0)  # 5 second timeout
    # timer.start()
    # # ... do work ...
    # if timer.is_expired():
    #     print("Timer expired!")
    #     timer.clear_expired()
    # timer.stop()
    class ThreadedTimer(threading.Thread):
        def __init__(self, timeout_sec, repeat=False, callback=None, auto_start=True, auto_clear_expired=True):
            super().__init__(daemon=True)
            self.timeout_sec = timeout_sec
            self.repeat = repeat  # If True, timer fires repeatedly like an interrupt
            self.callback = callback  # Optional callback function to execute on timeout
            self._expired = threading.Event()
            self._stop_event = threading.Event()
            self._reset_event = threading.Event()
            self._running = False
            self._fire_count = 0
            if auto_start:
                self.start()
            self._auto_clear_expired = auto_clear_expired

        def run(self):
            self._running = True
            while not self._stop_event.is_set():
                # Wait for timeout or stop/reset event
                if self._stop_event.wait(self.timeout_sec):
                    break  # Stop event was set

                # Check if reset was requested during wait
                if self._reset_event.is_set():
                    self._reset_event.clear()
                    continue  # Restart the timeout

                # Timeout occurred
                if not self._stop_event.is_set():
                    self._fire_count += 1
                    self._expired.set()

                    # Execute callback if provided (like interrupt service routine)
                    if self.callback:
                        try:
                            self.callback()
                        except Exception as e:
                            print(f"Timer callback error: {e}")

                    # If not repeating, exit after first timeout
                    if not self.repeat:
                        break

                    # For repeating timer, continue the loop
                    # The expired flag stays set until manually cleared

            self._running = False

        def start(self):
            if not self._running and not self.is_alive():
                super().start()

        def stop(self):
            self._stop_event.set()
            if self.is_alive():
                self.join(timeout=1.0)

        def reset(self):
            """Reset the timer - restart the countdown"""
            self._expired.clear()
            self._reset_event.set()
            self._fire_count = 0

        def is_expired(self):
            """Check if timer has expired and clear the expired flag"""
            expired = self._expired.is_set()
            if expired and self._auto_clear_expired:
                self._expired.clear()
            return expired

        def clear_expired(self):
            """Clear the expired flag without restarting the timer"""
            self._expired.clear()

        def is_running(self):
            """Check if timer thread is running"""
            return self._running

        def fire_count(self):
            """Get number of times timer has fired"""
            return self._fire_count

        def time_remaining(self):
            """Get approximate time remaining (not precise due to threading)"""
            if not self._running or self.is_expired():
                return 0
            return max(0, self.timeout_sec)

    def seconds_to_time(self, seconds):
        """Convert seconds to a time tuple (hours, minutes, seconds)"""
        hr = seconds // 3600
        min = (seconds % 3600) // 60
        sec = seconds % 60
        return hr, min, sec

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
            uptime_output = subprocess.check_output(['uptime', '-s']).decode(errors='replace').strip() # Get system boot time
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
        self._progress_line_active = True

    def print_same_line_end(self):
        if self._progress_line_active:
            print()
            self._progress_line_active = False

    # automatic add 1 to simplify calling at the and of for loop
    # to show 0%, pass n=-1
    def print_progress(self, n, total):
        progress = (n+1)/total*100
        if progress >= 100:
            progress = 100
        self.print_same_line("Progress: "+"{:.1f}".format(progress)+ " %")
        if progress == 100:
            self.print_same_line_end()

    # print private method to replace print function, and perform additional actions
    def print(self, *args, **kwargs):
        """
        Custom print function that can be extended to perform additional actions.
        For example, it can be used to log messages or display them in a specific format.
        """
        self.print_same_line_end()
        print(*args, **kwargs)

    def print_time_left(self, n, total):
        self.print_same_line(f'Waiting for {total}s... ({total-n}s)')
        if n >= total:
            print('\r')

    ############################################################################
    # strings related
    ############################################################################
    def remove_non_printable_ascii(self, a_str):
        ascii_chars = set(string.printable)
        return ''.join(x for x in a_str if x in ascii_chars)

    def contains_non_printable_ascii(self, a_str):
        # return any(ord(char) > 127 for char in string)
        return any(char not in string.printable for char in a_str)

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

    def pad_left(self, text, char=' ', length=80):
        return text.rjust(length, char)

    def pad_right(self, text, char=' ', length=80):
        return text.ljust(length, char)

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
    # Usage example:
    #   sorted_list = sorted(unsorted_list, key=natural_sort_key)
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

        def extract_lines(file):
            nonlocal inside_range

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

        # check if given path is http url
        if file_path.startswith('https://') or file_path.startswith('http://'):
            data = urllib.request.urlopen(file_path)
            # read all lines from the response
            lines = data.readlines()
            # lines will be a list of bytes, decode to str
            lines = [line.decode('utf-8') for line in lines]
            # remove lines ending, can be '\n' or '\r\n'
            lines = [line.rstrip('\n\r') for line in lines]
            extract_lines(lines)
        else:
            with open(file_path, 'r') as file:
                extract_lines(file)

        return lines_between

    ############################################################################
    # list, dict related
    ############################################################################
    def get_unique_elements(self, input_list, sorted=True):
        unique_list = list(set(input_list))
        if sorted:
            unique_list.sort()
        return unique_list

    def list_to_csv(self, data, delim=',', na_str='nan'):
        # return delim.join([str(x) for x in data])
        # return delim.join(map(str, data))
        if na_str == 'nan':
            return delim.join([na_str if x is None else str(x) for x in data])
        return delim.join([na_str if (x is None or str(x).lower() == 'nan') else str(x) for x in data])

    def dict_reverse_lookup(self, dict, lookup_value):
        """
        Reverse lookup in a dictionary to find the first key that matches the given value.
        Returns the key if found, otherwise returns None.
        :param dict: Dictionary to search in.
        :param lookup_value: Value to look up in the dictionary.
        :return: The key corresponding to the lookup_value if found, otherwise None.
        """
        for key, value in dict.items():
            if value == lookup_value:
                return key
        return None

        # # Using list comprehension
        # keys = [key for key, value in dict.items() if value == lookup_value]
        # if keys:
        #     return keys[0]
        # return None

    def dict_list_lookup(self, dict_list, lookup_key, lookup_value, return_key):
        """
        Look up a value in a list of dictionaries by a specific key and return another key's value.
        :param dict_list: List of dictionaries to search in.
        :param lookup_key: Key to look up in each dictionary.
        :param lookup_value: Value to match for the lookup key.
        :param return_key: Key whose value to return if the lookup is successful.
        :return: The value of return_key if found, otherwise None.
        """
        for d in dict_list:
            if d.get(lookup_key) == lookup_value:
                return d.get(return_key)
        return None

    # given an list, find the smallest value that is greater than or equal to the given value
    # [1, 2, 3, 4, 5], value=3.5, return [4]
    # [1, 2, 3, 4, 5], value=0, return [1]
    # [1, 2, 3, 4, 5], value=4, return [4]
    # [1, 2, 3, 4, 5], value=6, return None
    def find_smallest_gte(self, value, values, use_bisect=False):
        """
        Find the smallest value in a list that is greater than or equal to the given value.
        :param value: The value to compare against.
        :param values: A list of values to search in.
        :return: The smallest value >= value, or None if not found.
        """
        sorted_values = sorted(values)
        if use_bisect:
            import bisect
            index = bisect.bisect_left(sorted_values, value)
            if index < len(sorted_values):
                return sorted_values[index]
            return None
        else:
            # Linear search for simplicity
            for v in sorted_values:
                print(v, value)
                if v >= value:
                    return v
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

    def array_to_df(self, array, has_header=True, column_names=None):
        if has_header:
            # ignore given column_names if has_header is True
            df = pd.DataFrame(array[1:], columns=array[0])
        else:
            if column_names is not None:
                if len(column_names) != len(array[0]):
                    raise ValueError("Column names length does not match array length.")
                df = pd.DataFrame(array, columns=column_names)
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
            return response.read().decode(errors='replace')

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

    def download_file(self, url, download_dir='.', overwrite=False, show_abs_path=True, suppress_output=False):
        """Download file and return status: 'downloaded', 'skipped', or 'failed'"""
        try:
            filename = urllib.parse.unquote(url.split('/')[-1])
            file_path = os.path.join(download_dir, filename)

            if os.path.exists(file_path) and not overwrite:
                print(f"File '{os.path.abspath(file_path) if show_abs_path else os.path.basename(file_path)}' already exists. Skipping download.") if not suppress_output else None
                return 'skipped'

            urllib.request.urlretrieve(url, file_path)
            print(f"Downloaded '{os.path.abspath(file_path) if show_abs_path else os.path.basename(file_path)}'") if not suppress_output else None
            return 'downloaded'
        except Exception as e:
            self.print(f"Error downloading {urllib.parse.unquote(url)}: {e}")
            return 'failed'

    def download_files(self, urls, download_dir='.', overwrite=False, parallel_download=True, max_workers=5, output_type='progress', auto_retry_count=1):
        # output_type
        #   'progress' - print progress in the same line
        #   'full' - print full output for each download, does not print progress
        #   'quiet' or any - suppress all output except errors
        suppress_output = output_type == 'quiet' or output_type != 'full'

        def get_summary_line():
            return f'Total: {len(urls)}, Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed}'

        self.create_directory(download_dir) # Create download directory if not exists
        print(f"Download directory: {os.path.abspath(download_dir)}")

        retries = 0

        while retries < auto_retry_count+1:
            downloaded = 0; skipped = 0; failed = 0

            if retries:
                print(f'Retrying download... ({retries}/{auto_retry_count})') if output_type != 'quiet' else None

            if not parallel_download:
                for url in urls:
                    # self.download_file(url, download_dir, overwrite)
                    result = self.download_file(url, download_dir, overwrite, show_abs_path=False, suppress_output=suppress_output)
                    if result == 'downloaded':
                        downloaded += 1
                    elif result == 'skipped':
                        skipped += 1
                    else:
                        failed += 1
                    self.print_same_line(f'{get_summary_line()}') if output_type=='progress' else None
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # for url in urls:
                    #     executor.submit(self.download_file, url, download_dir, overwrite)
                    future_to_url = {executor.submit(self.download_file, url, download_dir, overwrite, show_abs_path=False, suppress_output=suppress_output): url for url in urls}

                    # Process completed downloads
                    for future in as_completed(future_to_url):
                        url = future_to_url[future]
                        result = future.result()
                        if result == 'downloaded':
                            downloaded += 1
                        elif result == 'skipped':
                            skipped += 1
                        else:
                            failed += 1
                        self.print_same_line(f'{get_summary_line()}') if output_type=='progress' else None
            if failed == 0:
                break
            if retries == auto_retry_count:
                print(f'Failed to download {failed} files after {retries} retries. Stopping.') if output_type != 'quiet' else None
                break
            retries += 1
            self.print_same_line_end()

        self.print_same_line_end() if output_type=='progress' else print(f'{get_summary_line()}') # print new line after progress output, or print final summary

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
                shutil.rmtree(path)
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
    def read_file(self, path, binary=False):
        mode = 'rb' if binary else 'r'
        with open(path, mode) as file:
            return file.read()

    # write content to file
    def write_file(self, path, content, overwrite=False, auto_create_dir=True):
        mode = 'w' if overwrite else 'a'

        # use binary switch if content is bytes
        if isinstance(content, bytes):
            mode = mode + 'b'

        # create directory if not exists
        if auto_create_dir:
            self.create_directory(os.path.dirname(path))

        with open(path, mode) as file:
            file.write(content)

    # list files in a directory, with optional filters
    def list_files(self, directory='.', ext='', recursive=False):
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

    def calculate_file_hash(self, file_path, hash_algorithm='md5'):
        import hashlib

        hash_func = getattr(hashlib, hash_algorithm, None)
        if hash_func is None:
            raise ValueError(f"Unsupported hash algorithm: {hash_algorithm}")

        hasher = hash_func()
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

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
        'float': (None, None, float, 4),
        'bytearray': (None, None, bytearray, 4),
        'bytes': (None, None, bytes, 1),
        'string': (None, None, str, 1),
    }

    def is_data_type_valid(self, data_type, value):
        if data_type not in self.data_type_properties:
            return False
        min_val, max_val, expected_type, _ = self.data_type_properties[data_type]
        if not isinstance(value, expected_type):
            return False

        # Only compare numeric types
        if not (expected_type==bytes or expected_type==bytearray or expected_type==str):
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

    def _generate_conversion_functions(self):
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
        if bytes is None:
            return ''
        return delim.join([f'{prefix}{x:02X}' for x in bytes])

    def hex_str_to_bytes(self, hex_string, delim=''):
        hex_string = hex_string.replace(delim, '')
        # replace '0x' and '0X' with ''
        hex_string = hex_string.replace('0x', '').replace('0X', '')
        return bytes.fromhex(hex_string)

    def string_to_bytes(self, string):
        return string.encode()

    def bytes_to_string(self, bytes):
        return bytes.decode(errors='replace')

    def dec_to_hex_str(self, dec, prefix='', delim='', pad=True, byte_size=None):
        # 459 => 1CB (without prefix, no delim, no padding)
        # 459 => 0x1CB (with prefix, no delim, no padding)
        # 459 => 1,CB (without prefix, with delim ",", no padding)
        # 459 => 0x1,0xCB (with prefix, with delim ",", no padding)

        # 459 => 01CB (without prefix, no delim, padding=2)
        # 459 => 0x01CB (with prefix, no delim, padding=2)
        # 459 => 01,CB (without prefix, with delim ",", padding=2)
        # 459 => 0x01,0xCB (with prefix, with delim ",", padding=2)

        # convert
        if byte_size:
            hex_str = f'{dec:0{byte_size*2}X}'

        # add padding
        if pad and len(hex_str) % 2:
            hex_str = '0' + hex_str

        # add delim
        if delim:
            hex_str = delim.join([hex_str[max(i-2, 0):i] for i in range(len(hex_str), 0, -2)][::-1])

        # add prefix
        if prefix:
            if delim: # add prefix to each delimited part
                hex_str = delim.join([f'{prefix}{x}' for x in hex_str.split(delim)])
            else: # add prefix once to the whole string
                hex_str = f'{prefix}{hex_str}'
        return hex_str

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

    def is_integer(self, s):
        try:
            float_val = float(s)
            return float_val.is_integer()
        except ValueError:
            return False

    def is_float(self, s):
        try:
            float(s)
            return True
        except ValueError:
            return False

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
    # Demo related
    ############################################################################
    # print menu by going through the menu_dict. Split into multiple columns if specifed
    # when combining columns, the first column will list the first half of the menu_dict, next column will list the second half
    # if the number of entries is odd, the first column will have one more entry than the second column
    # At least 2 spaces will be added between the columns
    # The key and name will be separated by a dot and a space
    # If the maximum length of a line is more than 80, fall back to single column
    # Example menu_dict, 4 columns, 80 max width:
    # menu_dict = [
    #     {'key': 'a', 'name': 'Beep'},
    #     {'key': 'b', 'name': 'Get Last Error'},
    #     {'key': 'c', 'name': 'Set Mode'},
    #     {'key': 'd', 'name': 'Get Mode'},
    #     {'key': 'e', 'name': 'Read Voltage DC'},
    #     {'key': 'f', 'name': 'Read Current DC'},
    # ]
    # Will be shown as:
    # a. Beep             c. Set Mode   e. Read Voltage DC   f. Read Current DC
    # b. Get Last Error   d. Get Mode
    def show_demo_menu(self, menu_dict, max_columns=8, max_width=80):
        number_len = 4
        col_widths = []
        columns = []
        col_start = 0

        for i in range(max_columns):
            col_end = col_start + len(menu_dict) // max_columns + (1 if i < len(menu_dict) % max_columns else 0)
            col = menu_dict[col_start:col_end]
            col_width = max(len(entry['name']) for entry in col) + number_len if col else 0
            col_widths.append(col_width)
            columns.append(col)
            col_start = col_end

        total_width = sum(col_widths) + 2 * (max_columns - 1)

        while total_width > max_width and max_columns > 1:
            max_columns -= 1
            col_widths = []
            columns = []
            col_start = 0

            for i in range(max_columns):
                col_end = col_start + len(menu_dict) // max_columns + (1 if i < len(menu_dict) % max_columns else 0)
                col = menu_dict[col_start:col_end]
                col_width = max(len(entry['name']) for entry in col) + number_len if col else 0
                col_widths.append(col_width)
                columns.append(col)
                col_start = col_end

            total_width = sum(col_widths) + 2 * (max_columns - 1)

        # Print all rows, handling missing entries in each column
        max_rows = max(len(col) for col in columns)
        for row_idx in range(max_rows):
            row_entries = []
            for col_idx, col in enumerate(columns):
                if row_idx < len(col):
                    entry = col[row_idx]
                    row_entries.append(f"{entry['key']}. {entry['name']}".ljust(col_widths[col_idx]))
                else:
                    row_entries.append(''.ljust(col_widths[col_idx]))
            print('  '.join(row_entries).rstrip())
        print()

    def get_demo_desc(self, menu_dict, key):
        return next((entry['name'] for entry in menu_dict if entry['key'] == key), 'Unknown demo')

    def demo(self, _class):
        instr_has_lib_demo_dict = hasattr(_class, 'lib_demo_dict') # check if demo_dict exist/declared for instrument class
        instr_has_lib_demo = hasattr(_class, 'lib_demo') # check if lib_demo function exist/declared for instrument class

        # if neither demo_dict nor lib_demo exist, return None
        if not instr_has_lib_demo_dict and not instr_has_lib_demo:
            print('This lib has no demo functions.')
            return None

        # if only lib_demo exist, call lib_demo
        if not instr_has_lib_demo_dict and instr_has_lib_demo:
            result = _class.lib_demo()
            return result

        # if both demo_dict and lib_demo exist, show menu and proceed
        if instr_has_lib_demo_dict and instr_has_lib_demo:
            self.show_demo_menu(_class.lib_demo_dict)

        demo_num = input('Enter demo number: ')

        demo_num = demo_num.lower()
        demo_desc = self.get_demo_desc(_class.lib_demo_dict, demo_num)
        if demo_desc == 'Unknown demo':
            print('Unknown demo number entered.')
            return None
        try:
            result = _class.lib_demo(demo_desc)
            return result
        finally:
            pass

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
