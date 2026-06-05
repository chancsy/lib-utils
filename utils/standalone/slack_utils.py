import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions

utils = UtilityFunctions()
utils.exit_if_module_missing('slack_sdk')

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackUtils:
    def __init__(self):
        self._client: WebClient = None
        self.token: str = None

    # Connect using a Slack API token; stores the WebClient for subsequent calls.
    def connect(self, token: str) -> None:
        self.token = token
        self._client = WebClient(token=token)
        print(f'Connected to Slack.')

    # Send a plain-text message to a channel; channel must include the # prefix.
    def send_message(self, channel: str = 'general', text: str = '') -> bool:
        assert self._client is not None, 'Call connect() first.'
        try:
            response = self._client.chat_postMessage(channel=channel, text=text)
            print(f'Message sent: {response["ts"]}')
            return True
        except SlackApiError as e:
            print(f'Error sending message: {e}')
            return False

    lib_demo_params = [
        {'key': 'a', 'name': 'Connect', 'function': 'connect', 'inputs': [
            {'label': 'Token', 'name': 'token', 'type': str, 'default': '', 'width': '150px'},
        ]},
        {'key': 'b', 'name': 'Send Message', 'function': 'send_message', 'inputs': [
            {'label': 'Channel', 'name': 'channel', 'type': str, 'default': 'general', 'width': '150px'},
            {'label': 'Text', 'name': 'text', 'type': str, 'default': '', 'width': '150px'},
        ]},
    ]


if __name__ == '__main__':
    slack = SlackUtils()
    utils.demo(slack)
