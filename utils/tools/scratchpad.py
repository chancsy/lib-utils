# %% [markdown]
# #### Demo Launcher

# %%
from utils.utilities import UtilityFunctions; utils = UtilityFunctions()
from utils.standalone.widget_utils import build_lib_demo_widget

# from utils.standalone.selenium_utils import SeleniumUtils; swd = SeleniumUtils(); build_lib_demo_widget(swd, swd.lib_demo_params)
# from utils.standalone.pdf_utils import PdfUtils; pdf_utils = PdfUtils(); build_lib_demo_widget(pdf_utils, pdf_utils.lib_demo_params)
from utils.standalone.playwright_utils import PlaywrightUtils; pw_utils = PlaywrightUtils(); build_lib_demo_widget(pw_utils, pw_utils.lib_demo_params)

# %% [markdown]
# ### scripts

# %% [markdown]
# #### boiler plate

# %%
import sys; sys.path.append(r'./userscripts')
# from script_collections import *

from utils.utilities import UtilityFunctions
utils = UtilityFunctions()
utils.ipython_auto_reload_modules()

import logging
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# %% [markdown]
# #### Exchange Rate

# %% [markdown]
# ##### print_xe_currency_xpaths

# %%
from userscripts.script_collections import XECurrency
xe = XECurrency()
xe.print_xe_currency_xpaths(currencies=['USD', 'SGD', 'EUR', 'GBP', 'JPY', 'CNY', 'AUD', 'NZD', 'THB', 'KRW', 'HKD'])

# %% [markdown]
# ##### get exchange rates

# %%
from userscripts.script_collections import XECurrency
xe = XECurrency()
# # get_MYR_rates_from_xe_dotcom(dates=["2024-06-30", "2024-07-31", "2024-08-31", "2024-09-30"])
xe.get_MYR_rates_from_xe_dotcom(dates=utils.get_last_day_of_month(2026), currencies=['AUD','HKD','JPY','KRW','SGD','THB','USD'])

# %% [markdown]
# #### AppUpdater

# %%
from script_collections import AppUpdater
updater = AppUpdater()

on_stale_files=None # None, ignore, clean

usr = utils.get_logon_username()
# updater.update_github_portable_app(repo_owner='gitextensions', repo_name='gitextensions', filter_value='GitExtensions-Portable-x64', dest_path=rf'C:/Users/{usr}/Downloads/programs/GitExtensions-Portable/', on_stale_files=on_stale_files)
# updater.update_github_portable_app(repo_owner='moneymanagerex', repo_name='moneymanagerex', filter_value='win64-portable.zip', dest_path=rf'C:/Users/{usr}/Downloads/programs/MoneyManagerEx/', on_stale_files=on_stale_files)
# updater.update_github_portable_app(repo_owner='genymobile', repo_name='scrcpy', filter_value='win64', dest_path=rf'C:/Users/{usr}/Downloads/programs/scrcpy-win64/', on_stale_files=on_stale_files)
# updater.update_github_portable_app(repo_owner='praydog', repo_name='UEVR', filter_value='.zip', dest_path=rf'C:/Users/{usr}/Downloads/programs/UEVR/', on_stale_files=on_stale_files)
# updater.update_github_portable_app(repo_owner='nomi-san', repo_name='parsec-vdd', filter_value='.zip', dest_path=rf'C:/Users/{usr}/Downloads/programs/ParsecVDisplay/', on_stale_files=on_stale_files)
updater.update_adb(download_url='https://dl.google.com/android/repository/platform-tools-latest-windows.zip', dest_path=rf'C:/Users/{usr}/Downloads/programs/adb/', on_stale_files=on_stale_files)

# extract fail
# updater.update_github_portable_app(repo_owner='git-for-windows', repo_name='git', filter_value='64-bit.7z.exe', dest_path=rf'C:/Users/{usr}/Downloads/programs/git/', on_stale_files=on_stale_files)


# %% [markdown]
# #### Bills

# %%
from userscripts.script_collections import Bills
bills = Bills()
bills.get_LAPS_bill_amount(account_no='17893330-IP1230331')

# %%
import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.mytnb.com.my/")
    try:
        page.get_by_role("button", name="Close").click(timeout=200) # try to close the pop-up if it appears, but ignore if it doesn't
    except:
        pass
    page.get_by_role("textbox", name="Enter Email Address").click()
    page.get_by_role("textbox", name="Enter Email Address").fill("test")
    page.get_by_role("textbox", name="Enter Password").click()
    page.get_by_role("textbox", name="Enter Password").fill("test")
    page.get_by_role("button", name="Login").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)


# %% [markdown]
# #### New Section

# %%
from utils.utilities import UtilityFunctions; utils = UtilityFunctions()
