"""Interactive split entry and screenshot OCR confirmation using Components V2."""

import discord
from discord import ui

from bot.utils.emojis import emoji_for, emoji_text
from bot.utils.split_ocr import SplitOCRError, extract_splits_from_attachment
from bot.utils.splits import (
    display_split, expected_segments, parse_manual_splits, validate_splits,
)
from bot.utils.running import format_duration

MAX_PREVIEW_LINES = 25


def split_summary(sport: str, meters: int, times: list[int]) -> str:
    lengths = expected_segments(sport, meters)
    lines = [
        f"**{i}.** {length} m  •  {display_split(sport, length, sec)}"
        for i, (length, sec) in enumerate(zip(lengths, times), start=1)
    ]
    if len(lines) > MAX_PREVIEW_LINES:
        omitted = len(lines) - MAX_PREVIEW_LINES
        return "\n".join(lines[:MAX_PREVIEW_LINES]) + f"\n… +{omitted} more splits"
    return "\n".join(lines)


async def editable_record(hub, interaction):
    record = await hub.bot.db.get_run(hub.activity_id)
    if not record or record["user_id"] != interaction.user.id or (
        record["verification_status"] != "pending"
    ):
        return None
    return record


class ManualSplitsButton(ui.Button):
    def __init__(self, hub):
        super().__init__(label="Enter times", emoji=emoji_for("pace"),
                         style=discord.ButtonStyle.success)
        self.hub = hub

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ManualSplitsModal(self.hub))


class OCRSplitsButton(ui.Button):
    def __init__(self, hub):
        super().__init__(label="Read screenshot", emoji=emoji_for("proof"),
                         style=discord.ButtonStyle.primary)
        self.hub = hub

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(OCRSplitsModal(self.hub))


class ManualSplitsModal(ui.Modal):
    def __init__(self, hub, initial: str = ""):
        self.hub = hub
        super().__init__(title="Enter split times")
        sport = hub.sport
        unit = "100 m" if sport == "swimming" else "1 km"
        self.times = ui.TextInput(
            style=discord.TextStyle.paragraph,
            placeholder="5:12\n5:08\n5:19" if sport != "swimming" else
                        "2:04\n2:01\n2:07",
            default=initial[:4000] if initial else None,
            max_length=4000, required=True,
        )
        self.add_item(ui.Label(
            text=f"Time for each {unit} interval",
            description="One interval duration per line, not cumulative elapsed time.",
            component=self.times,
        ))

    async def on_submit(self, interaction: discord.Interaction):
        record = await editable_record(self.hub, interaction)
        if not record:
            await interaction.response.send_message(
                "This activity cannot be edited now.", ephemeral=True
            )
            return
        try:
            seconds = parse_manual_splits(self.times.value)
            validate_splits(record["sport"], record["distance"],
                            record["duration"], seconds)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        saved = await self.hub.bot.db.save_activity_splits(
            record["id"], interaction.user.id, seconds
        )
        if not saved:
            await interaction.response.send_message(
                "The activity has already been reviewed.", ephemeral=True
            )
            return
        view = await self.hub.__class__.build(
            self.hub.bot, interaction.user.id, interaction.guild_id,
            screen="splits", sport=record["sport"], activity_id=record["id"],
        )
        await interaction.response.send_message(
            content="✅ Interval times saved.", view=view, ephemeral=True,
        )


class OCRSplitsModal(ui.Modal):
    def __init__(self, hub):
        self.hub = hub
        super().__init__(title="Extract interval times")
        self.image = ui.FileUpload(required=True, max_values=1, min_values=1)
        self.add_item(ui.Label(
            text="Screenshot of your split table",
            description="Crop to numbered splits. Processing is local; nothing is saved.",
            component=self.image,
        ))

    async def on_submit(self, interaction: discord.Interaction):
        record = await editable_record(self.hub, interaction)
        if not record:
            await interaction.response.send_message(
                "This activity cannot be edited now.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            split_times = await extract_splits_from_attachment(
                self.image.values[0], record["sport"], record["distance"]
            )
        except (SplitOCRError, IndexError) as exc:
            await interaction.followup.send(
                f"Couldn't recognize numbered splits: {str(exc) or 'No file selected.'}"
                "\nTry cropping your screenshot or enter the times manually.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            view=OCRSplitPreviewView(self.hub, record, split_times),
            ephemeral=True,
        )


class OCRSplitPreviewView(ui.LayoutView):
    """Nothing gets persisted until the athlete explicitly selects Confirm."""

    def __init__(self, hub, record: dict, split_times: list[int]):
        super().__init__(timeout=300)
        self.hub = hub
        self.record = record
        self.split_times = list(split_times)
        self.user_id = hub.user_id
        mismatch = None
        try:
            validate_splits(
                record["sport"], record["distance"], record["duration"], split_times
            )
        except ValueError as exc:
            mismatch = str(exc)
        container = ui.Container(
            ui.TextDisplay("## 🔎 OCR split preview"),
            ui.TextDisplay("**Unverified extraction.** Check every time before saving; "
                           "OCR can read digits incorrectly."),
            ui.Separator(),
            ui.TextDisplay(split_summary(
                record["sport"], record["distance"], split_times
            )),
            ui.TextDisplay(
                f"Split total: **{format_duration(sum(split_times))}**  •  "
                f"Activity: **{format_duration(record['duration'])}**"
                + (f"\n⚠️ {mismatch}" if mismatch else "")
            ),
            ui.ActionRow(ConfirmOCRButton(self, disabled=bool(mismatch)),
                         EditOCRButton(self), DiscardOCRButton(self)),
            accent_colour=discord.Colour.blurple(),
        )
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This screenshot preview belongs to someone else.", ephemeral=True
            )
            return False
        return True


class ConfirmOCRButton(ui.Button):
    def __init__(self, preview, *, disabled=False):
        super().__init__(label="Confirm splits", emoji="✅",
                         style=discord.ButtonStyle.success, disabled=disabled)
        self.preview = preview

    async def callback(self, interaction: discord.Interaction):
        record = await editable_record(self.preview.hub, interaction)
        if not record:
            await interaction.response.send_message(
                "Activity was already reviewed.", ephemeral=True
            )
            return
        try:
            updated = await self.preview.hub.bot.db.save_activity_splits(
                record["id"], interaction.user.id, self.preview.split_times,
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        if not updated:
            await interaction.response.send_message(
                "Activity no longer accepts changes.", ephemeral=True
            )
            return
        view = await self.preview.hub.__class__.build(
            self.preview.hub.bot, interaction.user.id, interaction.guild_id,
            screen="splits", sport=record["sport"], activity_id=record["id"],
        )
        await interaction.response.edit_message(view=view)


class EditOCRButton(ui.Button):
    def __init__(self, preview):
        super().__init__(label="Edit times", emoji="✏️",
                         style=discord.ButtonStyle.secondary)
        self.preview = preview

    async def callback(self, interaction: discord.Interaction):
        formatted = "\n".join(
            format_duration(seconds) for seconds in self.preview.split_times
        )
        await interaction.response.send_modal(
            ManualSplitsModal(self.preview.hub, formatted)
        )


class DiscardOCRButton(ui.Button):
    def __init__(self, preview):
        super().__init__(label="Discard", emoji="🗑️",
                         style=discord.ButtonStyle.danger)
        self.preview = preview

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="OCR suggestion discarded. No split times were saved.", view=None
        )
