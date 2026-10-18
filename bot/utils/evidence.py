"""Private Discord proof storage for owner review."""

import discord

MAX_PROOF_BYTES = 10 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def validate_elevation(value: int | None) -> int | None:
    if value is not None and not 0 <= value <= 20000:
        raise ValueError("Elevation gain must be between 0 and 20,000 meters.")
    return value


def validate_proof(image: discord.Attachment) -> None:
    if image.content_type not in IMAGE_TYPES:
        raise ValueError("Proof must be a PNG, JPG, WEBP or GIF image.")
    if image.size > MAX_PROOF_BYTES:
        raise ValueError("Proof image must be 10 MB or smaller.")


async def save_private_proof(bot: discord.Client, run_id: int,
                             user_id: int, image: discord.Attachment) -> tuple[int, int]:
    validate_proof(image)
    channel_id = getattr(bot, "proof_channel_id", None)
    if not channel_id:
        raise ValueError("Proof uploads are disabled until the owner configures PROOF_CHANNEL_ID.")
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        raise ValueError("PROOF_CHANNEL_ID must point to a private text channel.")
    file = await image.to_file()
    msg = await channel.send(
        content=f"Velocity proof | run #{run_id} | runner ID {user_id}",
        file=file,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    return msg.channel.id, msg.id


async def find_private_proof(bot: discord.Client, run: dict) -> tuple[str | None, str | None]:
    """Fetch current signed attachment URL and persistent review-channel message link."""
    channel_id, message_id = run.get("proof_channel_id"), run.get("proof_message_id")
    if not channel_id or not message_id:
        return None, None
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return None, None
    try:
        message = await channel.fetch_message(message_id)
    except (discord.HTTPException, discord.Forbidden, discord.NotFound):
        return None, None
    return (
        message.attachments[0].url if message.attachments else None,
        message.jump_url,
    )
