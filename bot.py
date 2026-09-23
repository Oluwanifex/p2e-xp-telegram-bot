"""Telegram-controlled XP optimizer for the authorized P2E reference game.

The bot drives the site's normal authenticated UI and server-validated handlers.
It does not write Firestore directly, forge XP, or bypass game rules.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

REFERENCE_URL = os.getenv("REFERENCE_URL", "https://p2efiktivgame.web.app")
GAME_URL = f"{REFERENCE_URL.rstrip('/')}/p2e/game.html"
PROFILE_ROOT = Path(os.getenv("PROFILE_ROOT", "./profiles"))
HEADLESS = os.getenv("HEADLESS", "1") != "0"
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "8"))
ACTION_TIMEOUT_MS = int(os.getenv("ACTION_TIMEOUT_MS", "20000"))
REPORT_INTERVAL_SECONDS = float(os.getenv("REPORT_INTERVAL_SECONDS", "60"))

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p2e-xp-bot")


@dataclass
class Session:
    chat_id: int
    context: BrowserContext
    page: Page
    running: bool = False
    task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_report_at: float = 0.0


class GameBot:
    def __init__(self) -> None:
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.sessions: dict[int, Session] = {}

    async def start(self) -> None:
        self.playwright = await async_playwright().start()
        launch_options = {"headless": HEADLESS, "args": ["--no-sandbox"]}
        if os.getenv("CHROMIUM_PATH"):
            launch_options["executable_path"] = os.environ["CHROMIUM_PATH"]
        self.browser = await self.playwright.chromium.launch(**launch_options)
        PROFILE_ROOT.mkdir(parents=True, exist_ok=True)

    async def stop(self) -> None:
        for session in list(self.sessions.values()):
            await self.close_session(session.chat_id)
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    def profile_dir(self, chat_id: int) -> Path:
        digest = hashlib.sha256(str(chat_id).encode()).hexdigest()[:20]
        return PROFILE_ROOT / digest

    async def open_session(self, chat_id: int) -> Session:
        old = self.sessions.get(chat_id)
        if old:
            return old
        if not self.playwright:
            raise RuntimeError("Browser is not started")
        # A persistent context preserves Firebase Auth's browser session without storing passwords.
        context_options = {"headless": HEADLESS, "args": ["--no-sandbox"]}
        if os.getenv("CHROMIUM_PATH"):
            context_options["executable_path"] = os.environ["CHROMIUM_PATH"]
        context = await self.playwright.chromium.launch_persistent_context(
            str(self.profile_dir(chat_id)), **context_options
        )
        page = await context.new_page()
        session = Session(chat_id=chat_id, context=context, page=page)
        self.sessions[chat_id] = session
        return session

    async def close_session(self, chat_id: int) -> None:
        session = self.sessions.pop(chat_id, None)
        if not session:
            return
        session.running = False
        if session.task and not session.task.done():
            session.task.cancel()
            try:
                await session.task
            except asyncio.CancelledError:
                pass
        await session.context.close()

    async def login(self, chat_id: int, username: str, password: str) -> None:
        session = await self.open_session(chat_id)
        async with session.lock:
            await session.page.goto(REFERENCE_URL, wait_until="domcontentloaded", timeout=ACTION_TIMEOUT_MS)
            await session.page.locator("#show-login").click()
            await session.page.locator("#login-username").fill(username)
            await session.page.locator("#login-password").fill(password)
            await session.page.locator("#login-form").locator("button[type=submit]").click()
            await session.page.wait_for_timeout(1200)
            await session.page.goto(GAME_URL, wait_until="domcontentloaded", timeout=ACTION_TIMEOUT_MS)
            await session.page.wait_for_function("Boolean(window.CURRENT_USER_UID && window.GAME_CACHE)", timeout=ACTION_TIMEOUT_MS)

    async def state(self, session: Session) -> dict[str, Any]:
        return await session.page.evaluate("""() => {
            const c = window.GAME_CACHE || {};
            const r = c.resources || {}, s = c.stats || {};
            return {
              xp: Number(s.xp || 0), level: Number(s.level || 1),
              energy: Number(r.energy || 0), maxEnergy: Number(window.MAX_ENERGY_FROM_RESOURCES || 100),
              tokens: Number(r.tokens || 0), food: Number(r.food || 0),
              wood: Number(r.wood || 0), coal: Number(r.coal || 0), stone: Number(r.stone || 0),
              sand: Number(r.sand || 0), glass: Number(r.glass || 0), plank: Number(r.plank || 0),
              earth: Number(r.earth || 0), fish: Number(r.fish || 0), farmland: Number(r.farmland || 0),
              timers: c.timers || {}, buildings: c.buildings || [],
              currentQuestId: c.currentQuestId || null,
              questsProgress: c.questsProgress || {},
              completedQuests: Number(s.completedQuestsCount || 0),
              dailyLastClaim: s.dailyLastClaim || null
            };
        }""")

    async def click(self, session: Session, selector: str) -> bool:
        loc = session.page.locator(selector)
        if await loc.count() == 0:
            return False
        try:
            if await loc.is_enabled():
                await loc.click(timeout=ACTION_TIMEOUT_MS)
                return True
        except Exception as exc:
            log.debug("click %s failed: %s", selector, exc)
        return False

    async def optimize_once(self, session: Session) -> dict[str, Any]:
        before = await self.state(session)

        # Claim daily reward whenever the official button is active.
        await self.click(session, "#daily-reward-btn")

        # Complete any ready timers before starting new work.
        timers = before.get("timers", {})
        timer_selectors = {
            "woodCutStart": "#collect-wood-btn", "coalMineStart": "#collect-coal-btn",
            "sandMineStart": "#collect-sand-btn", "stoneMineStart": "#mine-stone-btn",
            "plankStart": "#craft-plank-btn", "glassCraftStart": "#craft-glass-btn",
            "fishingStart": "#start-fishing-btn", "digStart": "#dig-earth-btn",
        }
        for timer_name, selector in timer_selectors.items():
            value = timers.get(timer_name, 0)
            if isinstance(value, (int, float)) and value > 0:
                # The site itself rejects early claims; clicking is safe and server validated.
                await self.click(session, selector)

        current = await self.state(session)
        energy = current["energy"]
        if energy < 5 and current["food"] > 0:
            await self.click(session, "#fill-energy-btn")
            await session.page.wait_for_timeout(150)
            await self.click(session, "#energyModal .food-btn")

        # Keep all independent 60–120 second production timers occupied.
        current = await self.state(session)
        timer_starts = current["timers"]
        for timer_name, selector in timer_selectors.items():
            value = timer_starts.get(timer_name, 0)
            if not value or value == -1:
                await self.click(session, selector)

        # Progress the current quest using its official action. This improves XP and level-gated access.
        quest_actions = {
            "q1_stone": "#mine-stone-btn", "q2_wood": "#collect-wood-btn", "q3_coal": "#collect-coal-btn",
            "q4_sand": "#collect-sand-btn", "q5_plank": "#craft-plank-btn", "q6_glass": "#craft-glass-btn",
            "q7_fish": "#start-fishing-btn",
        }
        quest_id = current.get("currentQuestId")
        if quest_id in quest_actions:
            await self.click(session, quest_actions[quest_id])
        elif quest_id == "q8_house":
            # Build only when the normal UI reports a valid affordable building.
            await session.page.evaluate("""() => {
                const order = ['gold_apartment','gold_house','gold_hut','apartment','house','hut'];
                for (const id of order) {
                  const b = document.getElementById('build-btn-' + id);
                  if (b && !b.disabled && typeof window.buildBuilding === 'function') { window.buildBuilding(id); break; }
                }
            }""")

        # Claim completed quests through the server-validated UI function, if available.
        await session.page.evaluate("""() => {
            if (typeof window.submitQuestToServer === 'function') {
              const q = window.GAME_CACHE?.currentQuestId;
              const p = window.GAME_CACHE?.questsProgress || {};
              const targets = {q1_stone:10,q2_wood:60,q3_coal:20,q4_sand:100,q5_plank:15,q6_glass:10,q7_fish:5,q8_house:1,q9_plot:1,q10_food:25};
              if (q && targets[q] !== undefined && Number(p[q] || 0) >= targets[q]) window.submitQuestToServer();
            }
        }""")

        await session.page.wait_for_timeout(250)
        return await self.state(session)

    async def run_loop(self, session: Session, notify) -> None:
        log.info("optimizer started for chat %s", session.chat_id)
        while session.running:
            try:
                async with session.lock:
                    st = await self.optimize_once(session)
                now = time.monotonic()
                should_report = (
                    session.last_report_at == 0.0
                    or now - session.last_report_at >= REPORT_INTERVAL_SECONDS
                    or "error" in st
                )
                if should_report:
                    session.last_report_at = now
                await notify(st, should_report, session.running)
                await asyncio.sleep(POLL_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("optimizer iteration failed")
                await notify({"error": str(exc)}, True, session.running)
                await asyncio.sleep(max(POLL_SECONDS, 10))


def private_only(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type == "private")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if private_only(update):
        await update.message.reply_text("Use /login <username> <password>, then /status and /run. /stop pauses automation.")


async def cmd_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not private_only(update):
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /login <participant_username> <password>\nSend this only in a private chat.")
        return
    username, password = context.args
    try:
        await update.message.delete()
    except Exception:
        pass
    bot: GameBot = context.application.bot_data["gamebot"]
    try:
        await bot.login(update.effective_chat.id, username, password)
        await update.effective_chat.send_message("Logged in successfully. Credentials were not stored. Use /status or /run.")
    except Exception:
        log.exception("login failed")
        await update.effective_chat.send_message("Login failed. Check the participant username/password and try again.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not private_only(update):
        return
    bot: GameBot = context.application.bot_data["gamebot"]
    session = bot.sessions.get(update.effective_chat.id)
    if not session:
        await update.message.reply_text("Not logged in.")
        return
    try:
        st = await bot.state(session)
        await update.message.reply_text(format_status(st, session.running))
    except Exception:
        await update.message.reply_text("The game session is unavailable; use /login again.")


def format_status(st: dict[str, Any], running: bool) -> str:
    if "error" in st:
        return f"Optimizer error: {st['error']}"
    return (f"XP: {st['xp']:,} | level {st['level']}\n"
            f"Energy: {st['energy']}/{st['maxEnergy']} | food {st['food']}\n"
            f"Wood {st['wood']} | coal {st['coal']} | stone {st['stone']}\n"
            f"Sand {st['sand']} | glass {st['glass']} | plank {st['plank']} | earth {st['earth']}\n"
            f"Quest: {st['currentQuestId'] or 'none'} | completed {st['completedQuests']}\n"
            f"Optimizer: {'running' if running else 'stopped'}")


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not private_only(update):
        return
    bot: GameBot = context.application.bot_data["gamebot"]
    session = bot.sessions.get(update.effective_chat.id)
    if not session:
        await update.message.reply_text("Log in first with /login <username> <password>.")
        return
    if session.running:
        await update.message.reply_text("Optimizer is already running.")
        return
    session.running = True
    session.last_report_at = 0.0
    session.task = asyncio.create_task(bot.run_loop(session, lambda st, report, running: periodic_update(update, st, report, running)))
    await update.message.reply_text("Optimizer started. Use /status for current XP or /stop to pause.")


async def periodic_update(update: Update, state: dict[str, Any], report: bool, running: bool) -> None:
    # Report at a bounded interval to avoid Telegram spam; /status remains on-demand.
    if report or "error" in state:
        try:
            await update.effective_chat.send_message(format_status(state, running))
        except Exception:
            pass


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not private_only(update):
        return
    bot: GameBot = context.application.bot_data["gamebot"]
    session = bot.sessions.get(update.effective_chat.id)
    if not session:
        await update.message.reply_text("Not logged in.")
        return
    session.running = False
    if session.task and not session.task.done():
        session.task.cancel()
    await update.message.reply_text("Optimizer stopped.")


async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not private_only(update):
        return
    bot: GameBot = context.application.bot_data["gamebot"]
    await bot.close_session(update.effective_chat.id)
    await update.message.reply_text("Logged out of the local browser session.")


async def post_init(application: Application) -> None:
    await application.bot_data["gamebot"].start()


async def post_shutdown(application: Application) -> None:
    await application.bot_data["gamebot"].stop()


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN before starting the bot")
    gamebot = GameBot()
    app = (Application.builder().token(token).post_init(post_init).post_shutdown(post_shutdown).build())
    app.bot_data["gamebot"] = gamebot
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("login", cmd_login))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("logout", cmd_logout))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

__all__ = ["GameBot", "format_status"]

# Prevent accidental unused-import lint noise in minimal deployments.
_ = (re, shutil)
