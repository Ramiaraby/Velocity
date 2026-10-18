"""Shared activity-logging pipeline used by slash commands and modal submissions."""

import discord

from bot.ui.activity import ActivityReceiptView
from bot.utils.evidence import save_private_proof, validate_proof
from bot.utils.location import LocationLookupError


async def log_activity(
    bot, interaction: discord.Interaction, *, sport: str, name: str,
    meters: int, seconds: int, elevation_m: int | None = None,
    location: str | None = None, swim_type: str | None = None,
    pool_length_m: int | None = None, notes: str | None = None,
    proof: discord.Attachment | None = None,
):
    if proof:
        try:
            validate_proof(proof)
            if not bot.proof_channel_id:
                raise ValueError(
                    "Proof uploads require a private PROOF_CHANNEL_ID. "
                    "Log without proof or ask the bot owner."
                )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        place = await bot.location_resolver.resolve(location)
    except LocationLookupError as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
        return

    activity_id = await bot.db.add_activity(
        interaction.user.id, sport, name, meters, seconds,
        guild_id=interaction.guild_id, elevation_gain_m=elevation_m,
        location_name=place, location_status="found" if place else "not_provided",
        swim_type=swim_type, pool_length_m=pool_length_m, notes=notes,
    )
    proof_saved = False
    if proof:
        try:
            channel_id, message_id = await save_private_proof(
                bot, activity_id, interaction.user.id, proof
            )
            proof_saved = await bot.db.attach_proof(
                activity_id, interaction.user.id, channel_id, message_id
            )
        except (ValueError, discord.DiscordException, OSError):
            await interaction.followup.send(
                f"Session saved as #{activity_id}, but proof upload failed. "
                f"Retry with \`/velocity proof activity_id:{activity_id}\`.",
                ephemeral=True,
            )
    activity = await bot.db.get_run(activity_id)
    if not proof_saved and activity is not None:
        activity["proof_message_id"] = None
    await interaction.followup.send(
        view=ActivityReceiptView(activity), ephemeral=True
    )


async def upload_proof(
    bot, interaction: discord.Interaction, *, activity_id: int, image: discord.Attachment
):
    activity = await bot.db.get_run(activity_id)
    if not activity or activity["user_id"] != interaction.user.id:
        await interaction.response.send_message("Activity not found in your history.", ephemeral=True)
        return
    if activity["verification_status"] != "pending":
        await interaction.response.send_message(
            "Evidence can only be added before the owner's decision.", ephemeral=True
        )
        return
    if activity.get("proof_message_id"):
        await interaction.response.send_message(
            "This activity already has an image. Contact the owner if it needs correction.",
            ephemeral=True,
        )
        return
    try:
        validate_proof(image)
        if not bot.proof_channel_id:
            raise ValueError("Ask the owner to configure the private PROOF_CHANNEL_ID.")
    except ValueError as exc:
        await interaction.response.send_message(str(exc), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        channel_id, message_id = await save_private_proof(
            bot, activity_id, interaction.user.id, image
        )
        attached = await bot.db.attach_proof(
            activity_id, interaction.user.id, channel_id, message_id
        )
    except (ValueError, discord.DiscordException, OSError):
        await interaction.followup.send(
            "Proof upload failed. Please retry later.", ephemeral=True
        )
        return
    await interaction.followup.send(
        "✅ Image stored in the private review channel."
        if attached else "The activity changed during upload; contact the owner.",
        ephemeral=True,
    )
