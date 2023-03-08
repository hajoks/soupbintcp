from ctypes import c_char, c_uint16
from dataclasses import dataclass, field
from enum import Enum

from cdataclass import BigEndianCDataMixIn, meta


class PacketType(Enum):
    SEQUENCED_DATA = b"S"
    UNSEQUENCED_DATA = b"U"
    LOGIN_REQUEST = b"L"
    LOGIN_ACCEPTED = b"A"
    LOGIN_REJECTED = b"J"
    LOGOUT_REQUEST = b"O"
    CLIENT_HEARTBEAT = b"R"
    SERVER_HEARTBEAT = b"H"
    END_OF_SESSION = b"Z"
    DEBUG = b"+"


@dataclass
class Packet:
    length: int
    type: PacketType
    payload: bytes


@dataclass
class Header(BigEndianCDataMixIn):
    packet_length: int = field(metadata=meta(c_uint16))
    packet_type: bytes = field(metadata=meta(c_char))

    @property
    def payload_length(self):
        return self.packet_length - 1


@dataclass
class LoginRequest(BigEndianCDataMixIn):
    username: bytes = field(metadata=meta(c_char * 6))
    password: bytes = field(metadata=meta(c_char * 10))
    requested_session: bytes = field(metadata=meta(c_char * 10))
    requested_sequence_number: bytes = field(metadata=meta(c_char * 20))

    @classmethod
    def new(
        cls,
        username: str,
        password: str,
        requested_session: str,
        requested_sequence_number: int,
    ):
        return cls(
            username.ljust(6).encode(),
            password.ljust(10).encode(),
            requested_session.ljust(10).encode(),
            str(requested_sequence_number).rjust(20).encode(),
        )


@dataclass
class LoginAccepted(BigEndianCDataMixIn):
    session: bytes = field(metadata=meta(c_char * 10))
    sequence_number: bytes = field(metadata=meta(c_char * 20))

    @classmethod
    def new(
        cls,
        session: str,
        sequence_number: int,
    ):
        return cls(
            session.ljust(10).encode(),
            str(sequence_number).rjust(20).encode(),
        )


@dataclass
class LoginRejected(BigEndianCDataMixIn):
    reject_reason_code: bytes = field(metadata=meta(c_char))


def create_packet(packet_type: PacketType, payload: bytes = b""):
    return Header(len(payload) + 1, packet_type.value).to_bytes() + payload
