import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from .errors import LoginRejectedError
from .packets import LoginAccepted, LoginRejected, LoginRequest, PacketType
from .protocol import Protocol
from .stream import Stream


@asynccontextmanager
async def connect(
    host: str,
    port: int,
    username: str,
    password: str,
    heartbeat_interval: float = 5.00,
    heartbeat_timout=15.00,
    loop: Optional[asyncio.AbstractEventLoop] = None,
):
    loop = asyncio.get_event_loop() if loop is None else loop
    transport, client = await loop.create_connection(
        lambda: Client(
            username, password, heartbeat_interval, heartbeat_timout, loop
        ),
        host,
        port,
    )
    try:
        await client.start()
        yield client
    finally:
        await client.stop()
        transport.close()


class Client(Protocol):
    def __init__(
        self,
        username: str,
        password: str,
        hearbeat_interval: float,
        heartbeat_timeout: float,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        super().__init__(
            stream=Stream(PacketType.SEQUENCED_DATA),
            heartbeat_type=PacketType.CLIENT_HEARTBEAT,
            hearbeat_interval=hearbeat_interval,
            heartbeat_timeout=heartbeat_timeout,
            loop=loop,
        )
        self.username = username
        self.password = password
        self.requested_session = ""
        self.requested_sequence_number = 0

    async def login(self):
        await self.send(
            PacketType.LOGIN_REQUEST,
            LoginRequest.new(
                self.username,
                self.password,
                self.requested_session,
                self.requested_sequence_number,
            ).to_bytes(),
        )
        async for packet in self:
            if packet.type == PacketType.LOGIN_ACCEPTED:
                login_accepted = LoginAccepted.from_buffer_copy(packet.data)
                self.requested_session = login_accepted.session.decode()
                self.requested_sequence_number = int(
                    login_accepted.sequence_number.decode()
                )
            elif packet.type == PacketType.LOGIN_REJECTED:
                raise LoginRejectedError(
                    LoginRejected.from_buffer_copy(
                        packet.data
                    ).reject_reason_code
                )
            break

    async def logout(self):
        await self.send(PacketType.LOGOUT_REQUEST)

    async def start(self):
        await self.login()
        self.start_keep_alive()

    async def stop(self):
        await self.logout()
        self.stop_keep_alive()
