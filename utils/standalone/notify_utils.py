import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()


class Notifier:
    """Facade over notification backends, so callers don't need to know which one is in use.

    'slack' (wraps SlackUtils) and 'telegram' (wraps TelegramUtils) are both
    implemented. Both backends' send_message/send_file take a per-call
    destination (Slack channel / Telegram chat_id) rather than binding it at
    connect() time, so this facade can pass `destination` through uniformly
    regardless of which backend is active.
    """

    def __init__(self, channel: str = 'slack'):
        self.channel = channel
        self._backend = None

    def connect(self, **kwargs):
        if self.channel == 'slack':
            from .slack_utils import SlackUtils
            self._backend = SlackUtils()
            self._backend.connect(token=kwargs['token'])
        elif self.channel == 'telegram':
            from .telegram_utils import TelegramUtils
            self._backend = TelegramUtils()
            self._backend.connect(token=kwargs['token'])
        else:
            raise ValueError(f"Unsupported notification channel: {self.channel}")

    def send(self, text: str, destination: str = 'general') -> bool:
        assert self._backend is not None, 'Call connect() first.'
        if self.channel == 'slack':
            return self._backend.send_message(channel=destination, text=text)
        if self.channel == 'telegram':
            return self._backend.send_message(chat_id=destination, text=text)
        raise ValueError(f"Unsupported notification channel: {self.channel}")

    def send_file(self, file_path: str, destination: str = 'general', text: str = '') -> bool:
        assert self._backend is not None, 'Call connect() first.'
        if self.channel == 'slack':
            return self._backend.send_file(channel=destination, file_path=file_path, text=text)
        if self.channel == 'telegram':
            return self._backend.send_file(chat_id=destination, file_path=file_path, text=text)
        raise ValueError(f"Unsupported notification channel: {self.channel}")

    lib_demo_params = [
        {'key': 'a', 'name': 'Connect', 'function': 'connect', 'inputs': [
            {'label': 'Token', 'name': 'token', 'type': str, 'default': '', 'width': '150px'},
        ]},
        {'key': 'b', 'name': 'Send', 'function': 'send', 'inputs': [
            {'label': 'Text', 'name': 'text', 'type': str, 'default': '', 'width': '150px'},
            {'label': 'Destination', 'name': 'destination', 'type': str, 'default': 'general', 'width': '150px'},
        ]},
        {'key': 'c', 'name': 'Send File', 'function': 'send_file', 'inputs': [
            {'label': 'File Path', 'name': 'file_path', 'type': str, 'default': '', 'width': '150px'},
            {'label': 'Destination', 'name': 'destination', 'type': str, 'default': 'general', 'width': '150px'},
            {'label': 'Text', 'name': 'text', 'type': str, 'default': '', 'width': '150px'},
        ]},
    ]


if __name__ == '__main__':
    notifier = Notifier()
    utils.demo(notifier)
