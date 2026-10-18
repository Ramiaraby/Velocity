"""Small async SQLite store for Velocity runs."""

import os
from pathlib import Path

import aiosqlite


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
        await self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_runs_user_id
            ON runs(user_id, id DESC)
        """)
        await self.connection.commit()

    async def add_run(self, user_id: int, name: str, meters: int, seconds: int) -> None:
        assert self.connection is not None
        await self.connection.execute(
            "INSERT INTO runs (user_id, distance, duration, name) VALUES (?, ?, ?, ?)",
            (user_id, meters, seconds, name),
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
            """SELECT id, name, distance, duration, created_at
               FROM runs WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def get_stats(self, user_id: int) -> dict:
        assert self.connection is not None
        async with self.connection.execute(
            """SELECT COUNT(*) AS run_count,
                      COALESCE(SUM(distance), 0) AS total_distance,
                      COALESCE(SUM(duration), 0) AS total_duration,
                      COALESCE(MAX(distance), 0) AS longest_distance
               FROM runs WHERE user_id = ?""",
            (user_id,),
        ) as cursor:
            return dict(await cursor.fetchone())


db = Database()
