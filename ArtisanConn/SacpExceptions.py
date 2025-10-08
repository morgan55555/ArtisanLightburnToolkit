class SACPError(Exception):
    """Base exception for SACP protocol errors"""
    pass

class InvalidSACPError(SACPError):
    """Data doesn't look like SACP packet"""
    pass

class InvalidSACPVerError(SACPError):
    """SACP version mismatch"""
    pass

class InvalidChecksumError(SACPError):
    """SACP checksum doesn't match data"""
    pass

class InvalidSizeError(SACPError):
    """SACP package is too short"""
    pass

class FileTransferError(SACPError):
    """File transfer related errors"""
    pass