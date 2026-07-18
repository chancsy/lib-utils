import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()
utils.exit_if_module_missing('playwright')

import os
import tempfile
import time

from playwright.sync_api import sync_playwright


class PlaywrightUtils:
    """Thin bootstrap around Playwright's sync API.

    Deliberately does not wrap individual page actions — Playwright's own API
    (page.get_by_role(...), .fill(...), .click()) is already high-level enough
    to call directly. This class only handles launching/closing the browser.
    """

    def __init__(self):
        self._playwright = None
        self.browser = None
        self.page = None

    # persistent=True keeps a real user-data-dir so the same profile can be
    # reattached to (e.g. by a Playwright MCP server) across runs.
    # cdp_port, if set, launches Chromium with --remote-debugging-port=<port>
    # so an external tool (e.g. `@playwright/mcp --cdp-endpoint=...`) can attach
    # to this exact running session later.
    def new_browser(self, headless=True, persistent=True, user_data_dir=None, cdp_port=None, viewport=None):
        # launch_persistent_context does NOT default to a fixed viewport like
        # browser.new_page() does — without one, the effective viewport
        # follows the real OS window size, which made responsive layouts
        # (e.g. a site switching between a hamburger nav and a full nav bar
        # at different widths) behave inconsistently across runs/machines.
        self._playwright = sync_playwright().start()

        launch_args = []
        if cdp_port:
            launch_args.append(f'--remote-debugging-port={cdp_port}')

        if persistent:
            user_data_dir = user_data_dir or os.path.join(tempfile.gettempdir(), 'playwright_profile')
            context = self._playwright.chromium.launch_persistent_context(
                user_data_dir, headless=headless, args=launch_args, viewport=viewport,
            )
            self.browser = context
            self.page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = self._playwright.chromium.launch(headless=headless, args=launch_args)
            self.browser = browser
            self.page = browser.new_page(viewport=viewport)

        return self._playwright, self.browser, self.page

    def close_browser(self):
        if self.browser is not None:
            self.browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self.browser = None
        self.page = None
        self._playwright = None

    def dismiss_modal_button(self, button_name, timeout=8000):
        """Repeatedly click a named button (e.g. a modal's close/dismiss
        control) until no matching button is left attached to the page.

        A click can succeed (the event really was dispatched) while the
        modal's own JS handler for it isn't ready yet, silently no-opping —
        Playwright's click() only ever dispatches one physical click per
        call, it won't keep clicking on our behalf. So the post-click detach
        check is capped short (500ms) rather than given the full remaining
        budget: on failure we loop back and issue a fresh click, spending
        the timeout on repeated real clicks rather than one long wait that
        can't fix a no-op click by itself. The click() call itself still
        gets the full remaining budget, so this also waits out a modal that
        hasn't rendered yet at all.
        """
        deadline = time.monotonic() + timeout / 1000
        while True:
            remaining_ms = (deadline - time.monotonic()) * 1000
            if remaining_ms <= 0:
                return
            btn = self.page.get_by_role("button", name=button_name)
            try:
                btn.click(timeout=remaining_ms)
            except Exception:
                return  # nothing appeared/clickable within the budget — genuinely done
            try:
                btn.wait_for(state="detached", timeout=min(remaining_ms, 500))
                return  # confirmed gone — done, no need to keep burning the budget
            except Exception:
                pass  # click didn't take effect yet — loop back and click again

    def click_dismissing_modals(self, locator, dismiss_button_names=("Close", "Later"), attempts=4, click_timeout=8000):
        """Click a locator that's occasionally covered by a modal,
        re-dismissing (trying each of dismiss_button_names) and retrying
        instead of racing a single timed check — a modal's appearance isn't
        perfectly predictable in timing.
        """
        last_exc = None
        for _ in range(attempts):
            try:
                locator.click(timeout=click_timeout)
                return
            except Exception as e:
                last_exc = e
                for name in dismiss_button_names:
                    self.dismiss_modal_button(name, timeout=1500)
        raise last_exc

    lib_demo_params = [
        {'key': 'a', 'name': 'New Browser', 'function': 'new_browser', 'inputs': [
            {'label': 'Headless', 'name': 'headless', 'type': bool, 'default': True},
            {'label': 'Persistent', 'name': 'persistent', 'type': bool, 'default': True},
            {'label': 'CDP port', 'name': 'cdp_port', 'type': int, 'default': None, 'width': '80px', 'allow_empty': True},
        ]},
        {'key': 'b', 'name': 'Close Browser', 'function': 'close_browser', 'inputs': []},
    ]


if __name__ == '__main__':
    pw_utils = PlaywrightUtils()
    utils.demo(pw_utils)
