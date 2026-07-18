import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions

utils = UtilityFunctions()
utils.exit_if_module_missing('requests')

import requests


class TelegramUtils:
    """Thin wrapper over Telegram's plain HTTP Bot API — no dedicated SDK
    needed for one-way notifications (sendMessage/sendDocument), unlike
    Slack's official slack_sdk. chat_id is Telegram's equivalent of a Slack
    channel — passed per-call, not at connect() time, so this matches
    SlackUtils' method shapes exactly (connect(token) only).
    """

    BASE_URL = 'https://api.telegram.org'

    def __init__(self):
        self.token: str = None

    # Connect using a bot token from @BotFather; no network call yet — the
    # token is only actually exercised on the first send.
    def connect(self, token: str) -> None:
        self.token = token
        print('Connected to Telegram.')

    # Send a plain-text message to a chat_id.
    def send_message(self, chat_id: str = '', text: str = '') -> bool:
        assert self.token is not None, 'Call connect() first.'
        try:
            resp = requests.post(
                f'{self.BASE_URL}/bot{self.token}/sendMessage',
                data={'chat_id': chat_id, 'text': text},
            )
            result = resp.json()
            if not result.get('ok'):
                print(f'Error sending message: {result}')
                return False
            print(f'Message sent: {result["result"]["message_id"]}')
            return True
        except requests.RequestException as e:
            print(f'Error sending message: {e}')
            return False

    # Upload a file to a chat_id, with optional caption text — Telegram's
    # `caption` renders in the same message as the file (like Slack's
    # initial_comment), not as a separate message.
    def send_file(self, chat_id: str = '', file_path: str = '', text: str = '') -> bool:
        assert self.token is not None, 'Call connect() first.'
        try:
            with open(file_path, 'rb') as f:
                resp = requests.post(
                    f'{self.BASE_URL}/bot{self.token}/sendDocument',
                    data={'chat_id': chat_id, 'caption': text},
                    files={'document': f},
                )
            result = resp.json()
            if not result.get('ok'):
                print(f'Error sending file: {result}')
                return False
            print(f'File sent: {result["result"]["message_id"]}')
            return True
        except requests.RequestException as e:
            print(f'Error sending file: {e}')
            return False

    lib_demo_params = [
        {'key': 'a', 'name': 'Connect', 'function': 'connect', 'inputs': [
            {'label': 'Token', 'name': 'token', 'type': str, 'default': '', 'width': '150px'},
        ]},
        {'key': 'b', 'name': 'Send Message', 'function': 'send_message', 'inputs': [
            {'label': 'Chat ID', 'name': 'chat_id', 'type': str, 'default': '', 'width': '150px'},
            {'label': 'Text', 'name': 'text', 'type': str, 'default': '', 'width': '150px'},
        ]},
        {'key': 'c', 'name': 'Send File', 'function': 'send_file', 'inputs': [
            {'label': 'Chat ID', 'name': 'chat_id', 'type': str, 'default': '', 'width': '150px'},
            {'label': 'File Path', 'name': 'file_path', 'type': str, 'default': '', 'width': '150px'},
            {'label': 'Text', 'name': 'text', 'type': str, 'default': '', 'width': '150px'},
        ]},
    ]


if __name__ == '__main__':
    telegram = TelegramUtils()
    utils.demo(telegram)
