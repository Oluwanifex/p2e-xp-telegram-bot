import asyncio
from bot import GameBot


async def main():
    gamebot = GameBot()
    await gamebot.start()
    await gamebot.stop()
    print('Playwright bundled Chromium launch passed')


if __name__ == '__main__':
    asyncio.run(main())
