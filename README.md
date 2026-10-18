# ⚡ Velocity

A Discord running tracker built with `discord.py`, async SQLite and Components V2 (`ui.LayoutView`).

## Commands

| Command | Description |
| --- | --- |
| `/runs panel` | Private dashboard; log runs using a modal |
| `/runs log` | Log a run; optionally provide elevation, place, and proof image |
| `/runs proof run_id image` | Attach a photo/screenshot after logging, before review |
| `/runs all` | Private paginated history (includes run ID and verification status) |
| `/runs stats` | Lifetime stats and owner-verified run count |
| `/runs pending` | **Owner only:** 10 newest runs awaiting review |
| `/runs inspect run_id` | **Owner only:** detailed run inspection with private proof image and Verify/Reject buttons |
| `/runs review run_id decision note` | **Owner only:** slash command for approving or rejecting |

Runs start **pending**, never automatically verified. A matching place name or screenshot is *not* evidence that the run definitely occurred. The sole authority to approve/reject is the Discord account specified by `OWNER_ID` in the environment. Review decisions are saved in SQLite with reviewer ID and timestamp; decisions are final, so the same run cannot be reviewed twice.

Distances support `5km`, `5k`, `5000m`; durations use `MM:SS` or `HH:MM:SS`. Elevation gain is an optional non-negative integer in meters. Location is optional city/neighborhood-level text and is looked up by the location resolver; exact addresses and GPS coordinates are deliberately not stored.

### Evidence privacy

Proof uploads use a **private Discord text channel** whose ID is `PROOF_CHANNEL_ID`. Create a channel that only you and your bot can access. The bot reuploads the image there and saves only the channel/message IDs in SQLite. Other runners cannot inspect anyone else's proof. Images may contain identifiable data: only upload images you are willing to share with the server owner. Supported formats: JPG, PNG, WEBP, GIF, up to 10 MB. Deleting a proof message in the review channel will remove that image.

Discord's standard five-field modal is used for name, distance, duration, optional elevation, and optional place. To attach an image, use the `/runs log` slash command's **proof** option or `/runs proof` afterward. Review results are visible privately in `/runs all`.

### Location verification

Velocity optionally uses **GeoPy + OpenStreetMap Nominatim** to check that a named place *exists*. That is a place-name lookup, **not GPS proof or AI verification of a runner's movement**. It stores only a coarse locality label (e.g. city and country) and caches queries in SQLite. A non-matching place is rejected; geocoder outages return a useful error rather than inventing an answer.

To enable this feature, first read the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/). The public server requires a distinctive contactable User-Agent, proper attribution (**© OpenStreetMap contributors**), local caching, and **a maximum of one request per second** from your single bot process. It must not be used for bulk geocoding or autocomplete. The integration uses an async adapter, a shared lock, 1.1-second throttling and persistent cache. Set `GEOCODER_USER_AGENT` only after deciding to use this service and following those rules. Leave it unset to disable location lookup without breaking run logging. If you scale beyond a single bot process, switch to a commercial/self-hosted geocoder instead.

### Setup

Python 3.10+ is required.

```bash
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and configure:

```ini
BOT_TOKEN=your_bot_token
DB_PATH=memory/main.db
OWNER_ID=your_numeric_discord_user_id
PROOF_CHANNEL_ID=your_private_discord_text_channel_id
# Optional after reading Nominatim policy:
# GEOCODER_USER_AGENT=VelocityBot/1.0 (admin@example.com)
```

Then run `python main.py`. Leave optional values unset if you do not need them. **Never commit your real .env file.**

The existing `runs` table is upgraded *in place* on startup using additive migrations, preserving previously logged runs. All historical runs are initially **pending** until you review them.

**Repository privacy warning:** `memory/main.db` has previously been committed publicly. A .gitignore cannot retroactively protect it: back up data and remove the tracked copy/history appropriately before relying on GitHub for privacy.

### Architecture and next milestone

- `classes/database.py`: SQLite schema migrations, run storage, proof links and review decisions
- `bot/utils/location.py`: throttled place-name geocoding and cache
- `bot/utils/evidence.py`: image/elevation validation and private Discord proof storage
- `bot/ui/running.py`: Components V2 views, modal, review buttons
- `bot/cogs/running.py`: slash commands and owner authorization

**Next:** build a shared `activities` model for **running, cycling and swimming**, with discipline-specific measurements and verified leaderboards. Cycling should track distance, duration, speed and optional climbing; swimming should track pool/open water, distance, duration and pace per 100m. Keep sports separate in rankings so a 5km swim is not compared with a 5km run.

Run tests with `python -m unittest discover -s tests -v`.
