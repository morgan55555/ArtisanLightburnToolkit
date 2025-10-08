import struct
from typing import NamedTuple

from .SacpExceptions import InvalidSizeError, InvalidSACPError, InvalidSACPVerError, InvalidChecksumError

class SACPPack(NamedTuple):
    """SACP packet structure"""
    receiver_id: int
    sender_id: int
    attribute: int
    sequence: int
    command_set: int
    command_id: int
    data: bytes

    @staticmethod
    def _head_checksum(data: bytes) -> int:
        """Calculate header checksum"""
        crc = 0
        poly = 7
        for byte in data:
            for j in range(8):
                bit = (byte >> (7 - j)) & 0x01 == 1
                c07 = (crc >> 7) & 0x01 == 1
                crc = (crc << 1) & 0xFF
                if (not c07 and bit) or (c07 and not bit):
                    crc ^= poly
        return crc & 0xFF

    @staticmethod
    def _u16_checksum(package_data: bytes, length: int) -> int:
        """Calculate 16-bit checksum"""
        check_num = 0
        if length > 0:
            for i in range(0, length - 1, 2):
                check_num += (package_data[i] << 8) | package_data[i + 1]
                check_num &= 0xFFFFFFFF
            
            if length % 2 != 0:
                check_num += package_data[length - 1]
        
        while check_num > 0xFFFF:
            check_num = ((check_num >> 16) & 0xFFFF) + (check_num & 0xFFFF)
        
        check_num = ~check_num
        return check_num & 0xFFFF

    def encode(self) -> bytes:
        """Encode SACP packet to bytes"""
        data_len = len(self.data) + 6 + 2  # +6 for header fields, +2 for data checksum
        result = bytearray(15 + len(self.data))
        
        # Header
        result[0] = 0xAA
        result[1] = 0x55
        struct.pack_into('<H', result, 2, data_len)
        result[4] = 0x01  # SACP version
        result[5] = self.receiver_id
        result[6] = self._head_checksum(result[:6])
        result[7] = self.sender_id
        result[8] = self.attribute
        struct.pack_into('<H', result, 9, self.sequence)
        result[11] = self.command_set
        result[12] = self.command_id
        
        # Data
        if self.data:
            result[13:13 + len(self.data)] = self.data
        
        # Data checksum
        checksum_data = result[7:13 + len(self.data)]
        data_checksum = self._u16_checksum(checksum_data, len(self.data) + 6)
        struct.pack_into('<H', result, 13 + len(self.data), data_checksum)
        
        return bytes(result)

    @classmethod
    def decode(cls, data: bytes) -> 'SACPPack':
        """Decode bytes to SACP packet"""
        if len(data) < 13:
            raise InvalidSizeError("Packet too short")
        
        if data[0] != 0xAA or data[1] != 0x55:
            raise InvalidSACPError("Invalid SACP header")
        
        data_len = struct.unpack_from('<H', data, 2)[0]
        if data_len != len(data) - 7:
            raise InvalidSizeError(f"Data length mismatch: {data_len} != {len(data) - 7}")
        
        if data[4] != 0x01:
            raise InvalidSACPVerError("Invalid SACP version")
        
        head_checksum = cls._head_checksum(data[:6])
        if head_checksum != data[6]:
            raise InvalidChecksumError("Header checksum mismatch")
        
        # Verify data checksum
        expected_data_checksum = struct.unpack_from('<H', data, len(data) - 2)[0]
        checksum_data = data[7:len(data) - 2]
        actual_data_checksum = cls._u16_checksum(checksum_data, data_len - 2)
        
        if expected_data_checksum != actual_data_checksum:
            raise InvalidChecksumError("Data checksum mismatch")
        
        return cls(
            receiver_id=data[5],
            sender_id=data[7],
            attribute=data[8],
            sequence=struct.unpack_from('<H', data, 9)[0],
            command_set=data[11],
            command_id=data[12],
            data=data[13:len(data) - 2]
        )