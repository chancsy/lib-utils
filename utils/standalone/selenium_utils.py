import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()

# from selenium.webdriver.common.action_chains import ActionChains
# import time
import os
from enum import Enum, auto

class SeleniumUtils:
    # Enum of locator types provided by Selenium (https://www.selenium.dev/documentation/webdriver/elements/locators/).
    # Members are plain placeholders (auto()), not selenium.webdriver.common.by.By's own
    # constants - resolved to the real By.* values lazily in _resolve_locator, so this
    # class definition itself doesn't require selenium to be importable.
    class LocatorType(Enum):
        CSS_SELECTOR = auto()
        XPATH = auto()
        ID = auto()
        NAME = auto()
        TAG_NAME = auto()
        CLASS_NAME = auto()
        LINK_TEXT = auto()
        PARTIAL_LINK_TEXT = auto()

    def __init__(self):
        # Checked here (at construction) rather than at module-import time, so merely
        # importing this module doesn't require selenium/webdriver_manager - only
        # actually instantiating SeleniumUtils does. Cached on self so the methods below
        # don't need their own import statements.
        utils.exit_if_module_missing('selenium')
        utils.exit_if_module_missing('webdriver_manager')
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.chrome.service import Service as ChromeService
        from webdriver_manager.chrome import ChromeDriverManager
        self._webdriver = webdriver
        self._By = By
        self._WebDriverWait = WebDriverWait
        self._EC = EC
        self._ChromeService = ChromeService
        self._ChromeDriverManager = ChromeDriverManager
        self.default_locator = SeleniumUtils.LocatorType.CSS_SELECTOR
        self.driver = None

    def new_driver(self, headless=False, auto_install_driver=False, socks5_proxy=None):
        download_dir = os.path.expanduser("~/Downloads/")

        if auto_install_driver:
            service = self._ChromeService(self._ChromeDriverManager().install())

        options = self._webdriver.ChromeOptions()
        profile = {
            "plugins.always_open_pdf_externally": True,
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True
            }
        options.add_experimental_option("prefs", profile)
        options.add_argument('log-level=3')
        # options.add_argument("--window-size=1552,832") # dev use window size
        options.add_experimental_option('excludeSwitches', ['enable-logging']) # Suppress "DevTools listening on ws://127.0.0.1" message

        if headless:
            options.add_argument("--headless")
        if socks5_proxy:
            options.add_argument(f'--proxy-server=socks5://{socks5_proxy}')

        try:
            if auto_install_driver:
                driver = self._webdriver.Chrome(service=service, options=options)
            else:
                driver = self._webdriver.Chrome(options=options)
        except Exception as e:
            print(f"Error occurred while creating the WebDriver: {e}")
            driver = None

        self.driver = driver
        return driver

    def open_url(self, site_url, driver=None):
        (driver or self.driver).get(site_url)

    def quit_driver(self, driver=None):
        target = driver or self.driver
        if target is None:
            return
        target.quit()
        if driver is None:  # only clear instance state when using self.driver
            self.driver = None

    def wait(self, wait_s, driver=None):
        # TBD driver wait instead of system wide wait
        utils.sleep(wait_s)

    # def css_element_click(wait_s, selector):
    #     # WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector))).click()
    #     WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
    #     # WebDriverWait(driver, 3).until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
    #     time.sleep(wait_s)
    #     driver.find_element(By.CSS_SELECTOR, selector).click()
    #     return
    def _resolve_locator(self, locator_type):
        lt = locator_type or self.default_locator
        if not isinstance(lt, SeleniumUtils.LocatorType):
            return lt
        By = self._By
        return {
            SeleniumUtils.LocatorType.CSS_SELECTOR: By.CSS_SELECTOR,
            SeleniumUtils.LocatorType.XPATH: By.XPATH,
            SeleniumUtils.LocatorType.ID: By.ID,
            SeleniumUtils.LocatorType.NAME: By.NAME,
            SeleniumUtils.LocatorType.TAG_NAME: By.TAG_NAME,
            SeleniumUtils.LocatorType.CLASS_NAME: By.CLASS_NAME,
            SeleniumUtils.LocatorType.LINK_TEXT: By.LINK_TEXT,
            SeleniumUtils.LocatorType.PARTIAL_LINK_TEXT: By.PARTIAL_LINK_TEXT,
        }[lt]

    def css_element_click(self, selector, locator_type=None, driver=None):
        d = driver or self.driver
        e = d.find_element(self._resolve_locator(locator_type), selector)
        d.execute_script("arguments[0].click();", e)

    def css_element_text(self, selector, locator_type=None, driver=None):
        d = driver or self.driver
        return d.find_element(self._resolve_locator(locator_type), selector).text

    def css_element_field_entry(self, selector, value, locator_type=None, driver=None):
        d = driver or self.driver
        e = d.find_element(self._resolve_locator(locator_type), selector)
        e.clear()
        e.send_keys(value)

    def css_element(self, selector, locator_type=None, driver=None):
        try:
            return (driver or self.driver).find_element(self._resolve_locator(locator_type), selector)
        except:
            return None

    # def css_element_present(selector):
    #     return len(driver.find_elements(By.CSS_SELECTOR, selector)) > 0
    #
    # TODO need more testing
    def wait_css_element(self, selector, timeout, locator_type=None, driver=None):
        try:
            self._WebDriverWait(driver or self.driver, timeout).until(self._EC.presence_of_element_located((self._resolve_locator(locator_type), selector)))
            return True
        except:
            return False

    # TODO need more testing
    def wait_for_page_load(self, driver=None):
        # Wait for the document.readyState to be "complete"
        self._WebDriverWait(driver or self.driver, 10).until(
            self._EC.presence_of_element_located((self._By.TAG_NAME, "body"))
        )

    # TODO need more testing
    def wait_till_clickable(self, selector, timeout, locator_type=None, driver=None):
        self._WebDriverWait(driver or self.driver, timeout).until(self._EC.element_to_be_clickable((self._resolve_locator(locator_type), selector)))

    # TODO need more testing
    def wait_till_text_matched(self, selector, text_to_match, timeout, driver=None):
        for _ in range(timeout * 10):
            if self.css_element_text(selector, driver=driver) == text_to_match:
                return True
            utils.sleep(0.1)
        return False

    lib_demo_params = [
        {'key': 'a', 'name': 'New Driver', 'function': 'new_driver', 'inputs': [
            {'label': 'Headless', 'name': 'headless', 'type': bool, 'default': False},
            {'label': 'Auto-install driver', 'name': 'auto_install_driver', 'type': bool, 'default': False},
            {'label': 'SOCKS5 proxy', 'name': 'socks5_proxy', 'type': str, 'default': '', 'width': '80px', 'placeholder': 'host:port'},
        ]},
        {'key': 'b', 'name': 'Open URL', 'function': 'open_url', 'inputs': [
            {'label': 'URL', 'name': 'site_url', 'type': str, 'default': 'https://www.google.com', 'width': '220px'},
        ]},
        {'key': 'c', 'name': 'Quit Driver', 'function': 'quit_driver', 'inputs': []},
    ]


if __name__ == '__main__':
    selenium = SeleniumUtils()
    utils.demo(selenium)
