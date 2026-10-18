"""Slash commands for Velocity's run tracking."""

import discord
from discord import app_commands
from discord.ext import commands

from bot.ui.running import PAGE_SIZE, RunHistoryView, RunPanelView, RunReceiptView, RunStatsView
from bot.utils.running import validate_run


class RunningCog(commands.Cog, name="Running"):
    def __init__(self, bot):
        self.bot = bot

    runs = app_commands.Group(name="runs", description="Running commands")

    @runs.command(name="panel", description="Open your interactive running dashboard")
    async def panel(self, interaction: discord.Interaction):
        stats = await self.bot.db.get_stats(interaction.user.id)
        await interaction.response.send_message(
            view=RunPanelView(self.bot.db, interaction.user.id, stats), ephemeral=True
        )

    @runs.command(name="log", description="Log a completed run")
    @app_commands.describe(name="A short name for your run", distance="E.g. 5km", duration="MM:SS or HH:MM:SS")
    async def log(self, interaction: discord.Interaction, name: str, distance: str, duration: str):
        try:
            name, meters, seconds = validate_run(name, distance, duration)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await self.bot.db.add_run(interaction.user.id, name, meters, seconds)
        await interaction.response.send_message(view=RunReceiptView(name, meters, seconds))

    @runs.command(name="all", description="Browse your logged runs")
    async def all(self, interaction: discord.Interaction):
        total = await self.bot.db.count_runs(interaction.user.id)
        runs = await self.bot.db.get_runs(interaction.user.id, limit=PAGE_SIZE)
        await interaction.response.send_message(
            view=RunHistoryView(self.bot.db, interaction.user.id, runs, total), ephemeral=True
        )

    @runs.command(name="stats", description="See your overall running statistics")
    async def stats(self, interaction: discord.Interaction):
        stats = await self.bot.db.get_stats(interaction.user.id)
        await interaction.response.send_message(view=RunStatsView(stats), ephemeral=True)


async def setup(bot):
    await bot.add_cog(RunningCog(bot))
