import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions

utils = UtilityFunctions()

import base64
import hashlib
import os


class Cryptography:
    def __init__(self):
        # Checked here (at construction) rather than at module-import time, so merely
        # importing this module doesn't require cryptography - only actually instantiating
        # Cryptography does. Cached on self so the methods below don't need their own
        # import statements.
        utils.exit_if_module_missing('cryptography')
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        self._Fernet = Fernet
        self._hashes = hashes
        self._PBKDF2HMAC = PBKDF2HMAC

    # Derive a Fernet-compatible key from a password using PBKDF2-SHA256.
    # Returns (salt_hex, key_str); pass salt=bytes.fromhex(salt_hex) to re-derive the same key.
    def derive_key(self, password: str, salt: bytes = None, length: int = 32, iterations: int = 480000) -> tuple[str, str]:
        if salt is None:
            salt = os.urandom(16)
        kdf = self._PBKDF2HMAC(
            algorithm=self._hashes.SHA256(),
            length=length,
            salt=salt,
            iterations=iterations,
        )
        return salt.hex(), base64.urlsafe_b64encode(kdf.derive(password.encode())).decode()

    # Encrypt a plaintext message with the given Fernet key; returns base64 ciphertext string.
    def encrypt(self, key: str | bytes, message: str) -> str:
        if isinstance(key, str):
            key = key.encode()
        return self._Fernet(key).encrypt(message.encode()).decode()

    # Decrypt a base64 ciphertext string or bytes with the given Fernet key; returns plaintext or '' on failure.
    def decrypt(self, key: str | bytes, message: str | bytes) -> str:
        if isinstance(key, str):
            key = key.encode()
        if isinstance(message, str):
            message = message.encode()
        try:
            return self._Fernet(key).decrypt(message).decode()
        except Exception:
            return ''

    # Encrypt with a password directly; returns 'salt_hex:fernet_token' as one paste-able string.
    def encrypt_with_password(self, password: str, message: str) -> str:
        salt_hex, key = self.derive_key(password)
        return f'{salt_hex}:{self.encrypt(key, message)}'

    # Reverse of encrypt_with_password(); returns '' on wrong password or corrupt input (same
    # failure convention as decrypt()).
    def decrypt_with_password(self, password: str, blob: str) -> str:
        salt_hex, _, token = blob.partition(':')
        if not token:
            return ''
        _, key = self.derive_key(password, salt=bytes.fromhex(salt_hex))
        return self.decrypt(key, token)

    # Return a hex digest of a string using any algorithm supported by hashlib.
    def get_hash(self, message: str, method: str = 'md5') -> str:
        method_norm = method.strip().lower().replace('-', '_')
        supported = {name.lower().replace('-', '_') for name in hashlib.algorithms_available}
        if method_norm not in supported:
            raise ValueError(f'Unsupported hash method: {method}.')
        hasher = hashlib.new(method_norm)
        hasher.update(message.encode())
        return hasher.hexdigest()

    lib_demo_params = [
        {'key': 'a', 'name': 'Derive key', 'function': 'derive_key', 'inputs': [
            {'label': 'Password',   'name': 'password',   'type': str, 'password': True, 'default': None, 'width': '80px'},
            {'label': 'Length',     'name': 'length',     'type': int, 'default': 32, 'width': '80px'},
            {'label': 'Iterations', 'name': 'iterations', 'type': int, 'default': 480000, 'width': '80px'},
        ], 'fill_targets': {'Encrypt.key': 1, 'Decrypt.key': 1}},
        {'key': 'b', 'name': 'Encrypt', 'function': 'encrypt', 'inputs': [
            {'label': 'Key', 'name': 'key', 'type': str, 'default': '', 'width': '150px'},
            {'label': 'Message', 'name': 'message', 'type': str, 'default': 'Test message', 'width': '150px'},
        ], 'fill_targets': {'Decrypt.message': True}},
        {'key': 'c', 'name': 'Decrypt', 'function': 'decrypt', 'inputs': [
            {'label': 'Key', 'name': 'key', 'type': str, 'default': '', 'width': '150px'},
            {'label': 'Message', 'name': 'message', 'type': str, 'default': '', 'width': '150px'},
        ]},
        {'key': 'd', 'name': 'Get Hash', 'function': 'get_hash', 'inputs': [
            {'label': 'Message', 'name': 'message', 'type': str, 'default': 'Test message', 'width': '150px'},
            {'label': 'Method', 'name': 'method', 'options': sorted(hashlib.algorithms_available), 'default': 'md5', 'width': '160px'},
        ]},
        {'key': 'e', 'name': 'Encrypt with password', 'function': 'encrypt_with_password', 'inputs': [
            {'label': 'Password', 'name': 'password', 'type': str, 'password': True, 'default': None, 'width': '80px'},
            {'label': 'Message', 'name': 'message', 'type': str, 'default': 'Test message', 'width': '150px'},
        ], 'fill_targets': {'Decrypt with password.blob': True}},
        {'key': 'f', 'name': 'Decrypt with password', 'function': 'decrypt_with_password', 'inputs': [
            {'label': 'Password', 'name': 'password', 'type': str, 'password': True, 'default': None, 'width': '80px'},
            {'label': 'Blob', 'name': 'blob', 'type': str, 'default': '', 'width': '150px'},
        ]},
    ]


if __name__ == '__main__':
    crypto = Cryptography()
    utils.demo(crypto)
