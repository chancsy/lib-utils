import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions

utils = UtilityFunctions()
utils.exit_if_module_missing('pyperclip')

import pyperclip as clipboard


class Clipboard:
    def __init__(self):
        pass

    # Copy text to the system clipboard.
    def copy(self, text: str) -> None:
        clipboard.copy(text)
        print(f'Copied to clipboard: {text}')

    # Return the current clipboard contents.
    def paste(self) -> str:
        text = clipboard.paste()
        print(f'Clipboard: {text}')
        return text

    lib_demo_params = [
        {'key': 'a', 'name': 'Copy', 'function': 'copy', 'inputs': [
            {'label': 'Text', 'name': 'text', 'type': str, 'default': '', 'width': '150px'},
        ]},
        {'key': 'b', 'name': 'Paste', 'function': 'paste', 'inputs': []},
    ]


if __name__ == '__main__':
    cb = Clipboard()
    utils.demo(cb)
