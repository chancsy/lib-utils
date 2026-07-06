import datetime
import logging
import os
import shutil
from enum import Enum

from utils.standalone.selenium_utils import SeleniumUtils
from utils.utilities import UtilityFunctions
utils = UtilityFunctions()

# from utils.standalone.playwright_utils import PlaywrightUtils
# pw = PlaywrightUtils()

class Bills():
    from utils.standalone.selenium_utils import SeleniumUtils
    def __init__(self):
        self.swd = SeleniumUtils()

    def get_LAPS_bill_amount(self, account_no):
        self.swd.new_driver(headless=True)
        try:
            self.swd.open_url('https://mylapapps.lap.com.my')
            xpath_input_no_account = '/html/body/div[1]/div/div/div/div[2]/form/div[1]/div/input'
            self.swd.css_element_field_entry(selector=xpath_input_no_account, value=account_no, locator_type=self.swd.LocatorType.XPATH)
            xpath_button_check = '/html/body/div[1]/div/div/div/div[2]/form/div[2]/div/input'
            self.swd.css_element_click(selector=xpath_button_check, locator_type=self.swd.LocatorType.XPATH)

            xpath_bill_amount = '/html/body/div[1]/div/div/div/div[2]/div[2]/div[2]/label/b'
            if not self.swd.wait_css_element(selector=xpath_bill_amount, timeout=10, locator_type=self.swd.LocatorType.XPATH):
                print(f"Account: {account_no} - No bill amount found.")
                return None
            else:
                amount_due = self.swd.css_element_text(selector=xpath_bill_amount, locator_type=self.swd.LocatorType.XPATH)
                try:
                    amount_due_val = float(amount_due.split('MYR')[-1].strip())
                except:
                    amount_due_val = 'Unknown'
                print(f"Account: {account_no} - Amount due: {amount_due_val}")
        except Exception as e:
            logging.error(f'Error occurred: {e}')
        finally:
            self.swd.quit_driver()

        return amount_due_val

    class TNB():
        def __init__(self):
            self.browser = pw.new_browser(headless=False)
            pw.open_url('https://www.tnb.com.my/')
            try:
                pw.get_by_role("button", name="Close").click(timeout=2000)
            except:
                pass

        def login(self, username, password):
            pw.get_by_role("textbox", name="Enter Email Address").fill(username)
            pw.get_by_role("textbox", name="Enter Password").fill(password)
            pw.get_by_role("button", name="Sign In").click() # TBD button name
            pass

        def change_account(self, account_no):
            pw.get_by_role("button", name="Accounts").click() # TBD button name
            pass

        def get_bill_amount(self, account_no):
            pass

        def download_bill(self, account_no, year, month):
            pass

        def logout_teardown(self):
            pw.get_by_role("button", name="Sign Out").click() # TBD button name
            pw.close_browser()


