import asyncio

from soupbintcp.server import Server, serve


async def main():
    class TestServer(Server):
        async def on_unsequenced_data(self, data: bytes):
            print(data)

    server = await serve(TestServer, "localhost", 20000, "test", "password")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
