# ⚡ Velocity

A Discord running tracker written with `discord.py`, async SQLite, and Components V2 (`ui.LayoutView`).

## Features

- `/runs panel` — private interactive dashboard with a run logging modal, history, and stats
- `/runs log` — log a run using slash command arguments and receive a visual summary
- `/runs all` — privately browse your run history (5 runs per page)
- `/runs stats` — view distance, running time, run count, average pace, and longest run

Distances support `5km`, `5k`, or `5000m`; durations use `MM:SS` or `HH:MM:SS`.

## Setup

Requires Python 3.10 or newer.

```bash
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set your Discord bot token. Then run:

```bash
python main.py
```

The SQLite database path defaults to `memory/main.db` and is created automatically if missing. The database uses the existing `runs` table, so existing run records are preserved.

**Privacy:** An older `memory/main.db` file is already committed in this repository. The new `.gitignore` prevents *new* database files being tracked, but does not untrack files already committed. Back up your data before removing a tracked database from git history.

## Code organization

- `bot/cogs/running.py`: Discord slash commands
- `bot/ui/running.py`: Components V2 layouts, modal, and pagination
- `bot/utils/running.py`: pure parsing/validation/formatting logic
- `classes/database.py`: async database queries

## Running tests

```bash
python -m unittest discover -s tests
```
