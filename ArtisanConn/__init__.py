from io import BytesIO

from .SacpConfig import SACPConfig
from .SacpClient import SACPClient
from .SacpUtils import SACPUtils

class ArtisanError(Exception):
    """Base exception for Artisan errors"""
    pass

class ArtisanConn:
    """Snapmaker Artisan client"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.client = SACPClient(debug=debug)

    def connect(self, ip: str) -> None:
        """Connect to device"""
        self.client.connect(ip)

    def is_homed(self) -> bool:
        """Check if homing sequence is completed"""
        data = BytesIO()
        
        pack = self.client.send_command(1, 0x01, 0x30, data.getvalue())
        remaining_data = pack.data[1:]
        is_homing_required, remaining_data = SACPUtils.read_uint8(remaining_data)
        is_homed = (is_homing_required != 1)

        if self.debug:
            print(f"-- Is homed: {is_homed}")

        return is_homed

    def home(self) -> None:
        """Home the printer"""
        data = BytesIO()
        data.write(bytes([0x00]))
        
        self.client.send_command(1, 0x01, 0x35, data.getvalue())

    def execute_gcode(self, gcode: str, timeout: float = SACPConfig.DEFAULT_TIMEOUT) -> None:
        """Execute gcode"""
        data = BytesIO()
        SACPUtils.write_sacp_string(data, gcode)
        
        self.client.send_command(1, 0x01, 0x02, data.getvalue(), timeout)

    def take_photo(self, x: float = 0, y: float = 0, z: float = 0, feed_rate: float = 0,
                   photoQuality: float = 0) -> None:
        """Order to make photo (laser)"""
        data = BytesIO()
        SACPUtils.write_uint8(data, 0)
        SACPUtils.write_float(data, x)
        SACPUtils.write_float(data, y)
        SACPUtils.write_float(data, z)
        SACPUtils.write_uint16(data, feed_rate)
        SACPUtils.write_uint8(data, photoQuality)
        
        self.client.send_command(2, 0xB0, 0x04, data.getvalue(), 30)

    def get_photo(self) -> str:
        """Get photo"""
        data = BytesIO()
        SACPUtils.write_uint8(data, 0)
        
        pack = self.client.send_command(2, 0xB0, 0x05, data.getvalue())
        file_path = self.client.receive_file(pack, 30)
        return file_path


    def get_material_thickness(self, x: float = 0, y: float = 0, feed_rate: float = 0) -> float:
        """Get laser material thickness"""
        data = BytesIO()
        SACPUtils.write_float(data, x)
        SACPUtils.write_float(data, y)
        SACPUtils.write_uint16(data, feed_rate)
        
        pack = self.client.send_command(2, 0xB0, 0x09, data.getvalue(), 30)
        remaining_data = pack.data[1:]
        thickness, remaining_data = SACPUtils.read_float(remaining_data)

        if self.debug:
            print(f"-- Thickness is: {thickness}")

        return thickness

    def get_module_info(self, target_id: int) -> dict[str, any]:
        """Get module info"""
        data = BytesIO()
        pack = self.client.send_command(1, 0x01, 0x20, data.getvalue())
        remaining_data = pack.data[1:]
        arr_size, remaining_data = SACPUtils.read_uint8(remaining_data)

        if self.debug:
            print(f"-- Module count: {arr_size}")

        for i in range(arr_size):
            key, remaining_data = SACPUtils.read_uint8(remaining_data)
            module_id, remaining_data = SACPUtils.read_uint16(remaining_data)
            module_index, remaining_data = SACPUtils.read_uint8(remaining_data)
            module_state, remaining_data = SACPUtils.read_uint8(remaining_data)
            serial, remaining_data = SACPUtils.read_uint32(remaining_data)
            hw_ver, remaining_data = SACPUtils.read_uint8(remaining_data)
            sw_ver, remaining_data = SACPUtils.read_sacp_string(remaining_data)

            if (module_id == target_id):
                if self.debug:
                    print(f"-- Module info: key {key}; id {module_id}; idx {module_index}; state {module_state}; ser {serial}; hw {hw_ver}; sw {sw_ver}")

                return {
                    "key": key,
                    "module_id": module_id,
                    "module_index": module_index,
                    "module_state": module_state,
                    "serial": serial,
                    "hw_version": hw_ver,
                    "sw_version": sw_ver
                }
        
        raise ArtisanError(f"Module with id {target_id} is not found!")

    def get_laser_info(self, target_id: int) -> dict[str, any]:
        """Get laser module info"""
        module_info = self.get_module_info(target_id)
        key = module_info["key"]

        data = BytesIO()
        SACPUtils.write_uint8(data, key)

        pack = self.client.send_command(1, 0x12, 0x01, data.getvalue())
        remaining_data = pack.data[1:]

        key, remaining_data = SACPUtils.read_uint8(remaining_data)
        status, remaining_data = SACPUtils.read_uint8(remaining_data)
        focalLength, remaining_data = SACPUtils.read_float(remaining_data)
        platformHeight, remaining_data = SACPUtils.read_float(remaining_data)
        centerHeight, remaining_data = SACPUtils.read_float(remaining_data)

        if self.debug:
            print(f"-- Laser info: key {key}; status {status}; focal {focalLength}; platform {platformHeight}; center {centerHeight}")

        return {
            "key": key,
            "status": status,
            "focal_length": focalLength,
            "platform_height": platformHeight,
            "center_height": centerHeight
        }

    def set_work_origin(self, direction: chr, value: float) -> None:
        """Set machine origin separately"""
        dirs = {'x': 0, 'y': 1, 'z': 2}
        current_dir = dirs[direction]

        data = BytesIO()
        SACPUtils.write_uint8(data, 1)
        SACPUtils.write_uint8(data, current_dir)
        SACPUtils.write_float(data, value)
        
        self.client.send_command(1, 0x01, 0x32, data.getvalue())

    def set_laser_work_height(self, target_id: int, material_thickness: float = 0, feed_rate: float = 0, use_focal: bool = True) -> None:
        """Set laser work height"""
        laser_info = self.get_laser_info(target_id)
        focal_length = laser_info["focal_length"]
        platform_height = laser_info["platform_height"]

        z = platform_height + material_thickness

        if use_focal:
            z += focal_length
        
        command = f"G53 G0 Z{z}"

        if feed_rate > 0:
            command += f" F{feed_rate}"

        self.execute_gcode(command)
        self.set_work_origin('z', 0)
        self.execute_gcode("G54")
    
    def disconnect(self) -> None:
        """Disconnect from printer"""
        self.client.disconnect()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

# Convenience functions
def create_client(debug: bool = False) -> ArtisanConn:
    """Create a new Snapmaker Artisan client"""
    return ArtisanConn(debug=debug)
