from utils.utilities import UtilityFunctions
utils = UtilityFunctions()
utils.exit_if_module_missing('selenium')
utils.exit_if_module_missing('webdriver_manager')

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.common.action_chains import ActionChains
# import time
import os

class SeleniumUtils:
    def __init__(self):
        pass

    def demo(self):
        print(f'{__name__} demo:')
        print('Creating a new WebDriver...')
        driver = self.new_driver()
        print('Opening google.com...')
        self.driver_open_url(driver, 'https://www.google.com')
        print('Waiting 5 seconds...')
        self.driver_wait(driver, 5)
        print('Quitting the WebDriver...')
        self.driver_quit(driver)
        print('Done.')

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

        return driver

    def driver_open_url(self, driver, site_url):
        driver.get(site_url)

    def driver_quit(self, driver):
        driver.quit()

    def driver_wait(self, driver, wait_s):
        utils.sleep(wait_s)

    # def css_element_click(wait_s, selector):
    #     # WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector))).click()
    #     WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
    #     # WebDriverWait(driver, 3).until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
    #     time.sleep(wait_s)
    #     driver.find_element(By.CSS_SELECTOR, selector).click()
    #     return
    def css_element_click(self, driver, selector):
        e = driver.find_element(By.CSS_SELECTOR, selector)
        driver.execute_script("arguments[0].click();", e)

    def css_element_text(self, driver, selector):
        e = driver.find_element(By.CSS_SELECTOR, selector)
        return e.text

    def css_element_field_entry(self, driver, selector, string):
        e = driver.find_element(By.CSS_SELECTOR, selector)
        e.clear()
        e.send_keys(string)
        return

    def css_element(self, driver, selector):
        try:
            return driver.find_element(By.CSS_SELECTOR, selector)
        except:
            return None

    # def css_element_present(selector):
    #     return len(driver.find_elements(By.CSS_SELECTOR, selector)) > 0
    #
    # TODO need more testing
    def wait_css_element(self, driver, selector, timeout):
        try:
            WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            return True
        except:
            return False

    # TODO need more testing
    def wait_for_page_load(self, driver):
        # Wait for the document.readyState to be "complete"
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

    # TODO need more testing
    def wait_till_clickable(self, driver, selector, timeout):
        WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
        return

    # TODO need more testing
    def wait_till_text_matched(self, driver, timeout, selector, text_to_match):
        matched = False
        for i in range(0, timeout*10):
            if self.css_element_text(driver, selector) == text_to_match:
                matched = True
                break
            utils.sleep(0.1)
        return matched
