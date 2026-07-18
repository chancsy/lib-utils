import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()

import json
import shutil
import subprocess


class SopsUtils:
    """Wraps the `sops` CLI (https://github.com/getsops/sops) for decrypting secrets.

    Not a pip package — requires the `sops` and `age` binaries on PATH, and
    SOPS_AGE_KEY_FILE set to an age private key file. Encrypting/editing secrets
    is done directly via `sops <file>` in a terminal (opens decrypted in $EDITOR,
    re-encrypts on save), so no encrypt-side method is provided here.
    """

    def __init__(self):
        pass

    def _check_sops_available(self):
        if shutil.which('sops') is None:
            raise RuntimeError(
                "'sops' binary not found on PATH. Install SOPS: https://github.com/getsops/sops"
            )

    def decrypt(self, file_path: str) -> dict:
        self._check_sops_available()
        result = subprocess.run(
            ['sops', '-d', '--output-type', 'json', file_path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"sops decrypt failed for '{file_path}': {result.stderr.strip()}")
        return json.loads(result.stdout)

    lib_demo_params = [
        {'key': 'a', 'name': 'Decrypt File', 'function': 'decrypt', 'inputs': [
            {'label': 'File', 'name': 'file_path', 'type': str, 'default': 'secrets.sops.json', 'width': '200px'},
        ]},
    ]


if __name__ == '__main__':
    sops = SopsUtils()
    utils.demo(sops)
