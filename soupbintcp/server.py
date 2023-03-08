import asyncio
from typing import Optional, Type

from .errors import LoginRejectCode
from .packets import LoginAccepted, LoginRejected, LoginRequest, PacketType
from .protocol import Protocol
from .stream import Stream


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
    return server


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

        self.requested_session = ""
        self.requested_sequence_number = 0
        self.authenticated = asyncio.Event()

    def connection_made(
        self, transport: asyncio.transports.BaseTransport
    ) -> None:
        super().connection_made(transport)
        self._loop.create_task(self.run_forever())

    async def run_forever(self):
        while not self._transport.is_closing():
            async for packet in self:
                if packet.type == PacketType.LOGIN_REQUEST:
                    await self.on_login_request(
                        LoginRequest.from_buffer_copy(packet.data)
                    )
                else:
                    await self.wait_authentication()
                    if packet.type == PacketType.LOGOUT_REQUEST:
                        await self.on_logout_request()
                    elif packet.type == PacketType.UNSEQUENCED_DATA:
                        await self.on_unsequenced_data(packet.data)
                    elif packet.type == PacketType.CLIENT_HEARTBEAT:
                        await self.on_client_heartbeat()
                    elif packet.type == PacketType.DEBUG:
                        await self.on_debug(packet.data)
                    else:
                        raise self._set_error(
                            ValueError(
                                f"InvalidPacketType=f{str(packet.type.value)}"
                            )
                        )

    async def wait_authentication(self):
        await asyncio.wait_for(self.authenticated.wait(), self.login_timeout)

    async def on_login_request(self, login_request: LoginRequest):
        username = login_request.username.decode().strip()
        password = login_request.password.decode().strip()
        requested_session = login_request.requested_session.decode()
        requested_sequence_number = int(
            login_request.requested_sequence_number.decode()
        )
        reject_reason = await self.authenticate(
            username, password, requested_session
        )
        if reject_reason is not None:
            await self.reject(reject_reason)
        else:
            await self.accept(
                requested_session,
                requested_sequence_number,
            )
            self.start_keep_alive()

    async def on_logout_request(self):
        self.close()

    async def on_unsequenced_data(self, data: bytes):
        raise NotImplementedError

    async def on_client_heartbeat(self):
        pass

    async def on_debug(self, data: bytes):
        await self.send(PacketType.DEBUG, data)

    async def authenticate(
        self, username: str, password: str, session: str
    ) -> Optional[LoginRejectCode]:
        if self.username == username and self.password == password:
            if self.requested_session == session:
                self.authenticated.set()
                return None
            else:
                return LoginRejectCode.SESSION_NOT_AVAILABLE
        else:
            return LoginRejectCode.NOT_AUTHORIZED

    async def accept(self, session: str, sequence_number: int):
        await self.send(
            PacketType.LOGIN_ACCEPTED,
            LoginAccepted.new(session, sequence_number),
        )

    async def reject(self, reason: LoginRejectCode):
        await self.send(
            PacketType.LOGIN_REJECTED, LoginRejected(reason.value).to_bytes()
        )
        self.close()

    def close(self):
        self.stop_keep_alive()
        self._transport.close()
