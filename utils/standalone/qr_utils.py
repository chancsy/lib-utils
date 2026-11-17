import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()

import os


class QRUtils:
    def __init__(self):
        # Checked here (at construction) rather than at module-import time, so merely
        # importing this module doesn't require pyzbar/Pillow - only actually instantiating
        # QRUtils does. Cached on self so decode_qr() doesn't need its own import statements.
        utils.exit_if_module_missing('pyzbar')
        utils.exit_if_module_missing('PIL')
        from pyzbar.pyzbar import decode
        from PIL import Image
        self._decode = decode
        self._Image = Image

    # Decode the first QR code / barcode in an image (a PIL image or an image file path).
    # Returns its text, or None if nothing was found.
    def decode_qr(self, qr_image):
        if isinstance(qr_image, (str, os.PathLike)):
            qr_image = self._Image.open(qr_image)
        decoded_objects = self._decode(qr_image)
        if decoded_objects:
            return decoded_objects[0].data.decode('utf-8')
        return None

    lib_demo_params = [
        {'key': 'a', 'name': 'Decode QR from image file', 'function': 'decode_qr', 'inputs': [
            {'label': 'Image file', 'name': 'qr_image', 'type': str, 'default': 'qr.png', 'width': '250px'},
        ]},
    ]


if __name__ == '__main__':
    # python qr_utils.py <image_file>   decode and print
    # python qr_utils.py                interactive demo
    if len(sys.argv) > 1:
        qr_file_path = sys.argv[1]
        if not os.path.exists(qr_file_path):
            print(f"\nUsage: python qr_utils.py [image_file]")
            print(f"File '{qr_file_path}' not found. Please specify an image file.")
            sys.exit(1)
        print(f'Decoded QR: {QRUtils().decode_qr(qr_file_path)}')
    else:
        utils.demo(QRUtils())
