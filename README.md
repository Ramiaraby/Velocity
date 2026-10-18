# ⚡ VELOCITY — One dashboard, three sports

**Velocity** is a Discord activity journal for running 🏃, cycling 🚴 and swimming 🏊.

## Start

Run **`/velocity`**. That is the **only slash command**.

The bot opens a private, user-specific Components V2 dashboard. Use it to navigate:

| Dashboard screen | What it does |
|---|---|
| 🏠 Home | Equal cards for running, cycling, swimming, with total sessions and distance |
| 🏃 Sport | Select any discipline; log an activity, see combined stats and records |
| 📚 History | Browse 5 at a time, select individual entries to open details |
| 📸 Activity details | Optional proof image, coarse location and notes while review is pending |
| 🏆 Rankings | Per-sport, per-server, owner-verified distance by 7 days/30 days/all time |
| 👤 Profile | Your activities, verified count, seven-day recap, private CSV export |
| 🛡️ Review | Only OWNER_ID can inspect pending records and verify/reject them |

Screens are **ephemeral** (private to the user opening the dashboard) and buttons reject interactions from a different account. The default interaction timeout is 10 minutes; reopen `/velocity` if a dashboard stops responding. Selecting a sport uses a dropdown; each sport has the *same layout* but uses its appropriate metrics.

## New Discord features

- Uses **discord.py 2.7.1**, Discord **Components V2**, `ui.LayoutView`, `ui.Container`, `ui.Section`, `ui.ActionRow`, and `ui.Select`.
- Logs activities in modern **modal forms** with `ui.Label`, `ui.TextInput`, and a swimming-specific water-type select.
- Optional proof upload is a **native `ui.FileUpload` modal component** accessed by clicking **Add proof** on an activity. This is a Discord 2.7+ feature. Attachments are copied into a private Discord channel for owner review.
- Personalized home screens, consistent icon-led sport cards, one-button sport switching, contextual history and owner review.

## Activity logging

The core modal asks for name, distance and duration, with sport-appropriate extra fields:

| Sport | Additional fields | Performance |
|---|---|---|
| 🏃 Running | Optional elevation gain and location | min/km |
| 🚴 Cycling | Optional elevation gain and location | km/h |
| 🏊 Swimming | Pool/open-water selection and optional pool length | min/100m |

Distances: `5km`, `5k`, `1500m`; durations: `MM:SS` or `HH:MM:SS`. The existing validation checks improbable entries, not athletic eligibility.

After logging, the dashboard opens that activity. **Add proof** and **Place / notes** buttons are available while a record is pending. Location entry is always optional, and swimming locations can be added through the details form.

### Manual verification

Every activity starts **pending**. Only the account whose numeric ID appears in **`OWNER_ID`** can approve or reject. Reviewer ID/time are saved in SQLite. An activity cannot be edited or re-reviewed after the decision. The owner review queue is paginated, and the owner can inspect proof images there.

A place-name lookup **does not prove someone was physically at the place**. A photo is evidence for a human to evaluate, not automatic verification. The app does not make AI claims about a runner's movements.

### Leaderboard rules

- Only owner-verified activities count.
- Guild rankings are restricted to activities originally logged in **that server**, and sports never compete directly.
- Old activities without a guild ID still appear in personal history but not in server rankings.
- User-specific dashboards and history stay private. Leaderboard pages are also shown privately within the dashboard.
- All-time personal records use the user's own logs and do not necessarily imply owner verification.

## Install

Use Python 3.11 or newer:

```bash
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set:

```ini
BOT_TOKEN=your_discord_bot_token
DB_PATH=memory/main.db
OWNER_ID=your_numeric_discord_user_id
PROOF_CHANNEL_ID=your_private_owner_review_text_channel_id
```

Only give the bot and its owner access to the proof channel. All environment values stay on the bot host, never in GitHub.

**Optional geocoding**: Read the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) first. If using the public service, set a contactable, identifying `GEOCODER_USER_AGENT`. The existing cached, throttled geocoder checks only whether a named area exists; public Nominatim is not designed for autocomplete or high-volume lookups. © OpenStreetMap contributors. Leave it unset if you don't want geocoding.

Then run:

```bash
python main.py
```

When the bot syncs its commands, obsolete slash commands are removed. You must restart with this code for `/velocity` to become the only command.

### Existing data

**No destructive migration is required.** The existing SQLite `runs` table is intentionally kept, with its new `sport` column, run IDs, evidence and review states. Old run rows remain running entries. Back up `memory/main.db` before deploying. If you have shared the database in the repo previously, `.gitignore` does not delete its public history—handle the old tracked file deliberately.

### Developer notes

- `bot/cogs/hub.py` — the one `/velocity` slash command
- `bot/ui/hub.py` — one navigable dashboard, sport forms, proof upload and owner review
- `bot/utils/activity.py` and `bot/utils/running.py` — input validation, conversions, metrics
- `bot/utils/evidence.py` — private image storage and owner review links
- `bot/utils/location.py` — coarse OpenStreetMap place lookup
- `classes/database.py` — async SQLite data access and non-destructive migrations

```bash
python -m unittest discover -s tests -v
```

Automatic tests check the UI's construction, user isolation, database upgrades, permissions, validation, owner moderation and leaderboards. A manual live Discord server test is still required before deployment, especially for file-upload and button interactions.
