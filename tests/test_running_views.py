import unittest

import discord

from bot.ui.running import (
    LogRunModal, PendingRunsView, ReviewRunView,
    RunHistoryView, RunPanelView, RunReceiptView, RunStatsView,
)


class RunningViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_layout_construction(self):
        stats = {
            "run_count": 1, "total_distance": 5000,
            "total_duration": 1500, "longest_distance": 5000, "verified_runs": 0,
        }
        run = {
            "id": 1, "name": "5K", "user_id": 123, "distance": 5000,
            "duration": 1500, "verification_status": "pending",
            "elevation_gain_m": 50, "location_name": "Beirut, Lebanon",
        }
        for view in [
            RunPanelView(None, 123, stats),
            RunReceiptView("5K", 5000, 1500, run_id=1, elevation_gain_m=50),
            RunStatsView(stats),
            RunHistoryView(None, 123, [run], 1),
            ReviewRunView(None, 123, run),
            PendingRunsView([run]),
        ]:
            with self.subTest(view=type(view).__name__):
                self.assertIsInstance(view, discord.ui.LayoutView)
                self.assertEqual(len(view.children), 1)

        modal = LogRunModal(None)
        self.assertIsInstance(modal, discord.ui.Modal)
        self.assertEqual(len(modal.children), 5)

    async def test_history_pagination_buttons(self):
        runs = [{"name": "Easy", "distance": 5000, "duration": 1500}]
        first = RunHistoryView(None, 123, runs, total=8, page=0)
        actions = first.children[0].children[-1]
        self.assertTrue(actions.previous.disabled)
        self.assertFalse(actions.next.disabled)
        second = RunHistoryView(None, 123, runs, total=8, page=1)
        actions = second.children[0].children[-1]
        self.assertFalse(actions.previous.disabled)
        self.assertTrue(actions.next.disabled)

    async def test_review_buttons_disappear_after_decision(self):
        run = {
            "id": 1, "user_id": 123, "name": "5K", "distance": 5000,
            "duration": 1500, "verification_status": "pending",
        }
        pending = ReviewRunView(None, 999, run)
        self.assertIsInstance(pending.children[0].children[-1], discord.ui.ActionRow)
        run["verification_status"] = "verified"
        reviewed = ReviewRunView(None, 999, run)
        self.assertNotIsInstance(reviewed.children[0].children[-1], discord.ui.ActionRow)
