import aiosqlite
import os
from dotenv import load_dotenv
from functools import wraps

load_dotenv()

class Database:
    def __init__(self, path=os.environ["DB_PATH"]):
        self.path = path
        self.connection: aiosqlite.Connection | None = None

    async def connect(self):
        if self.connection is None:
            self.connection = await aiosqlite.connect(self.path)
            self.connection.row_factory = aiosqlite.Row
    async def close(self):
        if self.connection is not None:
            self.connection = None

    async def create_tables(self):
        await self.connect()
        async with self.connection.cursor() as cursor:
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                distance INTEGER NOT NULL,
                duration INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

db = Database()