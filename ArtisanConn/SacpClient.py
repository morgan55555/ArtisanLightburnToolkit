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