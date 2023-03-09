import asyncio
import logging
import time
from typing import Literal, Optional, Union, cast

from .errors import HeartbeatTimeoutError
from .packets import PacketType, create_packet
from .stream import Stream

HeartbeatType = Union[
    Literal[PacketType.SERVER_HEARTBEAT], Literal[PacketType.CLIENT_HEARTBEAT]
]


logger = logging.getLogger(__name__)


class Protocol(asyncio.Protocol):
    def __init__(
        self,
        stream: Stream,
        heartbeat_type: HeartbeatType,
        hearbeat_interval: float,
        heartbeat_timeout: float,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self._stream = stream
        self.heartbeat_type = heartbeat_type
        self.heartbeat_interval = hearbeat_interval
        self.heartbeat_timeout = heartbeat_timeout

        self.last_tx_mills = 0.00
        self.last_rx_mills = 0.00
        self.session = ""
        self.sequence_number = 1

        self.error: Optional[Exception] = None
        self._loop = asyncio.get_event_loop() if loop is None else loop
        # self._waiter: Optional[asyncio.Future] = None
        self._has_packet = asyncio.Event()
        self._keep_alive_task: Optional[asyncio.Task] = None

    @property
    def host(self) -> str:
        return self._transport.get_extra_info("sockename")[0]

    @property
    def port(self) -> int:
        return self._transport.get_extra_info("sockename")[1]

    @property
    def peer_host(self) -> str:
        return self._transport.get_extra_info("peername")[0]

    @property
    def peer_port(self) -> int:
        return self._transport.get_extra_info("peername")[1]

    @property
    def is_closing(self) -> int:
        return self._transport.is_closing()

    @property
    def received(self):
        return self._stream.processed

    @property
    def next_sequence_number(self) -> int:
        return self.sequence_number + self.received

    def connection_made(self, transport: asyncio.transports.BaseTransport) -> None:
        self._transport = cast(asyncio.transports.Transport, transport)

    def data_received(self, data: bytes) -> None:
        logger.debug(f"<< {data.decode(errors='ignore')}")
        self.last_rx_mills = time.time()
        self._stream.feed(data)
        if self._stream.has_packet:
            self._has_packet.set()
            self._has_packet.clear()
        # self._wakeup_waiter()

    """
    async def _wait_packet(self):
        waiter = self._waiter = self._loop.create_future()
        try:
            await waiter
        finally:
            self._writer = None

    def _wakeup_waiter(self):
        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            waiter.set_result(None)

    def _set_error(self, exception: Exception):
        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_exception(exception)
    """

    async def send(self, packet_type: PacketType, payload: bytes = b""):
        return await self.send_raw(create_packet(packet_type, payload))

    async def send_raw(self, data: bytes):
        logger.debug(f">> {data.decode(errors='ignore')}")
        self.last_tx_mills = time.time()
        self._transport.write(data)

    async def recv(self):
        # if not self._stream.has_packet:
        #    await self._wait_packet()
        if not self._stream.has_packet:
            await self._has_packet.wait()
        packet = self._stream.get_packet()
        if packet is None:
            assert False
        else:
            return packet

    async def recvall(self):
        # if not self._stream.has_packet:
        #    await self._wait_packet()
        if not self._has_data.is_set():
            await self._has_data.wait()
        return self._stream.get_packets()

    async def keep_alive(self, run_forever: bool = False):
        now = time.time()
        if now - self.last_rx_mills > self.heartbeat_timeout:
            self.error = HeartbeatTimeoutError(now - self.last_rx_mills)
            # self._set_error(
            #    TimeoutError(f"Heartbeat lost for {self.heartbeat_timeout} seconds")
            # )
        if now - self.last_tx_mills > self.heartbeat_interval:
            await self.send(self.heartbeat_type)
        if run_forever:
            await asyncio.sleep(self.heartbeat_interval)
            await self.keep_alive(run_forever)

    def start_keep_alive(self):
        if self._keep_alive_task is None:
            self._keep_alive_task = self._loop.create_task(
                self.keep_alive(run_forever=True)
            )

    def stop_keep_alive(self):
        if self._keep_alive_task is not None:
            self._keep_alive_task.cancel()

    async def __anext__(self):
        packet = await self.recv()
        if self._transport.is_closing() or packet.type == PacketType.END_OF_SESSION:
            raise StopAsyncIteration
        return packet

    def __aiter__(self):
        return self
