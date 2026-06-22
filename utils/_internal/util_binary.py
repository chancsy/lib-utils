import base64
import struct


class UtilityBinaryMixin:
    data_type_properties = {
        'uint8': (0, 255, int, 1),
        'uint16': (0, 65535, int, 2),
        'uint32': (0, 4294967295, int, 4),
        'int8': (-128, 127, int, 1),
        'int16': (-32768, 32767, int, 2),
        'int32': (-2147483648, 2147483647, int, 4),
        'float': (None, None, float, 4),
        'bytearray': (None, None, bytearray, 4),
        'bytes': (None, None, bytes, 1),
        'string': (None, None, str, 1),
    }

    def is_data_type_valid(self, data_type, value):
        if data_type not in self.data_type_properties:
            return False
        min_val, max_val, expected_type, _ = self.data_type_properties[data_type]
        if not isinstance(value, expected_type):
            return False

        if not (expected_type == bytes or expected_type == bytearray or expected_type == str):
            if min_val is not None and (value < min_val or value > max_val):
                return False
        return True

    def get_data_type_length(self, data_type):
        return self.data_type_properties.get(data_type, (None, None, None, 0))[3]

    def _get_format(self, data_type, endian):
        formats = {
            'double': 'd',
            'float': 'f',
            'half': 'e',
            'uint32': 'I',
            'int32': 'i',
            'uint16': 'H',
            'int16': 'h',
            'uint8': 'B'
        }
        return f'>{formats[data_type]}' if endian == 'BE' else f'<{formats[data_type]}'

    def _check_length(self, num_bytes, expected_length):
        if len(num_bytes) != expected_length:
            raise ValueError(f'Requires a buffer of {expected_length} bytes, buffer is {len(num_bytes)} bytes long.')

    def _generate_conversion_functions(self):
        data_types = {
            'double': 8,
            'float': 4,
            'half': 2,
            'uint32': 4,
            'int32': 4,
            'uint16': 2,
            'int16': 2,
            'uint8': 1
        }

        def _create_to_bytes_function(data_type):
            def to_bytes(num, endian='BE'):
                return struct.pack(self._get_format(data_type, endian), num)
            return to_bytes

        def _create_from_bytes_function(data_type, length):
            def from_bytes(num_bytes, endian='BE'):
                self._check_length(num_bytes, length)
                return struct.unpack(self._get_format(data_type, endian), num_bytes)[0]
            return from_bytes

        for data_type, length in data_types.items():
            setattr(self, f'{data_type}_to_bytes', _create_to_bytes_function(data_type))
            setattr(self, f'bytes_to_{data_type}', _create_from_bytes_function(data_type, length))

        # list of the functions created:
        # double_to_bytes, bytes_to_double
        # float_to_bytes, bytes_to_float
        # half_to_bytes, bytes_to_half
        # uint32_to_bytes, bytes_to_uint32
        # int32_to_bytes, bytes_to_int32
        # uint16_to_bytes, bytes_to_uint16
        # int16_to_bytes, bytes_to_int16
        # uint8_to_bytes, bytes_to_uint8

    # Convert float to binary32 (single precision) format (caution - lose precision)
    def float_to_single(self, x):
        return struct.unpack('f', struct.pack('f', x))[0]

    # Convert float to binary16 (half precision) format (caution - lose precision)
    def float_to_half(self, x):
        return struct.unpack('e', struct.pack('e', x))[0]

    def get_bit(self, value, bit_index):
        return value & (1 << bit_index)

    def get_normalized_bit(self, value, bit_index):
        return (value >> bit_index) & 1

    def set_bit(self, value, bit_index):
        return value | (1 << bit_index)

    def clear_bit(self, value, bit_index):
        return value & ~(1 << bit_index)

    def toggle_bit(self, value, bit_index):
        return value ^ (1 << bit_index)

    def bytes_to_hex_str(self, bytes, prefix='', delim=''):
        if bytes is None:
            return ''
        return delim.join([f'{prefix}{x:02X}' for x in bytes])

    def hex_str_to_bytes(self, hex_string, delim=''):
        hex_string = hex_string.replace(delim, '')
        hex_string = hex_string.replace('0x', '').replace('0X', '')
        return bytes.fromhex(hex_string)

    def string_to_bytes(self, string):
        return string.encode()

    def bytes_to_string(self, bytes):
        return bytes.decode(errors='replace')

    # Encode a text string to a Base64 bytes object.
    def base64_encode(self, text: str) -> bytes:
        return base64.b64encode(text.encode('utf-8'))

    # Decode a Base64 bytes or string back to a UTF-8 text string.
    def base64_decode(self, data: bytes | str) -> str:
        if isinstance(data, str):
            data = data.encode('utf-8')
        return base64.b64decode(data).decode('utf-8')

    def dec_to_hex_str(self, dec, prefix='', delim='', pad=True, byte_size=1):
        hex_str = f'{dec:0{byte_size*2}X}' if byte_size else f'{dec:X}'

        if pad and len(hex_str) % 2:
            hex_str = '0' + hex_str

        if delim:
            hex_str = delim.join([hex_str[max(i-2, 0):i] for i in range(len(hex_str), 0, -2)][::-1])

        if prefix:
            if delim:
                hex_str = delim.join([f'{prefix}{x}' for x in hex_str.split(delim)])
            else:
                hex_str = f'{prefix}{hex_str}'
        return hex_str

    def crc32_jamcrc(self, data_bytes):
        import zlib
        crc32 = zlib.crc32(data_bytes)
        crc32_jamcrc = 2**32-1 - crc32
        return self.uint32_to_bytes(crc32_jamcrc, endian='LE')

    def XOR_checksum(self, bytes):
        checksum = 0
        for byte in bytes:
            checksum ^= byte
        return checksum

    def float_to_str_sf(self, num, sf):
        format_string = "{:." + str(sf) + "g}"
        return format_string.format(num)

    def is_integer(self, s):
        try:
            float_val = float(s)
            return float_val.is_integer()
        except ValueError:
            return False

    def int_whole_number(self, s):
        try:
            return int(s)
        except ValueError:
            try:
                float_val = float(s)
                if float_val.is_integer():
                    return int(float_val)
            except ValueError:
                return None

    def is_float(self, s):
        try:
            float(s)
            return True
        except ValueError:
            return False
