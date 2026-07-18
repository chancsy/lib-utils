import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()
utils.exit_if_module_missing('gspread')

import gspread


class GSheets:
    """Thin wrapper around gspread for reading/writing a Google Sheet via a service account."""

    def __init__(self):
        self._client = None

    def open_sheet(self, sheet_id: str, service_account_json: str):
        self._client = gspread.service_account(filename=service_account_json)
        return self._client.open_by_key(sheet_id)

    def append_row(self, sheet, worksheet_name: str, values: list):
        ws = sheet.worksheet(worksheet_name)
        ws.append_row(values)

    def update_cell_range(self, sheet, worksheet_name: str, cell_range: str, values: list):
        ws = sheet.worksheet(worksheet_name)
        ws.update(cell_range, values)

    lib_demo_params = [
        {'key': 'a', 'name': 'Open Sheet', 'function': 'open_sheet', 'inputs': [
            {'label': 'Sheet ID', 'name': 'sheet_id', 'type': str, 'default': '', 'width': '200px'},
            {'label': 'Service account JSON', 'name': 'service_account_json', 'type': str, 'default': 'service_account.json', 'width': '200px'},
        ]},
    ]


if __name__ == '__main__':
    sheets = GSheets()
    utils.demo(sheets)
