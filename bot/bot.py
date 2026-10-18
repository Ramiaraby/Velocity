"""Velocity Discord bot entry class."""

import logging
import os

import discord
from discord.ext import commands

from bot.utils.location import LocationResolver
from classes.database import db

logger = logging.getLogger(__name__)


def env_snowflake(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        result = int(value)
        if result <= 0:
            raise ValueError
        return result
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive Discord ID") from exc


class Bot(commands.Bot):
    COGS = ("running", "multisport")

    def __init__(self):
        self.db = db
        self.owner_id = env_snowflake("OWNER_ID")
        self.proof_channel_id = env_snowflake("PROOF_CHANNEL_ID")
        self.location_resolver = LocationResolver(self.db)
        super().__init__(command_prefix="?", intents=discord.Intents.default())

    async def setup_hook(self):
        await self.db.create_tables()
        logger.info("Database connected")
        if not self.owner_id:
            logger.warning("OWNER_ID is unset; run verification commands are disabled.")
        if not self.proof_channel_id:
            logger.info("PROOF_CHANNEL_ID unset; optional image uploads are disabled.")
        if not self.location_resolver.user_agent:
            logger.info("GEOCODER_USER_AGENT unset; optional location lookup is disabled.")

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
