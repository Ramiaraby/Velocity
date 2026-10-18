"""Run slash commands, optional evidence upload, and owner-only moderation."""

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.ui.running import (
    PAGE_SIZE, PendingRunsView, ReviewRunView,
    RunHistoryView, RunPanelView, RunReceiptView, RunStatsView,
)
from bot.utils.evidence import (
    find_private_proof, save_private_proof, validate_elevation, validate_proof,
)
from bot.utils.location import LocationLookupError
from bot.utils.running import validate_run


class RunningCog(commands.Cog, name="Running"):
    def __init__(self, bot):
        self.bot = bot

    runs = app_commands.Group(name="runs", description="Running commands")

    def is_owner(self, interaction: discord.Interaction) -> bool:
        return bool(self.bot.owner_id and interaction.user.id == self.bot.owner_id)

    async def owner_guard(self, interaction: discord.Interaction) -> bool:
        if not self.is_owner(interaction):
            await interaction.response.send_message(
                "Only the Velocity owner (OWNER_ID) can review runs.", ephemeral=True
            )
            return False
        return True

    @runs.command(name="panel", description="Open your running dashboard")
    async def panel(self, interaction: discord.Interaction):
        stats = await self.bot.db.get_stats(interaction.user.id)
        await interaction.response.send_message(
            view=RunPanelView(self.bot.db, interaction.user.id, stats,
                              self.bot.location_resolver),
            ephemeral=True,
        )

    @runs.command(name="log", description="Log a completed run with optional evidence")
    @app_commands.describe(
        name="Short run name", distance="E.g. 5km",
        duration="MM:SS or HH:MM:SS", elevation_m="Optional elevation gain in meters",
        location="Optional city or neighborhood and country (not street address)",
        proof="Optional run screenshot/photo (sent privately for owner review)",
    )
    async def log(
        self, interaction: discord.Interaction, name: str, distance: str,
        duration: str, elevation_m: int | None = None, location: str | None = None,
        proof: discord.Attachment | None = None,
    ):
        try:
            name, meters, seconds = validate_run(name, distance, duration)
            elevation_m = validate_elevation(elevation_m)
            if proof is not None:
                validate_proof(proof)
                if not self.bot.proof_channel_id:
                    raise ValueError(
                        "Proof uploads require PROOF_CHANNEL_ID. Log without proof or ask the owner."
                    )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            place = await self.bot.location_resolver.resolve(location)
        except LocationLookupError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        run_id = await self.bot.db.add_run(
            interaction.user.id, name, meters, seconds,
            elevation_gain_m=elevation_m, location_name=place,
            location_status="found" if place else "not_provided",
        )
        proof_saved = False
        warning = None
        if proof:
            try:
                channel_id, message_id = await save_private_proof(
                    self.bot, run_id, interaction.user.id, proof
                )
                proof_saved = await self.bot.db.attach_proof(
                    run_id, interaction.user.id, channel_id, message_id
                )
            except (ValueError, discord.DiscordException, OSError):
                warning = "Proof upload failed. Run was saved; retry with \`/runs proof\`."
        await interaction.followup.send(
            view=RunReceiptView(
                name, meters, seconds, run_id=run_id, elevation_gain_m=elevation_m,
                location_name=place, proof_submitted=proof_saved,
            ),
            ephemeral=True,
        )
        if warning:
            await interaction.followup.send(warning, ephemeral=True)

    @runs.command(name="proof", description="Attach a private image to your pending run")
    @app_commands.describe(run_id="Run ID shown in your history",
                           image="Run screenshot or photo")
    async def proof(self, interaction: discord.Interaction, run_id: int,
                    image: discord.Attachment):
        run = await self.bot.db.get_run(run_id)
        if not run or run["user_id"] != interaction.user.id:
            await interaction.response.send_message("Run not found in your history.", ephemeral=True)
            return
        if run["verification_status"] != "pending":
            await interaction.response.send_message(
                "Proof can only be attached before owner review.", ephemeral=True
            )
            return
        if run.get("proof_message_id"):
            await interaction.response.send_message(
                "This run already has an image. Ask the owner if you need a correction.",
                ephemeral=True,
            )
            return
        try:
            validate_proof(image)
            if not self.bot.proof_channel_id:
                raise ValueError("Ask the owner to configure PROOF_CHANNEL_ID.")
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            channel_id, message_id = await save_private_proof(
                self.bot, run_id, interaction.user.id, image
            )
            attached = await self.bot.db.attach_proof(
                run_id, interaction.user.id, channel_id, message_id
            )
        except (ValueError, discord.DiscordException, OSError):
            await interaction.followup.send(
                "Could not upload proof to the private review channel.", ephemeral=True
            )
            return
        await interaction.followup.send(
            "✅ Proof attached privately. Awaiting owner verification."
            if attached else "Run changed during upload. Please contact the owner.",
            ephemeral=True,
        )

    @runs.command(name="all", description="Browse your logged runs")
    async def all(self, interaction: discord.Interaction):
        total = await self.bot.db.count_runs(interaction.user.id)
        runs = await self.bot.db.get_runs(interaction.user.id, limit=PAGE_SIZE)
        await interaction.response.send_message(
            view=RunHistoryView(self.bot.db, interaction.user.id, runs, total),
            ephemeral=True,
        )

    @runs.command(name="stats", description="See your running statistics")
    async def stats(self, interaction: discord.Interaction):
        stats = await self.bot.db.get_stats(interaction.user.id)
        await interaction.response.send_message(view=RunStatsView(stats), ephemeral=True)

    @runs.command(name="pending", description="Owner only: see runs awaiting review")
    async def pending(self, interaction: discord.Interaction):
        if not await self.owner_guard(interaction):
            return
        runs = await self.bot.db.get_pending_runs(limit=10)
        await interaction.response.send_message(view=PendingRunsView(runs), ephemeral=True)

    @runs.command(name="inspect", description="Owner only: inspect run and proof")
    @app_commands.describe(run_id="Run ID to inspect")
    async def inspect(self, interaction: discord.Interaction, run_id: int):
        if not await self.owner_guard(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        run = await self.bot.db.get_run(run_id)
        if not run:
            await interaction.followup.send("No run with that ID.", ephemeral=True)
            return
        try:
            image_url, image_link = await find_private_proof(self.bot, run)
        except (discord.DiscordException, ValueError):
            image_url, image_link = None, None
        await interaction.followup.send(
            view=ReviewRunView(self.bot.db, self.bot.owner_id, run, image_url, image_link),
            ephemeral=True,
        )

    @runs.command(name="review", description="Owner only: verify or reject a run")
    @app_commands.describe(run_id="Run ID", decision="Verify or reject",
                           note="Optional explanation")
    async def review(self, interaction: discord.Interaction, run_id: int,
                     decision: Literal["verified", "rejected"], note: str | None = None):
        if not await self.owner_guard(interaction):
            return
        if note and len(note) > 200:
            await interaction.response.send_message(
                "Review note cannot exceed 200 characters.", ephemeral=True
            )
            return
        updated = await self.bot.db.review_run(
            run_id, self.bot.owner_id, decision, note
        )
        await interaction.response.send_message(
            f"✅ Run #{run_id} marked **{decision}**."
            if updated else "Run not found or already reviewed.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(RunningCog(bot))
