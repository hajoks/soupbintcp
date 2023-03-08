import pytest

from soupbintcp.packets import PacketType
from soupbintcp.stream import Stream


@pytest.fixture
def stream():
    return Stream(PacketType.SEQUENCED_DATA)


@pytest.fixture
def server_heartbeat():
    packet_length = 1
    packet_type = "H"
    return packet_length.to_bytes(2, "big") + bytes(packet_type, "utf8")


@pytest.fixture
def login_accepted():
    packet_length = 31
    packet_type = "A"
    session = "test      "
    sequence_number = "                   1"
    return (
        packet_length.to_bytes(2, "big")
        + bytes(packet_type, "utf8")
        + bytes(session, "utf8")
        + bytes(sequence_number, "utf8")
    )


def test_has_packet_only_header(stream, server_heartbeat):
    stream.feed(server_heartbeat[:2])
    assert not stream.has_packet
    stream.feed(server_heartbeat[2:])
    assert stream.has_packet


def test_has_packet_with_payload(stream, login_accepted):
    stream.feed(login_accepted[:10])
    assert not stream.has_packet
    stream.feed(login_accepted[10:])
    assert stream.has_packet


def test_get_packet_with_no_data(stream):
    packet_type, payload = stream.get_packet()
    assert packet_type is None
    assert payload is None


def test_get_packet_only_header(stream, server_heartbeat):
    packet_type, payload = stream.get_packet(server_heartbeat)
    assert packet_type.value == b"H"
    assert payload == b""


def test_get_packet_with_payload(stream, login_accepted):
    packet_type, payload = stream.get_packet(login_accepted)
    assert packet_type.value == b"A"
    assert payload == b"test      " + b"                   1"


def test_get_packets(stream, server_heartbeat, login_accepted):
    for i, (packet_type, payload) in enumerate(
        stream.get_packets(server_heartbeat + login_accepted)
    ):
        if i == 0:
            assert packet_type.value == b"H"
            assert payload == b""
        if i == 1:
            assert packet_type.value == b"A"
            assert payload == b"test      " + b"                   1"
        if i == 2:
            assert False


def test_get_packets_fragmented(stream, server_heartbeat, login_accepted):
    for i, (packet_type, payload) in enumerate(
        stream.get_packets(server_heartbeat + login_accepted[:5])
    ):
        if i == 0:
            assert packet_type.value == b"H"
        if i == 1:
            assert False
    stream.feed(login_accepted[5:])
    for i, (packet_type, payload) in enumerate(
        stream.get_packets(login_accepted[5:])
    ):
        if i == 0:
            assert packet_type.value == b"A"
            assert payload == b"test      " + b"                   1"
        if i == 1:
            assert False
