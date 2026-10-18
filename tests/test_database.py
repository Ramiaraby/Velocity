import unittest

from classes.database import Database


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database(":memory:")
        await self.db.create_tables()

    async def asyncTearDown(self):
        await self.db.close()

    async def test_history_is_user_scoped_and_ordered(self):
        await self.db.add_run(100, "First", 5000, 1500)
        await self.db.add_run(200, "Other runner", 3000, 900)
        second_id = await self.db.add_run(100, "Second", 10000, 3300)
        self.assertEqual(await self.db.count_runs(100), 2)
        self.assertEqual(await self.db.count_runs(200), 1)
        self.assertEqual((await self.db.get_runs(100, limit=1))[0]["name"], "Second")
        self.assertEqual((await self.db.get_runs(100, limit=1, offset=1))[0]["name"], "First")
        self.assertEqual((await self.db.get_run(second_id))["verification_status"], "pending")

    async def test_stats_are_weighted_by_distance(self):
        await self.db.add_run(100, "Easy", 5000, 1500)
        await self.db.add_run(100, "Long", 10000, 3600)
        stats = await self.db.get_stats(100)
        self.assertEqual(stats["run_count"], 2)
        self.assertEqual(stats["total_distance"], 15000)
        self.assertEqual(stats["total_duration"], 5100)
        self.assertEqual(stats["longest_distance"], 10000)
        self.assertEqual(stats["verified_runs"], 0)

    async def test_empty_stats(self):
        stats = await self.db.get_stats(500)
        self.assertEqual(stats["run_count"], 0)
        self.assertEqual(stats["total_distance"], 0)

    async def test_review_is_atomic_and_owner_recorded(self):
        run_id = await self.db.add_run(42, "Trail", 6000, 2200,
                                       elevation_gain_m=145, location_name="Beirut, Lebanon",
                                       location_status="found")
        self.assertTrue(await self.db.attach_proof(run_id, 42, 1001, 2002))
        self.assertFalse(await self.db.attach_proof(run_id, 84, 1001, 2003))
        self.assertFalse(await self.db.attach_proof(run_id, 42, 1001, 2003))
        self.assertTrue(await self.db.review_run(run_id, 12345, "verified", "Checked"))
        self.assertFalse(await self.db.review_run(run_id, 12345, "rejected"))
        self.assertFalse(await self.db.attach_proof(run_id, 42, 1001, 2003))
        row = await self.db.get_run(run_id)
        self.assertEqual(row["verification_status"], "verified")
        self.assertEqual(row["verified_by"], 12345)
        self.assertEqual(row["elevation_gain_m"], 145)
        self.assertEqual(row["location_name"], "Beirut, Lebanon")
        self.assertEqual(row["proof_message_id"], 2002)
        self.assertEqual((await self.db.get_stats(42))["verified_runs"], 1)
        self.assertEqual(await self.db.get_pending_runs(), [])

    async def test_location_cache_including_misses(self):
        await self.db.cache_place("beirut", "Beirut, Lebanon")
        self.assertEqual(await self.db.get_cached_place("beirut"), (True, "Beirut, Lebanon"))
        await self.db.cache_place("unknown", None)
        self.assertEqual(await self.db.get_cached_place("unknown"), (True, None))
        self.assertEqual(await self.db.get_cached_place("missing"), (False, None))

    async def test_migration_of_existing_database(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import aiosqlite
        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "old.db")
            async with aiosqlite.connect(path) as connection:
                await connection.execute("""
                    CREATE TABLE runs(
                        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                        distance INTEGER NOT NULL, duration INTEGER NOT NULL,
                        name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                await connection.execute(
                    "INSERT INTO runs(id, user_id, distance, duration, name) VALUES (7, 42, 5000, 1500, 'Old 5k')"
                )
                await connection.commit()
            upgraded = Database(path)
            try:
                await upgraded.create_tables()
                await upgraded.create_tables()
                old_run = await upgraded.get_run(7)
                self.assertEqual(old_run["name"], "Old 5k")
                self.assertEqual(old_run["verification_status"], "pending")
                self.assertIsNone(old_run["elevation_gain_m"])
            finally:
                await upgraded.close()
