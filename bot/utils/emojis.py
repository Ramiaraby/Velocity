"""Configurable Discord custom emojis with built-in Unicode fallbacks.

Server admins upload their assets through Discord; these env vars only
reference emojis the bot can already use. This module never creates emojis.
"""

import os
import re

import discord

FALLBACKS = {
    "running": "🏃",
    "cycling": "🚴",
    "swimming": "🏊",
    "home": "🏠",
    "rankings": "🏆",
    "profile": "👤",
    "review": "🛡️",
    "splits": "📊",
    "proof": "📸",
    "pace": "⚡",
}
CUSTOM = re.compile(r"^<a?:[A-Za-z0-9_]{2,32}:[0-9]{15,22}>$")


def emoji_for(key: str) -> str | discord.PartialEmoji:
    if key not in FALLBACKS:
        raise ValueError("Unrecognized emoji slot.")
    configured = os.getenv(f"VELOCITY_EMOJI_{key.upper()}", "").strip()
    if CUSTOM.fullmatch(configured):
        return discord.PartialEmoji.from_str(configured)
    return FALLBACKS[key]


def emoji_text(key: str) -> str:
    return str(emoji_for(key))
