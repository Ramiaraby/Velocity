import os
import unittest
from unittest.mock import patch

from bot.bot import Bot


class BotConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_id_survives_discord_bot_initialization(self):
        with patch.dict(os.environ, {
            "OWNER_ID": "123456789",
            "PROOF_CHANNEL_ID": "234567890",
        }):
            bot = Bot()
        self.assertEqual(bot.owner_id, 123456789)
        self.assertEqual(bot.proof_channel_id, 234567890)
        self.assertEqual(bot.COGS, ("hub",))
        await bot.close()

    async def test_missing_owner_stays_none(self):
        with patch.dict(os.environ, {"OWNER_ID": ""}):
            bot = Bot()
        self.assertIsNone(bot.owner_id)
        await bot.close()
