import asyncio

from soupbintcp.client import connect
from soupbintcp.packets import PacketType


async def main():
    async with connect("localhost", 20000, "test", "password") as c:
        await c.send(PacketType.DEBUG, b"DEBUG_PACKET")


if __name__ == "__main__":
    asyncio.run(main())
