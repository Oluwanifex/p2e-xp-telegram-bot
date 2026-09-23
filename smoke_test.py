import asyncio
from playwright.async_api import async_playwright

URL = 'https://p2efiktivgame.web.app/p2e/game.html'
SELECTORS = [
    '#collect-wood-btn', '#collect-coal-btn', '#collect-sand-btn', '#mine-stone-btn',
    '#craft-plank-btn', '#craft-glass-btn', '#start-fishing-btn', '#dig-earth-btn',
    '#daily-reward-btn', '#fill-energy-btn',
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        page = await browser.new_page()
        await page.goto(URL, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(1000)
        title = await page.title()
        present = {selector: await page.locator(selector).count() for selector in SELECTORS}
        print(title)
        print('final_url=', page.url)
        print(present)
        # The game intentionally redirects unauthenticated browsers to the public login page.
        if not any(present.values()):
            assert await page.locator('#show-login').count() == 1
            print('unauthenticated redirect verified')
        else:
            assert all(count == 1 for count in present.values())
            print('authenticated game controls verified')
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
