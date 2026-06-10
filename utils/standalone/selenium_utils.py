import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()
utils.exit_if_module_missing('selenium')
utils.exit_if_module_missing('webdriver_manager')

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
# from selenium.webdriver.common.action_chains import ActionChains
# import time
import os
from enum import Enum

class SeleniumUtils:
    # enum of locator types provided by Selenium
    # https://www.selenium.dev/documentation/webdriver/elements/locators/
    class LocatorType(Enum):
        CSS_SELECTOR = By.CSS_SELECTOR
        XPATH = By.XPATH
        ID = By.ID
        NAME = By.NAME
        TAG_NAME = By.TAG_NAME
        CLASS_NAME = By.CLASS_NAME
        LINK_TEXT = By.LINK_TEXT
        PARTIAL_LINK_TEXT = By.PARTIAL_LINK_TEXT

    def __init__(self):
        self.default_locator = SeleniumUtils.LocatorType.CSS_SELECTOR
        self.driver = None

    def new_driver(self, headless=False, auto_install_driver=False, socks5_proxy=None):
        download_dir = os.path.expanduser("~/Downloads/")

        if auto_install_driver:
            service = ChromeService(ChromeDriverManager().install())

        options = webdriver.ChromeOptions()
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
                driver = webdriver.Chrome(service=service, options=options)
            else:
                driver = webdriver.Chrome(options=options)
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
        utils.sleep(wait_s)

    # def css_element_click(wait_s, selector):
    #     # WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector))).click()
    #     WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
    #     # WebDriverWait(driver, 3).until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
    #     time.sleep(wait_s)
    #     driver.find_element(By.CSS_SELECTOR, selector).click()
    #     return
    def css_element_click(self, selector, driver=None):
        d = driver or self.driver
        e = d.find_element(By.CSS_SELECTOR, selector)
        d.execute_script("arguments[0].click();", e)

    def css_element_text(self, selector, locator_type=None, driver=None):
        d = driver or self.driver
        locator_type = locator_type or self.default_locator
        locator = locator_type.value if isinstance(locator_type, SeleniumUtils.LocatorType) else locator_type
        return d.find_element(locator, selector).text

    def css_element_field_entry(self, selector, string, driver=None):
        d = driver or self.driver
        e = d.find_element(By.CSS_SELECTOR, selector)
        e.clear()
        e.send_keys(string)

    def css_element(self, selector, driver=None):
        try:
            return (driver or self.driver).find_element(By.CSS_SELECTOR, selector)
        except:
            return None

    # def css_element_present(selector):
    #     return len(driver.find_elements(By.CSS_SELECTOR, selector)) > 0
    #
    # TODO need more testing
    def wait_css_element(self, selector, timeout, driver=None):
        try:
            WebDriverWait(driver or self.driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            return True
        except:
            return False

    # TODO need more testing
    def wait_for_page_load(self, driver=None):
        # Wait for the document.readyState to be "complete"
        WebDriverWait(driver or self.driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

    # TODO need more testing
    def wait_till_clickable(self, selector, timeout, driver=None):
        WebDriverWait(driver or self.driver, timeout).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))

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
