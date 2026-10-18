"""Velocity Discord bot entry class."""

import logging

import discord
from discord.ext import commands

from classes.database import db

logger = logging.getLogger(__name__)


class Bot(commands.Bot):
    COGS = ("running",)

    def __init__(self):
        self.db = db
        super().__init__(command_prefix="?", intents=discord.Intents.default())

    async def setup_hook(self):
        await self.db.create_tables()
        logger.info("Database connected")

        for cog in self.COGS:
            try:
                await self.load_extension(f"bot.cogs.{cog}")
            except commands.ExtensionError:
                logger.exception("Failed to load cog: %s", cog)
                raise

        await self.tree.sync()
        logger.info("Loaded %d cogs and synced application commands", len(self.COGS))

    async def on_ready(self):
        logger.info("Logged in as %s", self.user)

    async def close(self):
        try:
            await self.db.close()
        finally:
            await super().close()