class XECurrency():
    def __init__(self):
        self.swd = SeleniumUtils()

    # Enum of XPath for currency's exchange rate in the table on xe.com.
    # Generate/update using the function print_xe_currency_xpaths() below.
    class XeCurrencyXPath(Enum):
        USD = r'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[1]/td[3]'
        EUR = r'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[2]/td[3]'
        GBP = r'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[3]/td[3]'
        AUD = r'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[5]/td[3]'
        SGD = r'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[7]/td[3]'
        JPY = r'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[10]/td[3]'
        CNY = r'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[11]/td[3]'
        NZD = r'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[12]/td[3]'
        THB = r'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[13]/td[3]'
        HKD = r'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[16]/td[3]'
        KRW = r'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[26]/td[3]'

    # Retrieve XPath for each currency from xe.com, then print for user to copy and
    # paste into the Enum above. The XPath is more reliable than CSS selectors, as
    # the table structure can change, but the XPath will still work as long as the
    # currency is in the same position in the table. The function will print the
    # XPath for each currency in the table, which can then be copied and pasted
    # into the Enum above.
    # Reference URL: https://www.xe.com/currencytables/?from=MYR&date=2026-01-01
    def print_xe_currency_xpaths(self, date=None, currencies: list[str] | None = None):
        self.swd.new_driver(headless=True)
        try:
            date = date or utils.get_datestamp(time_now=utils.get_current_datetime()-datetime.timedelta(days=5), date_delim='-')
            self.swd.open_url(site_url=f'https://www.xe.com/currencytables/?from=MYR&date={date}')

            for i in range(1, 500):
                currency_xpath = f'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[{i}]/th/a'
                rate_xpath = f'//*[@id="table-section"]/section/div[2]/div/table/tbody/tr[{i}]/td[3]'

                try:
                    currency = self.swd.css_element_text(selector=currency_xpath, locator_type=self.swd.LocatorType.XPATH)
                    if currencies is None or currency in currencies:
                        print(f"    {currency} = r'{rate_xpath}'")
                except Exception as e:
                    logging.info(f'Unable to find currency at row {i}, assuming end of table.')
                    break
        except Exception as e:
            logging.error(f'Error occurred: {e}')
        finally:
            self.swd.quit_driver()

    # dates need to be in YYYY_MM_DD format
    # Example:
    #   get_MYR_rates_from_xe_dotcom([s.format_dates_YYYY_MM_DD(x) for x in s.get_last_day_of_month(2023)])
    #   get_MYR_rates_from_xe_dotcom([s.format_dates_YYYY_MM_DD(x) for x in s.get_last_day_of_month(2023)], ['SGD', 'USD'])
    def get_MYR_rates_from_xe_dotcom(self, dates, currencies: list[str] | None = None):
        from utils.standalone.math_utils import MathUtils
        maths = MathUtils()

        currency_selectors = list(self.XeCurrencyXPath) if currencies is None else [self.XeCurrencyXPath[c] for c in currencies]
        print(utils.list_to_csv(['Date'] + [x.name for x in currency_selectors]))

        self.swd.new_driver(headless=True)
        try:
            for date in dates:
                if date > utils.get_current_datetime():
                    logging.warning(f'Skipping future date: {date}')
                    continue
                date_str = utils.get_datestamp(time_now=date, date_delim='-')
                self.swd.open_url(site_url=f'https://www.xe.com/currencytables/?from=MYR&date={date_str}')

                rates = []
                for selector in currency_selectors:
                    rates.append(self.swd.css_element_text(selector=selector.value, locator_type=self.swd.LocatorType.XPATH))
                print(f'{date},{utils.list_to_csv(rates)}')
                utils.sleep(maths.random_integer(5, 10)) # be nice to the server, and avoid getting blocked for too many requests
        except Exception as e:
            logging.error(f'Error occurred: {e}')
        finally:
            self.swd.quit_driver()

