import struct
from io import BytesIO

class SACPUtils:
    """SACP protocol client"""

    @staticmethod
    def write_uint8(buffer: BytesIO, value: int) -> None:
        """Write unsigned 8-bit integer"""
        buffer.write(struct.pack('<B', value))
    
    @staticmethod
    def write_uint16(buffer: BytesIO, value: int) -> None:
        """Write unsigned 16-bit integer"""
        buffer.write(struct.pack('<H', value))

    @staticmethod
    def write_int32(buffer: BytesIO, value: float) -> None:
        """Write signed 32-bit integer"""
        buffer.write(struct.pack('<i', value))

    @staticmethod
    def write_uint32(buffer: BytesIO, value: float) -> None:
        """Write unsigned 32-bit integer"""
        buffer.write(struct.pack('<I', value))

    @staticmethod
    def write_float(buffer: BytesIO, value: float) -> None:
        """Write 32-bit float"""
        float_to_int_val = int(value * 1000)
        SACPUtils.write_int32(buffer, float_to_int_val)
    
    @staticmethod
    def write_sacp_string(buffer: BytesIO, s: str) -> None:
        """Write string with length prefix"""
        encoded = s.encode('utf-8')
        buffer.write(struct.pack('<H', len(encoded)))
        buffer.write(encoded)
    
    @staticmethod
    def write_sacp_bytes(buffer: BytesIO, data: bytes) -> None:
        """Write bytes with length prefix"""
        buffer.write(struct.pack('<H', len(data)))
        buffer.write(data)
    
    @staticmethod
    def write_le(buffer: BytesIO, value, fmt: str) -> None:
        """Write little-endian value"""
        buffer.write(struct.pack('<' + fmt, value))

    @staticmethod
    def read_uint8(data: bytes) -> tuple[float, bytes]:
        """Read unsigned 8-bit integer"""
        result = struct.unpack('<B', data[:1])[0]
        remaining_data = data[1:]
        return result, remaining_data

    @staticmethod
    def read_uint16(data: bytes) -> tuple[float, bytes]:
        """Read unsigned 16-bit integer"""
        result = struct.unpack('<H', data[:2])[0]
        remaining_data = data[2:]
        return result, remaining_data

    @staticmethod
    def read_uint32(data: bytes) -> tuple[float, bytes]:
        """Read unsigned 32-bit integer"""
        result = struct.unpack('<I', data[:4])[0]
        remaining_data = data[4:]
        return result, remaining_data

    @staticmethod
    def read_float(data: bytes) -> tuple[float, bytes]:
        """Read 32-bit float"""
        raw_float, remaining_data = SACPUtils.read_uint32(data)
        result = raw_float / 1000
        return result, remaining_data

    @staticmethod
    def read_sacp_string(data: bytes) -> tuple[str, bytes]:
        """Read string with length prefix"""
        str_length = struct.unpack('<H', data[:2])[0]
        str_bytes = data[2:2 + str_length]
        result = str_bytes.decode('utf-8')
        remaining_data = data[2 + str_length:]
        return result, remaining_data