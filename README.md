![AI Assisted](https://img.shields.io/badge/AI-Assisted-blue?style=flat-square&logo=openai)
# Guild Queue Bot 🛡️

Telegram bot for managing guild queues and character registration in MMO games.
Designed to simplify loot distribution and activity tracking.

## Features
* **Character Management:** Link main and alt characters to Telegram ID.
* **Validation:** Checks character nicknames against a Guild Google Sheet.
* **Queue System:** Sign up for guild activities (raids, loot distribution).
* **Database:** SQLite storage for reliable data handling.

## Tech Stack
* Python 3.10+
* aiogram 3.x (Async Telegram API)
* aiosqlite (Async SQLite)
* Google Sheets API (gspread)

## Setup
1. Clone the repository.
2. Create a `.env` file with your `BOT_TOKEN`.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt