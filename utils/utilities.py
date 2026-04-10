import sys
import subprocess
from ._internal.util_binary import UtilityBinaryMixin
from ._internal.util_collections import UtilityCollectionsMixin
from ._internal.util_dataframe import UtilityDataFrameMixin
from ._internal.util_demo import UtilityDemoMixin
from ._internal.util_filesystem import UtilityFilesystemMixin
from ._internal.util_ipython import UtilityIPythonMixin
from ._internal.util_lan_monitor import LanMonitorClient, LanMonitorServer
from ._internal.util_output import UtilityOutputMixin
from ._internal.util_runtime import UtilityRuntimeMixin
from ._internal.util_testing import UtilityTestingMixin
from ._internal.util_text import UtilityTextMixin
from ._internal.util_threads import UtilityThreadMixin
from ._internal.util_time import UtilityTimeMixin
from ._internal.util_web import UtilityWebMixin
# from utilities import UtilityFunctions
# from utilities import * # to include all functions
# utils = UtilityFunctions()
# utils.exit_if_module_missing('selenium')
# if not utils.module_exists('selenium'):
#     return

class UtilityFunctions(
    UtilityIPythonMixin,
    UtilityBinaryMixin,
    UtilityTimeMixin,
    UtilityTextMixin,
    UtilityCollectionsMixin,
    UtilityDataFrameMixin,
    UtilityFilesystemMixin,
    UtilityRuntimeMixin,
    UtilityOutputMixin,
    UtilityWebMixin,
    UtilityThreadMixin,
    UtilityDemoMixin,
    UtilityTestingMixin,
):
    _sys_exit_overridden = False # Class-level flag to track if the message has been shown

    def __init__(self):
        # binary data utils init
        self._generate_conversion_functions()
        self.temporary_dir_list = set()
        self.override_sys_exit_in_ipython()
        self.ipython = self.get_ipython_handle() if self.in_ipython() else None

        # Progress line tracking
        self._progress_line_active = False
        self._last_line_length = 0

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

class TestClass:
    def __init__(self, test_name, utils=None):
        self.utils = utils or UtilityFunctions() # Use the provided utils or create a new instance if None
        if not test_name:
            test_name = f'Test_{self.utils.get_datetimestamp(date_time_delim="_")}' # Use a default test name with timestamp if not provided
        self.test_name = test_name

    def exit_if_up_time_exceeds(self, pc_up_time_days, warn_only=False):
        up_time = self.utils.get_up_time_days()
        if up_time >= pc_up_time_days:
            print('Test PC has been running for too long. Please restart the PC before running the test.')
            if not warn_only:
                sys.exit(1)

    def print_test_info(self, print_test_env=True, print_git_info=True, pkg_list=[]):
        if print_test_env:
            self.utils.print_test_environment(pkg_list=pkg_list)
        if print_git_info:
            git_commit_hash = self.utils.get_git_info('commit')
            if git_commit_hash:
                print(f'Git Commit Hash: {git_commit_hash}')
        print(f'Test Name: {self.test_name}')
