import unittest

from bot.utils.activity import activity_metric, validate_activity
from classes.database import Database


class MultisportValidationTests(unittest.TestCase):
    def test_cycling(self):
        self.assertEqual(
            validate_activity("cycling", "Morning ride", "20km", "40:00",
                              elevation_m=200, notes="steady")[0:4],
            ("Morning ride", 20000, 2400, 200),
        )
        self.assertEqual(activity_metric("cycling", 20000, 2400), "30.0 km/h")

    def test_swimming(self):
        result = validate_activity(
            "swimming", "Laps", "1500m", "30:00",
            swim_type="pool", pool_length_m=25,
        )
        self.assertEqual(result[1:3], (1500, 1800))
        self.assertEqual(result[4:6], ("pool", 25))
        self.assertEqual(activity_metric("swimming", 1500, 1800), "2:00 /100m")

    def test_open_water(self):
        result = validate_activity(
            "swimming", "Lake swim", "2km", "45:00", swim_type="open_water"
        )
        self.assertEqual(result[4], "open_water")

    def test_invalid_sport_options(self):
        invalid = [
            ("cycling", "500m", "5:00", {}),
            ("swimming", "2km", "30:00", {"swim_type": "pool", "pool_length_m": 33}),
            ("swimming", "100m", "2:00", {"swim_type": "open_water", "pool_length_m": 25}),
            ("running", "5km", "25:00", {"swim_type": "pool"}),
            ("cycling", "20km", "40:00", {"notes": "x" * 201}),
            ("swimming", "1km", "20:00", {"elevation_m": 50}),
            ("triathlon", "5km", "25:00", {}),
        ]
        for sport, dist, dur, options in invalid:
            with self.subTest(sport=sport, distance=dist, options=options):
                with self.assertRaises(ValueError):
                    validate_activity(sport, "test", dist, dur, **options)


class MultisportDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database(":memory:")
        await self.db.create_tables()

    async def asyncTearDown(self):
        await self.db.close()

    async def test_multisport_filtering_and_legacy_api(self):
        old_id = await self.db.add_run(1, "5K", 5000, 1500, guild_id=80)
        ride_id = await self.db.add_activity(
            1, "cycling", "Ride", 20000, 2400, guild_id=80, elevation_gain_m=250,
        )
        swim_id = await self.db.add_activity(
            1, "swimming", "Swim", 1500, 1800, guild_id=80,
            swim_type="pool", pool_length_m=25,
        )
        self.assertEqual(await self.db.count_runs(1), 1)
        self.assertEqual(await self.db.count_activities(1), 3)
        self.assertEqual(await self.db.count_activities(1, sport="swimming"), 1)
        self.assertEqual((await self.db.get_runs(1))[0]["id"], old_id)
        self.assertEqual((await self.db.get_activities(1, sport="cycling"))[0]["id"], ride_id)
        self.assertEqual((await self.db.get_run(swim_id))["pool_length_m"], 25)
        self.assertEqual((await self.db.get_stats(1))["total_distance"], 5000)

    async def test_guild_leaderboard_only_verified(self):
        a = await self.db.add_activity(1, "cycling", "A", 10000, 1800, guild_id=100)
        b = await self.db.add_activity(2, "cycling", "B", 15000, 1800, guild_id=100)
        c = await self.db.add_activity(3, "cycling", "C", 100000, 8000, guild_id=200)
        d = await self.db.add_activity(4, "running", "D", 30000, 8000, guild_id=100)
        e = await self.db.add_activity(4, "cycling", "E", 60000, 7000, guild_id=None)
        await self.db.review_run(a, 99, "verified")
        await self.db.review_run(b, 99, "verified")
        await self.db.review_run(c, 99, "verified")
        await self.db.review_run(d, 99, "verified")
        await self.db.review_run(e, 99, "verified")
        rows = await self.db.get_leaderboard(100, "cycling", "all")
        self.assertEqual([r["user_id"] for r in rows], [2, 1])
        self.assertEqual(rows[0]["meters"], 15000)
        self.assertEqual(len(await self.db.get_leaderboard(100, "cycling", "week")), 2)

    async def test_personal_records_and_recap(self):
        await self.db.add_activity(1, "cycling", "Fast", 20000, 1800)
        await self.db.add_activity(1, "cycling", "Slow", 20000, 2100)
        long_id = await self.db.add_activity(1, "cycling", "Long", 35000, 3600)
        records = await self.db.get_personal_records(1, "cycling")
        self.assertEqual(records["longest"]["id"], long_id)
        self.assertEqual(records["fastest"]["duration"], 1800)
        self.assertEqual(records["distance"], 20000)
        weekly = await self.db.get_weekly_summary(1)
        self.assertEqual(weekly[0]["count"], 3)


    async def test_private_export_scope_and_persistence(self):
        await self.db.add_activity(
            1, "swimming", "Pool practice", 500, 900,
            swim_type="pool", notes="Easy",
        )
        await self.db.add_activity(2, "cycling", "Other user", 20000, 3600)
        first = await self.db.export_user_activities(1)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["name"], "Pool practice")
        self.assertEqual(first[0]["sport"], "swimming")
        self.assertEqual(first[0]["notes"], "Easy")
        self.assertNotIn("user_id", first[0])
        self.assertNotIn("proof_message_id", first[0])

    async def test_idempotent_migration(self):
        await self.db.add_run(1, "Old", 5000, 1600)
        await self.db.create_tables()
        self.assertEqual((await self.db.get_runs(1))[0]["sport"], "running")

