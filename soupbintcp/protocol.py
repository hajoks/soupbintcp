import asyncio
import time
from typing import Literal, Optional, Union, cast

from .packets import PacketType, create_packet
from .stream import Stream

HeartbeatType = Union[
    Literal[PacketType.SERVER_HEARTBEAT], Literal[PacketType.CLIENT_HEARTBEAT]
]


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
        self._loop = asyncio.get_event_loop() if loop is None else loop
        self._waiter: Optional[asyncio.Future] = None
        self._keep_alive_task: Optional[asyncio.Task] = None

    @property
    def received(self):
        return self._stream.processed

    def connection_made(
        self, transport: asyncio.transports.BaseTransport
    ) -> None:
        self._transport = cast(asyncio.transports.Transport, transport)

    def data_received(self, data: bytes) -> None:
        print("<< ", data)
        self.last_rx_mills = time.time()
        self._stream.feed(data)
        if self._stream.has_packet:
            self._wakeup_waiter()

    async def _wait_packet(self):
        self._waiter = self._loop.create_future()
        try:
            yield self._waiter
        finally:
            self._writer = None

    def _wakeup_waiter(self):
        if self._waiter is not None:
            if not self._waiter.cancelled():
                self._waiter.set_result(None)
            self._waiter = None

    def _set_error(self, exception: Exception):
        if self._waiter is not None:
            if not self._waiter.cancelled():
                self._waiter.set_exception(exception)
            self._waiter = None

    async def send(self, packet_type: PacketType, payload: bytes = b""):
        return await self.send_raw(create_packet(packet_type, payload))

    async def send_raw(self, data: bytes):
        print(">> ", data)
        self.last_tx_mills = time.time()
        self._transport.write(data)

    async def recv(self):
        if not self._stream.has_packet:
            await self._waiter
        return self._stream.get_packets()

    async def keep_alive(self, run_forever: bool = False):
        if time.time() - self.last_rx_mills > self.heartbeat_timeout:
            self._set_error(
                TimeoutError(
                    f"Heartbeat lost for {self.heartbeat_timeout} seconds"
                )
            )
        if time.time() - self.last_tx_mills > self.heartbeat_interval:
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
        packet = self._stream.get_packet()
        if packet is None:
            raise StopAsyncIteration
        return packet

    def __aiter__(self):
        return self
