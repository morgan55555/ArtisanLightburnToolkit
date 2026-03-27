import socket
import struct
from typing import Optional
from io import BytesIO

from .SacpConfig import SACPConfig
from .SacpExceptions import SACPError, InvalidSizeError, FileTransferError
from .SacpUtils import SACPUtils
from .SacpPack import SACPPack

class SACPClient:
    """SACP protocol client"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.conn: Optional[socket.socket] = None
        self.sequence = 2
    
    def connect(self, ip: str, timeout: float = SACPConfig.DEFAULT_TIMEOUT) -> None:
        """Connect to SACP device"""
        if self.debug:
            print(f"-- Connecting to {ip}:{SACPConfig.DEFAULT_PORT}")
        
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.settimeout(timeout)
        self.conn.connect((ip, SACPConfig.DEFAULT_PORT))
        
        # Send hello packet
        hello_data = bytes([
            11, 0, ord('s'), ord('m'), ord('2'), ord('u'), ord('p'), ord('l'), 
            ord('o'), ord('a'), ord('d'), ord('e'), ord('r'), 0, 0, 0, 0
        ])
        
        hello_packet = SACPPack(
            receiver_id=2,
            sender_id=0,
            attribute=0,
            sequence=1,
            command_set=0x01,
            command_id=0x05,
            data=hello_data
        )
        
        self.conn.send(hello_packet.encode())
        
        # Wait for hello response
        while True:
            response = self._read(timeout)
            if response.command_set == 1 and response.command_id == 5:
                break
        
        if self.debug:
            print("-- Connected to printer")
    
    def _read(self, timeout: float) -> SACPPack:
        """Read SACP packet from connection"""
        if not self.conn:
            raise SACPError("Not connected")
        
        self.conn.settimeout(timeout)
        
        # Read header (4 bytes)
        header = self._recv_exact(4)
        if len(header) != 4:
            raise InvalidSizeError("Failed to read complete header")
        
        data_len = struct.unpack_from('<H', header, 2)[0]
        
        # Read remaining data
        remaining = self._recv_exact(data_len + 3)
        if len(remaining) != data_len + 3:
            raise InvalidSizeError("Failed to read complete packet")
        
        full_packet = header + remaining
        return SACPPack.decode(full_packet)
    
    def _recv_exact(self, size: int) -> bytes:
        """Receive exactly size bytes"""
        if not self.conn:
            raise SACPError("Not connected")
        
        data = b''
        while len(data) < size:
            chunk = self.conn.recv(size - len(data))
            if not chunk:
                raise ConnectionError("Connection closed")
            data += chunk
        return data

    def receive_file(self, pack: SACPPack, timeout: float = SACPConfig.DEFAULT_TIMEOUT) -> str:
        filename, remaining_data = SACPUtils.read_sacp_string(pack.data)
        file_length, remaining_data = SACPUtils.read_uint32(remaining_data)
        total_chunks, remaining_data = SACPUtils.read_uint16(remaining_data)
        md5_hex_str, remaining_data = SACPUtils.read_sacp_string(remaining_data)

        if self.debug:
            print(f"-- File transfer started: {filename}, size: {file_length}, chunks: {total_chunks}, md5: {md5_hex_str}")

        received_data = open(filename, "wb")
        chunk_index = 0
        tries = total_chunks + 5

        try:
            while chunk_index < total_chunks:
                data = BytesIO()
                SACPUtils.write_sacp_string(data, md5_hex_str)
                SACPUtils.write_uint16(data, chunk_index)

                response = self.send_command(2, 0xB0, 0x01, data.getvalue())

                if response.data[0] == 0:
                    remaining = response.data[1:]
                    md5_received, remaining = SACPUtils.read_sacp_string(remaining)
                    chunk_index_received, remaining = SACPUtils.read_uint16(remaining)
                    chunk_length, remaining = SACPUtils.read_uint16(remaining)
                    chunk_data = remaining[:chunk_length]

                    if chunk_index_received != chunk_index:
                        raise FileTransferError(f"Failed to receive chunk {chunk_index}, got {chunk_index_received} instead")

                    if self.debug:
                        print(f"-- Received chunk: {chunk_index_received} ({chunk_index_received+1}/{total_chunks}), size: {chunk_length}")
                        print(f"-- Chunk contains: {str(chunk_data)[:128]}...")

                    received_data.write(chunk_data)
                    chunk_index = chunk_index + 1
                
                if tries <= 0:
                    raise FileTransferError(f"Failed to receive file {filename}")
                
                tries -= 1

        finally:
            received_data.close()

        data = BytesIO()
        data.write(bytes([0x00]))
        SACPUtils.write_sacp_string(data, filename)
        SACPUtils.write_sacp_string(data, md5_hex_str)
        self.send_command(2, 0xB0, 0x02, data.getvalue())

        if self.debug:
            print(f"-- Received file: {filename}")
        
        return filename

    def send_command(self, receiver_id: int, command_set: int, command_id: int, 
                                  data: bytes, timeout: float = SACPConfig.DEFAULT_TIMEOUT) -> SACPPack:
        """
        Send command and return the response packet
        
        This is used for commands that return data in response
        """
        if not self.conn:
            raise SACPError("Not connected")
        
        self.sequence += 1
        
        packet = SACPPack(
            receiver_id=receiver_id,
            sender_id=0,
            attribute=0,
            sequence=self.sequence,
            command_set=command_set,
            command_id=command_id,
            data=data
        )
        
        self.conn.settimeout(timeout)
        self.conn.send(packet.encode())
        
        if self.debug:
            print(f"-- Sequence: {self.sequence} Sent command: Set: {command_set} ID: {command_id} Data: {data.hex()}")
        
        # Wait for response and return it
        while True:
            response = self._read(timeout)

            if response.data[:1] == b'\xc9':
                raise SACPError("Printer reported error!")
            
            if self.debug:
                print(f"-- Got reply from printer: {str(response)[:128]}...")
            
            if ((response.sequence == self.sequence and 
                response.command_set == command_set and 
                response.command_id == command_id) or
                response.command_id == 0):
                return response

    def send_file(self, filename: str, file_data: bytes, timeout: float = SACPConfig.DEFAULT_TIMEOUT) -> None:
        """
        Send file to SACP device (upload G-code or similar)
        """
        if not self.conn:
            raise SACPError("Not connected")

        if self.debug:
            print(f"-- Starting file upload: {filename}, size: {len(file_data)}")

        SACP_data_len = SACPConfig.DATA_CHUNK_SIZE

        package_count = (len(file_data) // SACP_data_len) + (1 if len(file_data) % SACP_data_len else 0)
        import hashlib
        md5hash = hashlib.md5(file_data).digest()
        md5_hex = md5hash.hex()

        # Prepare and send start upload packet (B0 00)
        data = BytesIO()
        SACPUtils.write_sacp_string(data, filename)
        SACPUtils.write_uint32(data, len(file_data))
        SACPUtils.write_uint16(data, package_count)
        SACPUtils.write_sacp_string(data, md5_hex)

        start_packet = SACPPack(
            receiver_id=2,
            sender_id=0,
            attribute=0,
            sequence=1,
            command_set=0xB0,
            command_id=0x00,
            data=data.getvalue()
        )
        self.conn.send(start_packet.encode())

        chunk_index = 0
        while True:
            response = self._read(timeout)

            if response.command_set == 0xB0 and response.command_id == 0x00:
                # Ignore unknown B0/00 reply
                continue

            elif response.command_set == 0xB0 and response.command_id == 0x01:
                # Device requests a chunk
                if len(response.data) < 4:
                    raise FileTransferError("Invalid chunk request packet")

                # Parse request: md5 string + chunk_index (uint16)
                req_md5, remaining = SACPUtils.read_sacp_string(response.data)
                req_chunk, _ = SACPUtils.read_uint16(remaining)

                if req_chunk >= package_count:
                    raise FileTransferError(f"Requested invalid chunk {req_chunk}")

                # Prepare chunk data
                start = req_chunk * SACP_data_len
                end = start + SACP_data_len if req_chunk < package_count - 1 else len(file_data)
                chunk_data = file_data[start:end]

                if self.debug:
                    perc = (req_chunk + 1) / package_count * 100
                    print(f"-- Sending chunk {req_chunk + 1}/{package_count} ({perc:.1f}%) size: {len(chunk_data)}")

                # Build response (B0 01)
                resp_data = BytesIO()
                resp_data.write(b'\x00')  # success
                SACPUtils.write_sacp_string(resp_data, md5_hex)
                SACPUtils.write_uint16(resp_data, req_chunk)
                SACPUtils.write_uint16(resp_data, len(chunk_data))  # or write_sacp_bytes if helper exists
                resp_data.write(chunk_data)

                resp_packet = SACPPack(
                    receiver_id=2,
                    sender_id=0,
                    attribute=1,  # important: response attribute
                    sequence=response.sequence,
                    command_set=0xB0,
                    command_id=0x01,
                    data=resp_data.getvalue()
                )
                self.conn.send(resp_packet.encode())

            elif response.command_set == 0xB0 and response.command_id == 0x02:
                # Upload finished confirmation
                if len(response.data) == 1 and response.data[0] == 0x00:
                    if self.debug:
                        print(f"-- File upload finished: {filename}")
                    return
                else:
                    raise FileTransferError("Upload finished with error")
            else:
                # Unexpected packet — continue waiting
                continue

        raise FileTransferError("File upload did not complete")

    def disconnect(self, timeout: float = SACPConfig.DEFAULT_TIMEOUT) -> None:
        """Disconnect from printer"""
        if not self.conn:
            return
        
        disconnect_packet = SACPPack(
            receiver_id=2,
            sender_id=0,
            attribute=0,
            sequence=1,
            command_set=0x01,
            command_id=0x06,
            data=b''
        )
        
        self.conn.settimeout(timeout)
        self.conn.send(disconnect_packet.encode())
        self.conn.close()
        self.conn = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.disconnect()