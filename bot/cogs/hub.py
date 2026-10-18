"""Velocity's only slash command: an interactive dashboard."""

import discord
from discord import app_commands
from discord.ext import commands

from bot.ui.hub import HubView


class VelocityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="velocity", description="Open your running, cycling and swimming dashboard")
    async def velocity(self, interaction: discord.Interaction):
        # Each dashboard belongs to the user who opened it. All UI responses
        # are ephemeral, including the server-specific leaderboard.
        view = await HubView.build(
            self.bot, interaction.user.id, interaction.guild_id
        )
        await interaction.response.send_message(view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(VelocityCog(bot))
