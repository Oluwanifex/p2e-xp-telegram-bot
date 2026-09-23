# Telegram XP Optimizer

This bot controls the authorized reference game through a real Chromium session. It signs in with each participant's own account, invokes the site's normal UI actions, and relies on the site's Firebase callable functions to validate and award XP. It does **not** write Firestore directly, forge XP, bypass authentication, or exploit client-side state.

## Setup

```bash
cd /home/ubuntu/p2e_xp_bot
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
export TELEGRAM_BOT_TOKEN='your-bot-token'
python bot.py
```

Playwright uses its bundled Chromium by default, which is the correct setup for Railway. Set `CHROMIUM_PATH` only when running locally with a separately installed browser. `HEADLESS=0` is useful for debugging. Profiles are kept under `./profiles`; use `/logout` to close the session, and delete the profile directory manually if a participant asks for a full local-session reset.

## Railway variables

Set these variables in the Railway service. `TELEGRAM_BOT_TOKEN` is the only required secret. Participants authenticate through the private Telegram `/login` command, so participant passwords do not belong in Railway variables.

| Variable | Required | Value |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | Token from BotFather. |
| `REFERENCE_URL` | No | Defaults to `https://p2efiktivgame.web.app`. |
| `HEADLESS` | No | Keep `1` on Railway. |
| `POLL_SECONDS` | No | Gameplay loop interval; default `8`. |
| `REPORT_INTERVAL_SECONDS` | No | Telegram progress-report interval; default `60`. |
| `ACTION_TIMEOUT_MS` | No | Browser action timeout; default `20000`. |
| `PROFILE_ROOT` | No | Defaults to `./profiles`; Railway storage is ephemeral unless a volume is attached. |

While `/run` is active, the bot sends a Telegram report at the configured interval containing XP, level, energy, food, resources, active quest, completed quests, and optimizer state. `/status` returns the same information immediately.

## Commands

| Command | Purpose |
| --- | --- |
| `/login username password` | Sign in to the participant's account. Use only in a private Telegram chat; the message is deleted on a best-effort basis. |
| `/status` | Show XP, level, energy, resources, current quest, and optimizer state. |
| `/run` | Start the XP loop. |
| `/stop` | Pause the loop. |
| `/logout` | Close the participant's local browser session. |

The loop claims ready timers, starts eligible production, refills energy with available food, advances the active quest, and submits completed quests through the game's server-validated function. It is intentionally conservative: it does not submit requests faster than the game's own controls and does not attempt to defeat cooldowns.

## Important rules

Run this only where the hackathon organizers explicitly permit automation and only with the participant's own login. Do not use it against accounts or environments without authorization. Do not commit `.env`, Telegram tokens, passwords, browser profiles, or session data.
