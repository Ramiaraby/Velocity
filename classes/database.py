"""Async SQLite store for running activities, evidence and manual review."""

import os
from pathlib import Path

import aiosqlite

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
        # Additive migrations keep pre-existing runs and IDs intact.
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
        await self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_runs_user_id ON runs(user_id, id DESC)
        """)
        await self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_runs_review ON runs(verification_status, id DESC)
        """)
        await self.connection.commit()

    async def add_run(
        self, user_id: int, name: str, meters: int, seconds: int,
        *, elevation_gain_m: int | None = None,
        location_name: str | None = None, location_status: str = "not_provided"
    ) -> int:
        assert self.connection is not None
        async with self.connection.execute(
            """INSERT INTO runs
               (user_id, distance, duration, name, elevation_gain_m, location_name, location_status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, meters, seconds, name, elevation_gain_m, location_name, location_status),
        ) as cursor:
            run_id = cursor.lastrowid
        await self.connection.commit()
        return int(run_id)

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

    async def get_pending_runs(self, *, limit: int = 10) -> list[dict]:
        assert self.connection is not None
        async with self.connection.execute(
            """SELECT * FROM runs WHERE verification_status = 'pending'
               ORDER BY id DESC LIMIT ?""", (limit,)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

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
        assert self.connection is not None
        async with self.connection.execute(
            "SELECT COUNT(*) FROM runs WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0])

    async def get_runs(self, user_id: int, *, limit: int = 5, offset: int = 0) -> list[dict]:
        assert self.connection is not None
        async with self.connection.execute(
            """SELECT * FROM runs WHERE user_id = ?
               ORDER BY id DESC LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def get_stats(self, user_id: int) -> dict:
        assert self.connection is not None
        async with self.connection.execute(
            """SELECT COUNT(*) AS run_count,
                      COALESCE(SUM(distance), 0) AS total_distance,
                      COALESCE(SUM(duration), 0) AS total_duration,
                      COALESCE(MAX(distance), 0) AS longest_distance,
                      COUNT(CASE WHEN verification_status = 'verified' THEN 1 END) AS verified_runs
               FROM runs WHERE user_id = ?""",
            (user_id,),
        ) as cursor:
            return dict(await cursor.fetchone())


db = Database()
