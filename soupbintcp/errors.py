from enum import Enum


class LoginRejectCode(Enum):
    NOT_AUTHORIZED = b"A"
    SESSION_NOT_AVAILABLE = b"S"


class HeartbeatTimeoutError(Exception):
    ...


class LoginRejectedError(Exception):
    def __init__(self, code: bytes):
        self.code = LoginRejectCode(code)

    def __str__(self):
        if self.code == LoginRejectCode.NOT_AUTHORIZED:
            return "There was an invalid username and password\
                     combination in the Login Request Message."
        elif self.code == LoginRejectCode.SESSION_NOT_AVAILABLE:
            return "The Requested Session in the Login Request Packet\
                     was either invalid or not available."
