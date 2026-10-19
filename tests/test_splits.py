import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import discord

from bot.utils.splits import (
    split_step, expected_segments, parse_manual_splits, parse_ocr_rows,
    display_split, validate_splits,
)
from bot.utils.emojis import emoji_for, emoji_text
from bot.ui.splits import ManualSplitsModal, OCRSplitsModal, OCRSplitPreviewView
from bot.ui.hub import HubView
from classes.database import Database


class SplitUtilityTests(unittest.TestCase):
    def test_step_size_for_all_sports(self):
        self.assertEqual(split_step("running"), 1000)
        self.assertEqual(split_step("cycling"), 1000)
        self.assertEqual(split_step("swimming"), 100)

    def test_last_partial_interval_and_normalized_pace(self):
        self.assertEqual(expected_segments("running", 2500), [1000, 1000, 500])
        self.assertEqual(expected_segments("swimming", 250), [100, 100, 50])
        self.assertIn("/100m", display_split("swimming", 50, 60))
        self.assertNotIn("/km", display_split("swimming", 50, 60))
        self.assertIn("km/h", display_split("cycling", 1000, 120))

    def test_manual_times(self):
        self.assertEqual(parse_manual_splits("5:10\n5:15\n5:20"), [310, 315, 320])
        self.assertEqual(parse_manual_splits("1 5:10\n2 5:15"), [310, 315])
        self.assertEqual(parse_manual_splits("1. 2:05,2. 2:07"), [125, 127])

    def test_bad_manual(self):
        for text in ("", "1 5:10\n3 5:11", "5:70", "5:10\nbanana", "0:00"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_manual_splits(text)

    def test_valid_splits_and_tolerance(self):
        self.assertEqual(
            validate_splits("running", 2000, 600, [295, 305]),
            [(1000, 295), (1000, 305)]
        )
        self.assertEqual(
            validate_splits("swimming", 250, 350, [120, 140, 90]),
            [(100, 120), (100, 140), (50, 90)]
        )
        with self.assertRaises(ValueError):
            validate_splits("running", 2000, 600, [290])
        with self.assertRaises(ValueError):
            validate_splits("running", 2000, 600, [90, 90])

    def test_ocr_parses_sequential_km_rows(self):
        text = "Splits\nKm Pace\n1 5:10\n2 5:15\n3 5:20\n"
        self.assertEqual(parse_ocr_rows(text, "running", 3000), [310, 315, 320])

    def test_ocr_swim_cumulative_100m_rows(self):
        text = "Distance Pace\n100 2:00\n200 2:10\n300 2:05\n"
        self.assertEqual(parse_ocr_rows(text, "swimming", 300), [120, 130, 125])

    def test_ocr_refuses_uncertain_or_incomplete_rows(self):
        with self.assertRaises(ValueError):
            parse_ocr_rows("Total 15:25\nAverage 5:08", "running", 3000)
        with self.assertRaises(ValueError):
            parse_ocr_rows("1 5:12\n3 5:08", "running", 2000)

    def test_large_split_bound(self):
        with self.assertRaises(ValueError):
            expected_segments("swimming", 10100)

    def test_configured_custom_emoji_and_fallback(self):
        with patch.dict(os.environ, {
            "VELOCITY_EMOJI_RUNNING": "<:runner:123456789012345678>",
            "VELOCITY_EMOJI_SWIMMING": "not-valid",
        }):
            self.assertIsInstance(emoji_for("running"), discord.PartialEmoji)
            self.assertEqual(emoji_text("running"), "<:runner:123456789012345678>")
            self.assertEqual(emoji_for("swimming"), "🏊")


class SplitStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database(":memory:")
        await self.db.create_tables()

    async def asyncTearDown(self):
        await self.db.close()

    async def test_save_replace_and_lock_after_review(self):
        run_id = await self.db.add_activity(123, "running", "5K", 2000, 600)
        self.assertTrue(await self.db.save_activity_splits(run_id, 123, [290, 310]))
        self.assertEqual(len(await self.db.get_activity_splits(run_id)), 2)
        self.assertTrue(await self.db.save_activity_splits(run_id, 123, [295, 305]))
        rows = await self.db.get_activity_splits(run_id)
        self.assertEqual(rows[0]["duration_seconds"], 295)
        self.assertFalse(await self.db.save_activity_splits(run_id, 999, [300, 300]))
        await self.db.review_run(run_id, 700, "verified")
        self.assertFalse(await self.db.save_activity_splits(run_id, 123, [300, 300]))
        self.assertEqual((await self.db.get_activity_splits(run_id))[0]["duration_seconds"], 295)

    async def test_swim_100m_splits_and_migration(self):
        activity_id = await self.db.add_activity(
            123, "swimming", "Pool", 250, 350, swim_type="pool"
        )
        await self.db.create_tables()
        self.assertTrue(await self.db.save_activity_splits(
            activity_id, 123, [120, 140, 90]
        ))
        self.assertEqual(
            [r["segment_meters"] for r in await self.db.get_activity_splits(activity_id)],
            [100, 100, 50],
        )

    async def test_reject_invalid_split_totals_without_wiping_old(self):
        activity_id = await self.db.add_activity(123, "cycling", "Ride", 2000, 240)
        await self.db.save_activity_splits(activity_id, 123, [120, 120])
        with self.assertRaises(ValueError):
            await self.db.save_activity_splits(activity_id, 123, [70, 70])
        self.assertEqual(len(await self.db.get_activity_splits(activity_id)), 2)


class SplitViewsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database(":memory:")
        await self.db.create_tables()
        self.bot = SimpleNamespace(
            db=self.db, owner_id=999, proof_channel_id=None,
            location_resolver=SimpleNamespace(resolve=None),
        )

    async def asyncTearDown(self):
        await self.db.close()

    async def test_all_sports_split_pages_and_modals(self):
        for sport, distance, duration in (
            ("running", 2000, 600),
            ("cycling", 2000, 240),
            ("swimming", 200, 260),
        ):
            activity_id = await self.db.add_activity(
                123, sport, sport, distance, duration
            )
            hub = await HubView.build(
                self.bot, 123, 888, screen="splits",
                activity_id=activity_id, sport=sport,
            )
            self.assertEqual(hub.payload["sport"], sport)
            self.assertIsInstance(hub, discord.ui.LayoutView)
            self.assertEqual(len(ManualSplitsModal(hub).children), 1)
            self.assertIsInstance(
                OCRSplitsModal(hub).children[0].component, discord.ui.FileUpload
            )
            times = [duration // 2, duration - duration // 2]
            preview = OCRSplitPreviewView(hub, hub.payload, times)
            self.assertIsInstance(preview, discord.ui.LayoutView)

    async def test_other_users_cannot_see_split_page(self):
        activity_id = await self.db.add_activity(123, "running", "Run", 2000, 600)
        hub = await HubView.build(
            self.bot, 555, 888, screen="splits", activity_id=activity_id
        )
        self.assertIsNone(hub.payload)
