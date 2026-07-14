import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions

utils = UtilityFunctions()


class Clipboard:
    def __init__(self):
        # Checked here (at construction) rather than at module-import time, so merely
        # importing this module doesn't require pyperclip - only actually instantiating
        # Clipboard does. Cached on self so copy()/paste() don't need their own import
        # statements.
        utils.exit_if_module_missing('pyperclip')
        import pyperclip
        self._pyperclip = pyperclip

    # Copy text to the system clipboard.
    def copy(self, text: str) -> None:
        self._pyperclip.copy(text)
        print(f'Copied to clipboard: {text}')

    # Return the current clipboard contents.
    def paste(self) -> str:
        text = self._pyperclip.paste()
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