class AppUpdater():
    def __init__(self):
        pass

    def _find_7z_executable(self):
        import shutil as _shutil
        if path := _shutil.which('7z'):
            return path
        for candidate in [r'C:\Program Files\7-Zip\7z.exe', r'C:\Program Files (x86)\7-Zip\7z.exe']:
            if os.path.isfile(candidate):
                return candidate
        return None

    def _download_and_extract(self, app_name: str, download_url: str, temp_dir: str) -> str | None:
        result = utils.download_file(url=download_url, download_dir=temp_dir)
        if result == 'failed':
            logging.error(f'[{app_name}] Failed to download the file.')
            return None
        downloaded_file_path = utils.os_path_join(temp_dir, utils.get_filename(download_url))
        extract_dir = utils.os_path_join(temp_dir, 'extracted')
        if downloaded_file_path.endswith('.7z.exe'):
            import subprocess
            seven_zip = self._find_7z_executable()
            if not seven_zip:
                logging.error(f'[{app_name}] 7z.exe not found. Install 7-Zip to extract .7z.exe files.')
                return None
            os.makedirs(extract_dir, exist_ok=True)
            result = subprocess.run([seven_zip, 'x', downloaded_file_path, f'-o{extract_dir}', '-y'],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                logging.error(f'[{app_name}] 7z extraction failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}')
                return None
        elif downloaded_file_path.endswith('.7z'):
            import py7zr
            with py7zr.SevenZipFile(downloaded_file_path, mode='r') as archive:
                archive.extractall(path=extract_dir)
        else:
            shutil.unpack_archive(downloaded_file_path, extract_dir)
        return utils.unwrap_single_dir_archive(extract_dir)

    def _handle_stale_files(self, app_name: str, extract_dir: str, dest_path: str,
                            on_stale_files: str | None, exclude_files: list[str] | None = None) -> bool:
        if not os.path.isdir(dest_path):
            return True
        stale_files = utils.find_orphaned_files(source_dir=extract_dir, dest_dir=dest_path)
        if exclude_files:
            stale_files = [f for f in stale_files if f not in exclude_files]
        if not stale_files:
            return True
        if on_stale_files is None:
            logging.warning(
                f'[{app_name}] Aborting: {len(stale_files)} file(s) in dest_path are not in the new release.\n'
                f'Re-run with on_stale_files="ignore" to leave them, or on_stale_files="clean" to remove them first.\n'
                'Stale files:\n' + '\n'.join(f'  {f}' for f in stale_files)
            )
            return False
        if on_stale_files == 'clean':
            shutil.rmtree(dest_path)
            logging.info(f'[{app_name}] Cleaned dest_path before update: {dest_path}')
        elif on_stale_files == 'ignore':
            logging.info(f'[{app_name}] Proceeding with stale files in dest_path: {dest_path}')
        return True

    def _install(self, app_name: str, extract_dir: str, dest_path: str, release_ver: str):
        utils.create_directory(dest_path)
        shutil.copytree(extract_dir, dest_path, dirs_exist_ok=True)
        logging.info(f'[{app_name}] Update complete: {release_ver}')

    def _check_version(self, app_name: str, installed_ver: str | None,
                       release_ver: str, force_update: bool) -> bool:
        """Returns True if an update should proceed, False if already up to date."""
        logging.info(f'[{app_name}] Installed: {installed_ver or "not installed"} | Latest: {release_ver}')
        if installed_ver == release_ver and not force_update:
            logging.info(f'[{app_name}] Already up to date: {release_ver}')
            return False
        logging.info(f'[{app_name}] Updating from {installed_ver or "not installed"} to {release_ver}')
        return True

    def _read_properties_key(self, directory: str, filename: str, key: str) -> str | None:
        """Reads a value from a key=value properties file in the given directory."""
        props_path = utils.os_path_join(directory, filename)
        if not utils.file_exists(props_path):
            return None
        for line in utils.read_file(props_path).splitlines():
            if line.startswith(f'{key}='):
                return line[len(key) + 1:].strip()
        return None

    def update_github_portable_app(self, repo_owner, repo_name, filter_value, dest_path,
                                   on_stale_files: str | None = None, force_update: bool = False):
        """
        on_stale_files: None     → abort if stale files detected (lists them for review)
                        'ignore' → proceed, leaving stale files in dest_path
                        'clean'  → wipe dest_path before copying new files
        """
        app_name = f'{repo_owner}/{repo_name}'
        version_file = f'version_{repo_owner}_{repo_name}.txt'
        version_file_path = utils.os_path_join(dest_path, version_file)
        installed_ver = utils.read_file(version_file_path).strip() if utils.file_exists(version_file_path) else None

        release_info = utils.get_github_latest_release(repo_owner, repo_name)
        if not release_info:
            logging.error(f'[{app_name}] Unable to fetch release info.')
            return

        release_ver = release_info['tag_name']
        if not self._check_version(app_name, installed_ver, release_ver, force_update):
            return

        download_urls = utils.get_github_release_download_url(release_info, filter_value=filter_value)
        if not download_urls:
            logging.error(f'[{app_name}] Unable to find download URL with specified filter.')
            return
        logging.info(f'[{app_name}] Download URL: {download_urls[0]}')

        temp_dir = utils.create_temp_dir()
        try:
            extract_dir = self._download_and_extract(app_name, download_urls[0], temp_dir)
            if extract_dir is None:
                return
            if not self._handle_stale_files(app_name, extract_dir, dest_path, on_stale_files,
                                            exclude_files=[version_file]):
                return
            self._install(app_name, extract_dir, dest_path, release_ver)
            utils.write_file(version_file_path, release_ver, overwrite=True)
        finally:
            utils.remove_temp_dir(temp_dir)

    def update_adb(self, download_url, dest_path, on_stale_files: str | None = None, force_update: bool = False):
        _PROPS_FILE = 'source.properties'
        _VERSION_KEY = 'Pkg.Revision'
        app_name = 'ADB'

        installed_ver = self._read_properties_key(dest_path, _PROPS_FILE, _VERSION_KEY)

        temp_dir = utils.create_temp_dir()
        try:
            extract_dir = self._download_and_extract(app_name, download_url, temp_dir)
            if extract_dir is None:
                return

            release_ver = self._read_properties_key(extract_dir, _PROPS_FILE, _VERSION_KEY)
            if not release_ver:
                logging.error(f'[{app_name}] Unable to determine version from {_PROPS_FILE} in archive.')
                return

            if not self._check_version(app_name, installed_ver, release_ver, force_update):
                return

            if not self._handle_stale_files(app_name, extract_dir, dest_path, on_stale_files):
                return
            self._install(app_name, extract_dir, dest_path, release_ver)
        finally:
            utils.remove_temp_dir(temp_dir)
