"""Async SQLite storage for Velocity's running, cycling, and swimming activities.

The existing 'runs' table name is deliberately retained for lossless,
additive migrations. Its 'sport' column distinguishes all three disciplines.
"""

import os
from pathlib import Path

import aiosqlite

SPORTS = ("running", "cycling", "swimming")
ADDED_COLUMNS = {
    "elevation_gain_m": "INTEGER",
    "location_name": "TEXT",
    "location_status": "TEXT NOT NULL DEFAULT 'not_provided'",
    "proof_channel_id": "INTEGER",
    "proof_message_id": "INTEGER",
    "verification_status": "TEXT NOT NULL DEFAULT 'pending'",
    "verified_by": "INTEGER",
    "verified_at": "TEXT",
    "moderation_note": "TEXT",
    "sport": "TEXT NOT NULL DEFAULT 'running'",
    "guild_id": "INTEGER",
    "swim_type": "TEXT",
    "pool_length_m": "INTEGER",
    "notes": "TEXT",
}


class Database:
    def __init__(self, path: str | None = None):
        self.path = path or os.getenv("DB_PATH", "memory/main.db")
        self.connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self.connection is None:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self.connection = await aiosqlite.connect(self.path)
            self.connection.row_factory = aiosqlite.Row

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None

    async def create_tables(self) -> None:
        await self.connect()
        assert self.connection is not None
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                distance INTEGER NOT NULL,
                duration INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        async with self.connection.execute("PRAGMA table_info(runs)") as cursor:
            columns = {row["name"] for row in await cursor.fetchall()}
        for name, sql_type in ADDED_COLUMNS.items():
            if name not in columns:
                await self.connection.execute(f"ALTER TABLE runs ADD COLUMN {name} {sql_type}")
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS place_cache (
                query TEXT PRIMARY KEY,
                display_name TEXT,
                looked_up_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_user_id ON runs(user_id, id DESC)"
        )
        await self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_review ON runs(verification_status, id DESC)"
        )
        await self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_activities_rank
            ON runs(guild_id, sport, verification_status, created_at)
        """)
        await self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_activities_user_sport
            ON runs(user_id, sport, id DESC)
        """)
        await self.connection.commit()

    async def add_activity(
        self, user_id: int, sport: str, name: str, meters: int, seconds: int,
        *, guild_id: int | None = None, elevation_gain_m: int | None = None,
        location_name: str | None = None, location_status: str = "not_provided",
        swim_type: str | None = None, pool_length_m: int | None = None,
        notes: str | None = None,
    ) -> int:
        if sport not in SPORTS:
            raise ValueError("Unknown activity type.")
        assert self.connection is not None
        async with self.connection.execute(
            """INSERT INTO runs (
                user_id, sport, name, distance, duration, guild_id,
                elevation_gain_m, location_name, location_status,
                swim_type, pool_length_m, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, sport, name, meters, seconds, guild_id,
             elevation_gain_m, location_name, location_status,
             swim_type, pool_length_m, notes),
        ) as cursor:
            activity_id = cursor.lastrowid
        await self.connection.commit()
        return int(activity_id)

    async def add_run(
        self, user_id: int, name: str, meters: int, seconds: int,
        *, elevation_gain_m: int | None = None,
        location_name: str | None = None, location_status: str = "not_provided",
        guild_id: int | None = None,
    ) -> int:
        return await self.add_activity(
            user_id, "running", name, meters, seconds, guild_id=guild_id,
            elevation_gain_m=elevation_gain_m, location_name=location_name,
            location_status=location_status,
        )

    async def get_run(self, run_id: int) -> dict | None:
        assert self.connection is not None
        async with self.connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def attach_proof(self, run_id: int, user_id: int, channel_id: int, message_id: int) -> bool:
        assert self.connection is not None
        async with self.connection.execute(
            """UPDATE runs SET proof_channel_id = ?, proof_message_id = ?
               WHERE id = ? AND user_id = ? AND verification_status = 'pending'
               AND proof_message_id IS NULL""",
            (channel_id, message_id, run_id, user_id),
        ) as cursor:
            updated = cursor.rowcount == 1
        await self.connection.commit()
        return updated

    async def review_run(self, run_id: int, owner_id: int, status: str, note: str | None = None) -> bool:
        if status not in {"verified", "rejected"}:
            raise ValueError("Invalid verification status.")
        assert self.connection is not None
        async with self.connection.execute(
            """UPDATE runs SET verification_status = ?, verified_by = ?,
               verified_at = CURRENT_TIMESTAMP, moderation_note = ?
               WHERE id = ? AND verification_status = 'pending'""",
            (status, owner_id, note, run_id),
        ) as cursor:
            updated = cursor.rowcount == 1
        await self.connection.commit()
        return updated

    async def get_pending_runs(self, *, limit: int = 10, offset: int = 0) -> list[dict]:
        assert self.connection is not None
        async with self.connection.execute(
            """SELECT * FROM runs WHERE verification_status = 'pending'
               ORDER BY id DESC LIMIT ? OFFSET ?""", (limit, offset)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def count_pending_runs(self) -> int:
        assert self.connection is not None
        async with self.connection.execute(
            "SELECT COUNT(*) FROM runs WHERE verification_status = 'pending'"
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0])

    async def get_cached_place(self, query: str) -> tuple[bool, str | None]:
        assert self.connection is not None
        async with self.connection.execute(
            "SELECT display_name FROM place_cache WHERE query = ?", (query,)
        ) as cursor:
            row = await cursor.fetchone()
        return (True, row["display_name"]) if row else (False, None)

    async def cache_place(self, query: str, display_name: str | None) -> None:
        assert self.connection is not None
        await self.connection.execute(
            """INSERT INTO place_cache(query, display_name) VALUES (?, ?)
               ON CONFLICT(query) DO UPDATE SET display_name = excluded.display_name,
               looked_up_at = CURRENT_TIMESTAMP""",
            (query, display_name),
        )
        await self.connection.commit()

    async def count_runs(self, user_id: int) -> int:
        return await self.count_activities(user_id, sport="running")

    async def count_activities(self, user_id: int, *, sport: str | None = None) -> int:
        assert self.connection is not None
        if sport and sport not in SPORTS:
            raise ValueError("Unknown activity type.")
        query = "SELECT COUNT(*) FROM runs WHERE user_id = ?"
        params: list = [user_id]
        if sport:
            query += " AND sport = ?"
            params.append(sport)
        async with self.connection.execute(query, tuple(params)) as cursor:
            row = await cursor.fetchone()
        return int(row[0])

    async def get_runs(self, user_id: int, *, limit: int = 5, offset: int = 0) -> list[dict]:
        return await self.get_activities(user_id, sport="running", limit=limit, offset=offset)

    async def get_activities(
        self, user_id: int, *, sport: str | None = None,
        limit: int = 5, offset: int = 0,
    ) -> list[dict]:
        assert self.connection is not None
        if sport and sport not in SPORTS:
            raise ValueError("Unknown activity type.")
        query = "SELECT * FROM runs WHERE user_id = ?"
        params: list = [user_id]
        if sport:
            query += " AND sport = ?"
            params.append(sport)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend((min(max(limit, 1), 100), max(offset, 0)))
        async with self.connection.execute(query, tuple(params)) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def get_stats(self, user_id: int) -> dict:
        return await self.get_activity_stats(user_id, sport="running")

    async def get_activity_stats(self, user_id: int, *, sport: str | None = None) -> dict:
        assert self.connection is not None
        if sport and sport not in SPORTS:
            raise ValueError("Unknown activity type.")
        query = """
            SELECT COUNT(*) AS run_count,
                   COALESCE(SUM(distance), 0) AS total_distance,
                   COALESCE(SUM(duration), 0) AS total_duration,
                   COALESCE(MAX(distance), 0) AS longest_distance,
                   COUNT(CASE WHEN verification_status = 'verified' THEN 1 END) AS verified_runs,
                   COALESCE(SUM(elevation_gain_m), 0) AS total_elevation
            FROM runs WHERE user_id = ?
        """
        params: list = [user_id]
        if sport:
            query += " AND sport = ?"
            params.append(sport)
        async with self.connection.execute(query, tuple(params)) as cursor:
            return dict(await cursor.fetchone())

    async def get_weekly_summary(self, user_id: int) -> list[dict]:
        assert self.connection is not None
        async with self.connection.execute(
            """SELECT sport, COUNT(*) AS count, SUM(distance) AS meters,
                      SUM(duration) AS seconds,
                      COUNT(CASE WHEN verification_status='verified' THEN 1 END) AS verified
               FROM runs WHERE user_id = ?
                 AND created_at >= datetime('now', '-7 days')
               GROUP BY sport ORDER BY sport""", (user_id,)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def get_leaderboard(
        self, guild_id: int, sport: str, period: str, *, limit: int = 10
    ) -> list[dict]:
        if sport not in SPORTS:
            raise ValueError("Unknown activity type.")
        days = {"week": 7, "month": 30, "all": None}
        if period not in days:
            raise ValueError("Unknown leaderboard period.")
        assert self.connection is not None
        sql = """
            SELECT user_id, COUNT(*) AS count,
                   SUM(distance) AS meters, SUM(duration) AS seconds
            FROM runs
            WHERE guild_id = ? AND sport = ? AND verification_status = 'verified'
        """
        params: list = [guild_id, sport]
        if days[period] is not None:
            sql += " AND created_at >= datetime('now', ?)"
            params.append(f"-{days[period]} days")
        sql += " GROUP BY user_id ORDER BY meters DESC, seconds ASC, user_id ASC LIMIT ?"
        params.append(min(max(limit, 1), 25))
        async with self.connection.execute(sql, tuple(params)) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def get_personal_records(self, user_id: int, sport: str) -> dict:
        """All-time user history: longest activity and exact-distance fastest time."""
        if sport not in SPORTS:
            raise ValueError("Unknown activity type.")
        assert self.connection is not None
        distance = {"running": 5000, "cycling": 20000, "swimming": 100}[sport]
        async with self.connection.execute(
            """SELECT id, name, distance, duration FROM runs
               WHERE user_id = ? AND sport = ?
               ORDER BY distance DESC, id DESC LIMIT 1""",
            (user_id, sport),
        ) as cursor:
            longest = await cursor.fetchone()
        async with self.connection.execute(
            """SELECT id, name, distance, duration FROM runs
               WHERE user_id = ? AND sport = ? AND distance = ?
               ORDER BY duration ASC, id ASC LIMIT 1""",
            (user_id, sport, distance),
        ) as cursor:
            fastest = await cursor.fetchone()
        return {
            "distance": distance,
            "longest": dict(longest) if longest else None,
            "fastest": dict(fastest) if fastest else None,
        }

    async def update_activity_details(
        self, activity_id: int, user_id: int, *,
        location_name: str | None, location_status: str,
        notes: str | None,
    ) -> bool:
        """Only an activity's owner can edit metadata before moderation."""
        if notes is not None and len(notes) > 200:
            raise ValueError("Notes may not exceed 200 characters.")
        assert self.connection is not None
        async with self.connection.execute(
            """UPDATE runs SET location_name = ?, location_status = ?, notes = ?
               WHERE id = ? AND user_id = ? AND verification_status = 'pending'""",
            (location_name, location_status, notes, activity_id, user_id),
        ) as cursor:
            updated = cursor.rowcount == 1
        await self.connection.commit()
        return updated

    async def export_user_activities(self, user_id: int, *, limit: int = 10001) -> list[dict]:
        """Owner-scoped raw data export. An extra row signals truncation."""
        assert self.connection is not None
        async with self.connection.execute(
            """SELECT id, sport, name, distance, duration, created_at,
                      elevation_gain_m, location_name, location_status,
                      swim_type, pool_length_m, notes, verification_status,
                      verified_at, moderation_note
               FROM runs WHERE user_id = ? ORDER BY id ASC LIMIT ?""",
            (user_id, min(max(limit, 1), 10001)),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


db = Database()
