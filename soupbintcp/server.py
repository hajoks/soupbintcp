import asyncio
import logging
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Optional, Type

from .errors import LoginRejectCode
from .packets import LoginAccepted, LoginRejected, LoginRequest, Packet, PacketType
from .protocol import Protocol
from .stream import Stream

logger = logging.getLogger(__name__)


@asynccontextmanager
async def serve(
    server_class: Type["Server"],
    host: str,
    port: int,
    username: str,
    password: str,
    heartbeat_interval: float = 5.00,
    heartbeat_timeout: float = 15.00,
    login_timeout: float = 1.00,
    loop: Optional[asyncio.AbstractEventLoop] = None,
    **kwargs,
):
    loop = asyncio.get_event_loop() if loop is None else loop
    server = await loop.create_server(
        lambda: server_class(
            username,
            password,
            heartbeat_interval,
            heartbeat_timeout,
            login_timeout,
            loop,
        ),
        host,
        port,
        **kwargs,
    )
    try:
        yield server
    finally:
        server.close()


class Server(Protocol):
    def __init__(
        self,
        username: str,
        password: str,
        hearbeat_interval: float,
        heartbeat_timeout: float,
        login_timeout: float,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        super().__init__(
            stream=Stream(PacketType.UNSEQUENCED_DATA),
            heartbeat_type=PacketType.SERVER_HEARTBEAT,
            hearbeat_interval=hearbeat_interval,
            heartbeat_timeout=heartbeat_timeout,
            loop=loop,
        )
        self.username = username
        self.password = password
        self.login_timeout = login_timeout

        self.session = ""
        self.sequence_number = 1
        self._authenticated = asyncio.Event()
        self._service: Optional[asyncio.Task]

    @property
    def url(self):
        return f"multisoupbin300://{self.host}:{self.port}"

    def connection_made(self, transport: asyncio.transports.BaseTransport) -> None:
        super().connection_made(transport)
        self._service = self._loop.create_task(self.serve())

    async def serve(self):
        async for packet in self:
            await self.dispatch(packet)
            if self.error is None:
                self._service.set_exception(self.error)

    async def dispatch(self, packet: Packet):
        logger.debug(f"Dispatch {packet.type}")
        if packet.type == PacketType.LOGIN_REQUEST:
            await self.on_login_request(LoginRequest.from_buffer_copy(packet.payload))
        else:
            await self.wait_authentication()
            if packet.type == PacketType.LOGOUT_REQUEST:
                await self.on_logout_request()
            elif packet.type == PacketType.UNSEQUENCED_DATA:
                await self.on_unsequenced_data(packet.payload)
            elif packet.type == PacketType.CLIENT_HEARTBEAT:
                await self.on_client_heartbeat()
            elif packet.type == PacketType.DEBUG:
                await self.on_debug(packet.payload)
            else:
                self.error = ValueError(
                    f"InvalidPacketType={packet.type.value.decode()}"
                )

    async def on_login_request(self, login_request: LoginRequest):
        username = login_request.username.decode().strip()
        password = login_request.password.decode().strip()
        requested_session = login_request.requested_session.decode().strip()
        requested_sequence_number = int(
            login_request.requested_sequence_number.decode().strip()
        )
        reject_reason = await self.authenticate(username, password, requested_session)
        if reject_reason is not None:
            await self.reject(reject_reason)
        else:
            await self.accept(
                requested_session,
                requested_sequence_number,
            )

    async def on_logout_request(self):
        self.close()

    async def on_unsequenced_data(self, data: bytes):
        raise NotImplementedError

    async def on_client_heartbeat(self):
        pass

    async def on_debug(self, data: bytes):
        await self.send(PacketType.DEBUG, data)

    async def wait_authentication(self):
        logger.debug("start:wait_authentication")
        await asyncio.wait_for(self._authenticated.wait(), self.login_timeout)
        logger.debug("end:wait_authentication")

    async def authenticate(
        self, username: str, password: str, session: str
    ) -> Optional[LoginRejectCode]:
        if self.username == username and self.password == password:
            if self.session == session:
                return None
            else:
                return LoginRejectCode.SESSION_NOT_AVAILABLE
        else:
            return LoginRejectCode.NOT_AUTHORIZED

    async def accept(self, session: str, sequence_number: int):
        await self.send(
            PacketType.LOGIN_ACCEPTED,
            LoginAccepted.new(session, sequence_number).to_bytes(),
        )
        self._authenticated.set()
        self.start_keep_alive()

    async def reject(self, reason: LoginRejectCode):
        await self.send(
            PacketType.LOGIN_REJECTED, LoginRejected(reason.value).to_bytes()
        )
        self.close()

    def close(self):
        self.stop_keep_alive()
        self._transport.close()
        self._stream.get_packets()
        self._service.set_exception(self.error)

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()


async def main():
    import logging
    import sys

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(sys.stdout))

    class TestServer(Server):
        async def on_unsequenced_data(self, data: bytes):
            print(data)

    async with serve(TestServer, "localhost", 20000, "test", "password") as s:
        await s.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
