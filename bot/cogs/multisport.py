"""Cycling, swimming, and Velocity multisport Discord slash commands."""

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.services.activities import log_activity, upload_proof
from bot.ui.activity import (
    PAGE_SIZE, ActivityHistoryView, ActivityStatsView, DashboardView,
    LeaderboardView, RecordsView, WeeklyView,
)
from bot.utils.activity import validate_activity


class MultisportCog(commands.Cog, name="Multisport"):
    def __init__(self, bot):
        self.bot = bot

    cycling = app_commands.Group(name="cycling", description="Cycling commands")
    swimming = app_commands.Group(name="swimming", description="Swimming commands")
    velocity = app_commands.Group(name="velocity", description="Your multisport training hub")

    async def submit(
        self, interaction: discord.Interaction, *, sport: str, name: str,
        distance: str, duration: str, elevation_m: int | None = None,
        location: str | None = None, swim_type: str | None = None,
        pool_length_m: int | None = None, notes: str | None = None,
        proof: discord.Attachment | None = None,
    ):
        try:
            normalized = validate_activity(
                sport, name, distance, duration, elevation_m=elevation_m,
                swim_type=swim_type, pool_length_m=pool_length_m, notes=notes,
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        name, meters, seconds, elevation_m, swim_type, pool_length_m, notes = normalized
        await log_activity(
            self.bot, interaction, sport=sport, name=name, meters=meters,
            seconds=seconds, elevation_m=elevation_m, location=location,
            swim_type=swim_type, pool_length_m=pool_length_m, notes=notes, proof=proof,
        )

    async def history(self, interaction: discord.Interaction, sport: str):
        total = await self.bot.db.count_activities(interaction.user.id, sport=sport)
        activities = await self.bot.db.get_activities(
            interaction.user.id, sport=sport, limit=PAGE_SIZE,
        )
        await interaction.response.send_message(
            view=ActivityHistoryView(
                self.bot.db, interaction.user.id, sport, activities, total
            ), ephemeral=True,
        )

    async def stats(self, interaction: discord.Interaction, sport: str):
        stats = await self.bot.db.get_activity_stats(interaction.user.id, sport=sport)
        await interaction.response.send_message(
            view=ActivityStatsView(sport, stats), ephemeral=True,
        )

    @cycling.command(name="log", description="Log a ride, including optional climbing and proof")
    @app_commands.describe(
        name="Name this ride", distance="E.g. 20km", duration="MM:SS or HH:MM:SS",
        elevation_m="Optional elevation gain in meters",
        location="Optional town or area and country (not a street address)",
        notes="Optional session notes", proof="Optional screenshot/photo of the ride",
    )
    async def cycling_log(
        self, interaction: discord.Interaction, name: str, distance: str,
        duration: str, elevation_m: int | None = None,
        location: str | None = None, notes: str | None = None,
        proof: discord.Attachment | None = None,
    ):
        await self.submit(
            interaction, sport="cycling", name=name, distance=distance,
            duration=duration, elevation_m=elevation_m, location=location,
            notes=notes, proof=proof,
        )

    @cycling.command(name="history", description="Browse your rides")
    async def cycling_history(self, interaction: discord.Interaction):
        await self.history(interaction, "cycling")

    @cycling.command(name="stats", description="Cycling distance, time and average speed")
    async def cycling_stats(self, interaction: discord.Interaction):
        await self.stats(interaction, "cycling")

    @swimming.command(name="log", description="Log a pool or open-water swim")
    @app_commands.describe(
        name="Name this swim", distance="E.g. 1500m",
        duration="MM:SS or HH:MM:SS", environment="Pool or open water",
        pool_length_m="Optional length of pool in meters",
        location="Optional city and country for open-water swimming",
        notes="Optional session notes", proof="Optional screenshot/photo of the swim",
    )
    async def swimming_log(
        self, interaction: discord.Interaction, name: str, distance: str,
        duration: str, environment: Literal["pool", "open_water"] = "pool",
        pool_length_m: int | None = None, location: str | None = None,
        notes: str | None = None, proof: discord.Attachment | None = None,
    ):
        await self.submit(
            interaction, sport="swimming", name=name, distance=distance,
            duration=duration, swim_type=environment, pool_length_m=pool_length_m,
            location=location, notes=notes, proof=proof,
        )

    @swimming.command(name="history", description="Browse your swims")
    async def swimming_history(self, interaction: discord.Interaction):
        await self.history(interaction, "swimming")

    @swimming.command(name="stats", description="Swimming distance, time and pace per 100 m")
    async def swimming_stats(self, interaction: discord.Interaction):
        await self.stats(interaction, "swimming")

    @velocity.command(name="dashboard", description="Open your multisport activity dashboard")
    async def dashboard(self, interaction: discord.Interaction):
        stats = {}
        for sport in ("running", "cycling", "swimming"):
            stats[sport] = await self.bot.db.get_activity_stats(
                interaction.user.id, sport=sport
            )
        await interaction.response.send_message(
            view=DashboardView(self.bot, interaction.user.id, stats),
            ephemeral=True,
        )

    @velocity.command(name="weekly", description="See your last seven days across all sports")
    async def weekly(self, interaction: discord.Interaction):
        summary = await self.bot.db.get_weekly_summary(interaction.user.id)
        await interaction.response.send_message(
            view=WeeklyView(summary), ephemeral=True,
        )

    @velocity.command(name="leaderboard", description="Server leaderboard of owner-verified activities")
    @app_commands.describe(
        sport="Sport to compare", period="Last 7 days, last 30 days, or all time",
    )
    async def leaderboard(
        self, interaction: discord.Interaction,
        sport: Literal["running", "cycling", "swimming"],
        period: Literal["week", "month", "all"] = "week",
    ):
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Leaderboards only work in a Discord server.", ephemeral=True,
            )
            return
        records = await self.bot.db.get_leaderboard(
            interaction.guild_id, sport, period, limit=10
        )
        await interaction.response.send_message(
            view=LeaderboardView(sport, period, records),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @velocity.command(name="records", description="See your distance and time personal bests")
    @app_commands.describe(sport="Sport to view")
    async def records(
        self, interaction: discord.Interaction,
        sport: Literal["running", "cycling", "swimming"],
    ):
        records = await self.bot.db.get_personal_records(interaction.user.id, sport)
        await interaction.response.send_message(
            view=RecordsView(sport, records), ephemeral=True,
        )

    @velocity.command(name="proof", description="Attach a private proof image to a pending activity")
    @app_commands.describe(
        activity_id="Activity ID from history", image="PNG/JPG/WEBP/GIF, up to 10 MB",
    )
    async def proof(
        self, interaction: discord.Interaction, activity_id: int,
        image: discord.Attachment,
    ):
        await upload_proof(
            self.bot, interaction, activity_id=activity_id, image=image,
        )

    @velocity.command(name="help", description="Get a quick guide to Velocity commands")
    async def help(self, interaction: discord.Interaction):
        import discord
        from discord import ui
        view = ui.LayoutView(timeout=None)
        view.add_item(ui.Container(
            ui.TextDisplay("## ⚡ Velocity — Quick start"),
            ui.TextDisplay(
                "**Running**: `/runs panel`, `/runs log`, `/runs stats`, `/runs all`\n"
                "**Cycling**: `/cycling log`, `/cycling history`, `/cycling stats`\n"
                "**Swimming**: `/swimming log`, `/swimming history`, `/swimming stats`\n"
                "**All sports**: `/velocity dashboard`, `/velocity weekly`, "
                "`/velocity records`, `/velocity leaderboard`, `/velocity proof`, "\n                "`/velocity profile`, `/velocity export`\n"
                "**Owner**: `/runs pending`, `/runs inspect`, `/runs review`"
            ),
            ui.Separator(),
            ui.TextDisplay(
                "Only owner-verified activities count toward server leaderboards. "
                "Location lookups check that a place exists, not that an activity happened there."
            ),
            accent_colour=discord.Colour.blurple(),
        ))
        await interaction.response.send_message(view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(MultisportCog(bot))
