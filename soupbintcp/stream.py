from typing import Literal, Optional, Union

from .packets import Header, Packet, PacketType

DataType = Union[
    Literal[PacketType.SEQUENCED_DATA], Literal[PacketType.UNSEQUENCED_DATA]
]


class Stream:
    def __init__(self, data_type: DataType):
        self.data_type = data_type
        self._buffer = bytearray()
        self._processed = 0

    @property
    def processed(self):
        return self._processed

    @property
    def has_packet(self):
        header_size = Header.size()
        if len(self._buffer) < header_size:
            return False
        header = Header.from_buffer(self._buffer)
        if len(self._buffer) - header_size < header.payload_length:
            return False
        return True

    def clear(self):
        self._buffer = bytearray()

    def feed(self, data: bytes):
        self._buffer.extend(data)

    def get_packet(self, data: Optional[bytes] = None):
        if data is not None:
            self.feed(data)
        if self.has_packet:
            header_size = Header.size()
            header = Header.from_buffer(self._buffer)
            offset_to_next_packet = header_size + header.payload_length
            packet_type = PacketType(header.packet_type)
            payload = bytes(self._buffer[header_size:offset_to_next_packet])
            if packet_type == self.data_type:
                self._processed += 1
            del self._buffer[:offset_to_next_packet]
            return Packet(header.packet_length, packet_type, payload)
        else:
            return None

    def get_packets(self, data: Optional[bytes] = None):
        if data is not None:
            self.feed(data)
        while True:
            packet = self.get_packet()
            if packet is None:
                break
            else:
                yield packet
