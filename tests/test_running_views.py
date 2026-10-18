import unittest

import discord

from bot.ui.running import (
    LogRunModal,
    RunHistoryView,
    RunPanelView,
    RunReceiptView,
    RunStatsView,
)


class RunningViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_layout_construction(self):
        stats = {
            "run_count": 1,
            "total_distance": 5000,
            "total_duration": 1500,
            "longest_distance": 5000,
        }
        for view in [
            RunPanelView(None, 123, stats),
            RunReceiptView("5K", 5000, 1500),
            RunStatsView(stats),
            RunHistoryView(None, 123, [{"name": "5K", "distance": 5000, "duration": 1500}], 1),
        ]:
            with self.subTest(view=type(view).__name__):
                self.assertIsInstance(view, discord.ui.LayoutView)
                self.assertEqual(len(view.children), 1)

        modal = LogRunModal(None)
        self.assertIsInstance(modal, discord.ui.Modal)

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
