from .utilities import UtilityFunctions
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
