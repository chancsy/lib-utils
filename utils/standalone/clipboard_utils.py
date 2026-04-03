from ..utilities import UtilityFunctions
utils = UtilityFunctions()
utils.exit_if_module_missing('pyperclip')

import pyperclip as clipboard

class Clipboard:
    def __init__(self):
        pass

    def copy(self, text):
        clipboard.copy(text)

    def paste(self):
        return clipboard.paste()

    def lib_demo(self):
        print('Clipboard demo - Copy any text to clipboard and press enter')
        utils.wait_user_enter_key()
        cb = self.paste()
        print(f'Clipboard is: {cb}')

        self.copy('test')
        print(f'Clipboard demo - "test" copied to clipboard, paste to see if it works')
        utils.wait_user_enter_key()
