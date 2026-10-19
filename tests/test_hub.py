import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import discord

from classes.database import Database
from bot.ui.hub import (
    HubView, LogModal, ProofModal, DetailsModal, SportSelect,
    ActivitySelect, ReviewSelect, ReviewButton,
)


class HubTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database(":memory:")
        await self.db.create_tables()
        self.bot = SimpleNamespace(
            db=self.db,
            owner_id=900,
            proof_channel_id=None,
            location_resolver=SimpleNamespace(resolve=None),
        )

    async def asyncTearDown(self):
        await self.db.close()

    async def view(self, screen="home", *, user=123, sport="running",
                   period="week", activity_id=None, guild=55):
        return await HubView.build(
            self.bot, user, guild, screen=screen, sport=sport,
            period=period, activity_id=activity_id,
        )

    async def test_home_has_three_equal_sport_sections(self):
        home = await self.view()
        self.assertIsInstance(home, discord.ui.LayoutView)
        self.assertEqual(home.screen, "home")
        self.assertEqual(len(home.children), 2)
        sections = [x for x in home.children[1].children
                    if isinstance(x, discord.ui.Section)]
        self.assertEqual(len(sections), 3)
        self.assertEqual(home.user_id, 123)
        self.assertFalse(home.owner)

    async def test_each_sport_uses_same_template(self):
        for sport in ("running", "cycling", "swimming"):
            with self.subTest(sport=sport):
                view = await self.view("sport", sport=sport)
                self.assertIsInstance(view, discord.ui.LayoutView)
                self.assertEqual(view.sport, sport)
                modal = LogModal(view)
                self.assertEqual(len(modal.children), 5)
                self.assertTrue(all(isinstance(i, discord.ui.Label)
                                    for i in modal.children))
                self.assertIsInstance(modal, discord.ui.Modal)

    async def test_proof_uses_new_27_file_upload_component(self):
        view = await self.view("sport", sport="swimming")
        proof = ProofModal(view)
        self.assertEqual(len(proof.children), 1)
        self.assertIsInstance(proof.children[0].component, discord.ui.FileUpload)
        self.assertEqual(proof.children[0].component.max_values, 1)
        details = DetailsModal(view)
        self.assertEqual(len(details.children), 2)

    async def test_all_sports_history_and_private_detail(self):
        own = await self.db.add_activity(
            123, "cycling", "Easy spin", 20000, 3600, guild_id=55
        )
        stranger = await self.db.add_activity(
            456, "cycling", "Elsewhere", 20000, 3600, guild_id=55
        )
        history = await self.view("history", sport="cycling")
        self.assertEqual(history.payload["total"], 1)
        self.assertEqual(history.payload["records"][0]["id"], own)
        self.assertIsNotNone((await self.view("detail", activity_id=own)).payload)
        self.assertIsNone((await self.view("detail", activity_id=stranger)).payload)

    async def test_review_screen_owner_only_and_state(self):
        rid = await self.db.add_activity(
            123, "swimming", "Pool", 1000, 1500,
            swim_type="pool", guild_id=55
        )
        nonowner = await self.view("reviews")
        self.assertEqual(nonowner.payload["total"], 0)
        owner = await self.view("reviews", user=900)
        self.assertEqual(owner.payload["total"], 1)
        review = await self.view("review_detail", user=900, activity_id=rid)
        self.assertEqual(review.payload["sport"], "swimming")
        self.assertIsNone((await self.view(
            "review_detail", user=123, activity_id=rid)).payload)
        self.assertTrue(await self.db.review_run(rid, 900, "verified"))
        review_after = await self.view("review_detail", user=900, activity_id=rid)
        self.assertEqual(review_after.payload["verification_status"], "verified")
        self.assertEqual((await self.view("reviews", user=900)).payload["total"], 0)

    async def test_rankings_are_verified_and_server_scoped(self):
        a = await self.db.add_activity(
            123, "running", "5k", 5000, 1500, guild_id=55
        )
        await self.db.add_activity(
            456, "running", "10k", 10000, 3000, guild_id=55
        )
        await self.db.review_run(a, 900, "verified")
        view = await self.view("rankings", sport="running")
        self.assertEqual(len(view.payload), 1)
        self.assertEqual(view.payload[0]["user_id"], 123)

    async def test_pending_owner_queue_is_paginated(self):
        for i in range(8):
            await self.db.add_activity(123, "running", f"Run {i}", 5000, 1500)
        self.assertEqual(await self.db.count_pending_runs(), 8)
        page1 = await HubView.build(self.bot, 900, 55, screen="reviews", page=0)
        page2 = await HubView.build(self.bot, 900, 55, screen="reviews", page=1)
        self.assertEqual(len(page1.payload["records"]), 5)
        self.assertEqual(len(page2.payload["records"]), 3)

    async def test_pending_activity_details_only(self):
        rid = await self.db.add_activity(123, "cycling", "Test", 10000, 2000)
        self.assertFalse(await self.db.update_activity_details(
            rid, 789, location_name="Town", location_status="found", notes=None
        ))
        self.assertTrue(await self.db.update_activity_details(
            rid, 123, location_name="Town", location_status="found", notes="Easy"
        ))
        self.assertEqual((await self.db.get_run(rid))["notes"], "Easy")
        await self.db.review_run(rid, 900, "verified")
        self.assertFalse(await self.db.update_activity_details(
            rid, 123, location_name=None, location_status="not_provided", notes=None
        ))
