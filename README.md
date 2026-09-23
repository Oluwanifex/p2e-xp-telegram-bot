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

The system Chromium is used by default. Set `CHROMIUM_PATH` if a different executable is required. `HEADLESS=0` is useful for debugging. Profiles are kept under `./profiles`; use `/logout` to close the session, and delete the profile directory manually if a participant asks for a full local-session reset.

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
