import sys
import subprocess
import csv
import json
from pathlib import Path
from ._internal.util_binary import UtilityBinaryMixin
from ._internal.util_collections import UtilityCollectionsMixin
from ._internal.util_dataframe import UtilityDataFrameMixin
from ._internal.util_demo import UtilityDemoMixin
from ._internal.util_filesystem import UtilityFilesystemMixin
from ._internal.util_ipython import UtilityIPythonMixin
from ._internal.util_lan_monitor import LanMonitorClient, LanMonitorServer
from ._internal.util_output import UtilityOutputMixin, TeeStringIO
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
    UtilityBinaryMixin,
    UtilityCollectionsMixin,
    UtilityDataFrameMixin,
    UtilityDemoMixin,
    UtilityFilesystemMixin,
    UtilityIPythonMixin,
    UtilityOutputMixin,
    UtilityRuntimeMixin,
    UtilityTestingMixin,
    UtilityTextMixin,
    UtilityThreadMixin,
    UtilityTimeMixin,
    UtilityWebMixin,
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

    # Normalize keys for stable text matching across sources.
    def normalize_lookup_key(self, key: str) -> str:
        if key is None:
            return ''
        normalized = str(key).strip().lower().replace('_', ' ')
        return ' '.join(normalized.split())

    # Discover a sidecar file near the source file, with an optional fallback name.
    def find_override_file(self, source_path: str, suffix: str = '.override.csv', fallback_name: str = 'override.csv') -> str | None:
        source = Path(source_path)
        sidecar_path = source.with_name(f'{source.stem}{suffix}')
        if sidecar_path.is_file():
            print(f'Found sidecar file: {sidecar_path}')
            return str(sidecar_path)

        fallback_path = source.with_name(fallback_name)
        if fallback_path.is_file():
            print(f'Found fallback sidecar file: {fallback_path}')
            return str(fallback_path)
        return None

    # Read a two-column (key, value) override CSV into a normalized map.
    def read_key_value_override_csv(self, file_path: str, key_column: str = 'key', value_column: str = 'value') -> dict[str, str]:
        overrides: dict[str, str] = {}
        with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if key_column not in (reader.fieldnames or []) or value_column not in (reader.fieldnames or []):
                raise ValueError(
                    f'Override CSV missing required columns: {key_column}, {value_column}. '
                    f'Found: {reader.fieldnames}'
                )

            for row in reader:
                raw_key = row.get(key_column, '')
                raw_value = row.get(value_column, '')
                norm_key = self.normalize_lookup_key(raw_key)
                value = str(raw_value).strip()
                if not norm_key or not value:
                    continue
                overrides[norm_key] = value
        return overrides

    # Persist a list of dict rows to CSV using explicit field ordering.
    def write_dict_rows_to_csv(self, file_path: str, rows: list[dict], fieldnames: list[str], encoding: str = 'utf-8') -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding=encoding, newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    # Persist JSON using stable formatting to reduce commit noise.
    def write_json_file(self, file_path: str, data: object, encoding: str = 'utf-8') -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding=encoding) as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')

    # Read JSON, returning 'default' if the file doesn't exist (caller decides whether
    # that's a valid empty-config case or should be treated as an error).
    def read_json_file(self, file_path: str, default: object = None, encoding: str = 'utf-8') -> object:
        path = Path(file_path)
        if not path.is_file():
            return default
        with open(path, 'r', encoding=encoding) as f:
            return json.load(f)

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
