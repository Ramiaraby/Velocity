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
        await self.db.add_run(100, "Second", 10000, 3300)

        self.assertEqual(await self.db.count_runs(100), 2)
        self.assertEqual(await self.db.count_runs(200), 1)
        self.assertEqual((await self.db.get_runs(100, limit=1))[0]["name"], "Second")
        self.assertEqual((await self.db.get_runs(100, limit=1, offset=1))[0]["name"], "First")

    async def test_stats_are_weighted_by_distance(self):
        await self.db.add_run(100, "Easy", 5000, 1500)
        await self.db.add_run(100, "Long", 10000, 3600)
        stats = await self.db.get_stats(100)
        self.assertEqual(stats["run_count"], 2)
        self.assertEqual(stats["total_distance"], 15000)
        self.assertEqual(stats["total_duration"], 5100)
        self.assertEqual(stats["longest_distance"], 10000)

    async def test_empty_stats(self):
        stats = await self.db.get_stats(500)
        self.assertEqual(stats["run_count"], 0)
        self.assertEqual(stats["total_distance"], 0)
