"""Components V2 views, owner review controls, and run logging modal."""

from math import ceil

import discord
from discord import ui

from bot.utils.evidence import validate_elevation
from bot.utils.location import LocationLookupError
from bot.utils.running import calculate_pace, format_distance, format_duration, validate_run
from classes.database import Database

ACCENT = discord.Colour.from_rgb(46, 204, 113)
PAGE_SIZE = 5
STATUS = {"pending": "🟡 Pending owner review", "verified": "✅ Verified by owner",
          "rejected": "❌ Rejected by owner"}


def clean_text(value: str) -> str:
    return discord.utils.escape_markdown(discord.utils.escape_mentions(value))


def run_lines(run: dict) -> str:
    lines = [
        f"🏃 **Distance:** {format_distance(run['distance'])}",
        f"⏱️ **Time:** {format_duration(run['duration'])}",
        f"⚡ **Average pace:** {format_duration(calculate_pace(run['distance'], run['duration']))} /km",
    ]
    if run.get("elevation_gain_m") is not None:
        lines.append(f"⛰️ **Elevation gain:** {run['elevation_gain_m']} m")
    if run.get("location_name"):
        lines.append(f"📍 **Place found in OpenStreetMap:** {clean_text(run['location_name'])}")
    lines.append(f"🖼️ **Proof image:** {'Submitted privately' if run.get('proof_message_id') else 'Not submitted'}")
    lines.append(f"**Status:** {STATUS.get(run.get('verification_status', 'pending'), 'Pending')}")
    return "\n".join(lines)


class OwnedLayout(ui.LayoutView):
    def __init__(self, user_id: int, *, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This panel belongs to someone else. Use `/runs panel` for your own.",
                ephemeral=True,
            )
            return False
        return True


class RunReceiptView(ui.LayoutView):
    def __init__(self, name: str, meters: int, seconds: int, *,
                 run_id: int | None = None, elevation_gain_m: int | None = None,
                 location_name: str | None = None, proof_submitted: bool = False):
        super().__init__(timeout=None)
        run = {
            "name": name, "distance": meters, "duration": seconds,
            "elevation_gain_m": elevation_gain_m, "location_name": location_name,
            "proof_message_id": 1 if proof_submitted else None,
            "verification_status": "pending",
        }
        self.add_item(ui.Container(
            ui.TextDisplay("## ⚡ Run logged"),
            ui.TextDisplay(f"**{clean_text(name)}**" + (f"  •  ID #{run_id}" if run_id else "")),
            ui.Separator(),
            ui.TextDisplay(run_lines(run)),
            ui.TextDisplay("Add optional evidence with `/runs proof`. Only the owner can verify this run."),
            accent_colour=ACCENT,
        ))


class RunStatsView(ui.LayoutView):
    def __init__(self, stats: dict):
        super().__init__(timeout=None)
        count = stats["run_count"]
        if count:
            distance = stats["total_distance"]
            summary = (
                f"🏃 **Runs:** {count}\n"
                f"✅ **Owner verified:** {stats.get('verified_runs', 0)}\n"
                f"📍 **Total distance:** {format_distance(distance)}\n"
                f"⏱️ **Total running time:** {format_duration(stats['total_duration'])}\n"
                f"⚡ **Overall average pace:** "
                f"{format_duration(calculate_pace(distance, stats['total_duration']))} /km\n"
                f"🏅 **Longest run:** {format_distance(stats['longest_distance'])}"
            )
        else:
            summary = "No runs logged yet. Open `/runs panel` to add your first one!"
        self.add_item(ui.Container(
            ui.TextDisplay("## 📊 Your running stats"),
            ui.Separator(),
            ui.TextDisplay(summary),
            accent_colour=ACCENT,
        ))


class RunHistoryButtons(ui.ActionRow):
    def __init__(self, history: "RunHistoryView"):
        super().__init__()
        self.history = history
        self.previous.disabled = history.page == 0
        self.next.disabled = history.page >= history.last_page

    @ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: ui.Button):
        await self.history.change_page(interaction, -1)

    @ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: ui.Button):
        await self.history.change_page(interaction, 1)


class RunHistoryView(OwnedLayout):
    def __init__(self, db: Database, user_id: int, runs: list[dict], total: int, page: int = 0):
        super().__init__(user_id)
        self.db = db
        self.runs = runs
        self.total = total
        self.page = page
        self.last_page = max(0, ceil(total / PAGE_SIZE) - 1)
        self.render()

    def render(self) -> None:
        self.clear_items()
        if not self.runs:
            entries = "No runs yet! Use `/runs panel` to log your first run."
        else:
            entries = "\n\n".join(
                f"**#{run.get('id', '?')} {clean_text(run['name'])}** "
                f"— {STATUS.get(run.get('verification_status', 'pending'), 'Pending')}\n"
                f"{format_distance(run['distance'])} • {format_duration(run['duration'])} • "
                f"{format_duration(calculate_pace(run['distance'], run['duration']))} /km"
                + (f" • ⛰️ {run['elevation_gain_m']} m"
                   if run.get("elevation_gain_m") is not None else "")
                + (f"\n📍 {clean_text(run['location_name'])}" if run.get("location_name") else "")
                + (" • 🖼️ Evidence attached" if run.get("proof_message_id") else "")
                for run in self.runs
            )
        self.add_item(ui.Container(
            ui.TextDisplay("## 🏃 Your running history"),
            ui.TextDisplay(f"{self.total} runs • Page {self.page + 1} of {self.last_page + 1}"),
            ui.Separator(),
            ui.TextDisplay(entries),
            RunHistoryButtons(self),
            accent_colour=ACCENT,
        ))

    async def change_page(self, interaction: discord.Interaction, direction: int) -> None:
        new_page = max(0, min(self.last_page, self.page + direction))
        if new_page != self.page:
            self.runs = await self.db.get_runs(
                self.user_id, limit=PAGE_SIZE, offset=new_page * PAGE_SIZE
            )
            self.page = new_page
            self.render()
        await interaction.response.edit_message(view=self)


class LogRunModal(ui.Modal, title="Log a run"):
    run_name = ui.TextInput(label="Run name", placeholder="Morning 5K", max_length=20)
    distance = ui.TextInput(label="Distance", placeholder="5km or 5000m", max_length=20)
    duration = ui.TextInput(label="Duration", placeholder="24:30 or 1:05:30", max_length=20)
    elevation = ui.TextInput(label="Elevation gain in meters (optional)",
                             placeholder="120", required=False, max_length=5)
    location = ui.TextInput(label="City or neighborhood (optional)",
                            placeholder="Aramoun, Lebanon", required=False, max_length=100)

    def __init__(self, db: Database, resolver=None):
        super().__init__()
        self.db = db
        self.resolver = resolver

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            name, meters, seconds = validate_run(
                self.run_name.value, self.distance.value, self.duration.value
            )
            raw_elevation = self.elevation.value.strip()
            if raw_elevation and not raw_elevation.isascii():
                raise ValueError("Elevation must contain only digits.")
            elevation = validate_elevation(int(raw_elevation) if raw_elevation else None)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        # Location lookup may take >3s; acknowledge the modal first.
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            if self.location.value.strip() and self.resolver is None:
                raise LocationLookupError("Location lookup is not configured.")
            location = await self.resolver.resolve(self.location.value) if self.resolver else None
        except LocationLookupError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        run_id = await self.db.add_run(
            interaction.user.id, name, meters, seconds, elevation_gain_m=elevation,
            location_name=location, location_status="found" if location else "not_provided",
        )
        await interaction.followup.send(
            view=RunReceiptView(name, meters, seconds, run_id=run_id,
                                elevation_gain_m=elevation, location_name=location),
            ephemeral=True,
        )


class RunPanelButtons(ui.ActionRow):
    def __init__(self, db: Database, user_id: int, resolver=None):
        super().__init__()
        self.db = db
        self.user_id = user_id
        self.resolver = resolver

    @ui.button(label="➕ Log run", style=discord.ButtonStyle.success)
    async def log_run(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(LogRunModal(self.db, self.resolver))

    @ui.button(label="📖 History", style=discord.ButtonStyle.primary)
    async def history(self, interaction: discord.Interaction, button: ui.Button):
        total = await self.db.count_runs(self.user_id)
        runs = await self.db.get_runs(self.user_id, limit=PAGE_SIZE)
        await interaction.response.send_message(
            view=RunHistoryView(self.db, self.user_id, runs, total), ephemeral=True
        )

    @ui.button(label="📊 My stats", style=discord.ButtonStyle.secondary)
    async def stats(self, interaction: discord.Interaction, button: ui.Button):
        stats = await self.db.get_stats(self.user_id)
        await interaction.response.send_message(view=RunStatsView(stats), ephemeral=True)


class RunPanelView(OwnedLayout):
    def __init__(self, db: Database, user_id: int, stats: dict, resolver=None):
        super().__init__(user_id)
        count = stats["run_count"]
        headline = (
            f"**{count} runs** logged • **{format_distance(stats['total_distance'])}** total"
            if count else "Your training starts here. Log your first run!"
        )
        self.add_item(ui.Container(
            ui.TextDisplay("## ⚡ Velocity | Running dashboard"),
            ui.TextDisplay("Log runs, review your progress, and add optional evidence."),
            ui.Separator(),
            ui.TextDisplay(headline),
            RunPanelButtons(db, user_id, resolver),
            accent_colour=ACCENT,
        ))


class ReviewButtons(ui.ActionRow):
    def __init__(self, db: Database, run_id: int, owner_id: int, proof_url: str | None,
                 proof_link: str | None):
        super().__init__()
        self.db, self.run_id, self.owner_id = db, run_id, owner_id
        self.proof_url, self.proof_link = proof_url, proof_link

    async def _review(self, interaction: discord.Interaction, status: str):
        updated = await self.db.review_run(self.run_id, self.owner_id, status)
        if not updated:
            await interaction.response.send_message(
                "This run was already reviewed. Open `/runs inspect` again.", ephemeral=True
            )
            return
        run = await self.db.get_run(self.run_id)
        await interaction.response.edit_message(
            view=ReviewRunView(self.db, self.owner_id, run, self.proof_url, self.proof_link)
        )

    @ui.button(label="✅ Verify", style=discord.ButtonStyle.success)
    async def verify(self, interaction: discord.Interaction, button: ui.Button):
        await self._review(interaction, "verified")

    @ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: ui.Button):
        await self._review(interaction, "rejected")


class ReviewRunView(OwnedLayout):
    def __init__(self, db: Database, owner_id: int, run: dict,
                 proof_url: str | None = None, proof_link: str | None = None):
        super().__init__(owner_id)
        details = (
            f"Runner: <@{run['user_id']}> (ID {run['user_id']})\n"
            + run_lines(run)
        )
        if proof_link:
            details += f"\n[Open evidence in private review channel]({proof_link})"
        if run.get("moderation_note"):
            details += f"\n**Review note:** {clean_text(run['moderation_note'])[:200]}"
        components = [
            ui.TextDisplay(f"## 🏁 Owner review | Run #{run['id']}"),
            ui.TextDisplay(f"**{clean_text(run['name'])}**"),
            ui.Separator(),
            ui.TextDisplay(details),
        ]
        if run["verification_status"] == "pending":
            components.append(ReviewButtons(db, run["id"], owner_id, proof_url, proof_link))
        self.add_item(ui.Container(*components, accent_colour=ACCENT))
        if proof_url:
            self.add_item(ui.MediaGallery(discord.MediaGalleryItem(proof_url, description="Private run proof")))


class PendingRunsView(ui.LayoutView):
    def __init__(self, runs: list[dict]):
        super().__init__(timeout=None)
        body = "\n\n".join(
            f"**#{run['id']} {clean_text(run['name'])}** — runner <@{run['user_id']}>\n"
            f"{format_distance(run['distance'])} • {format_duration(run['duration'])}"
            f" • {'🖼️ Evidence' if run.get('proof_message_id') else 'No image'}"
            for run in runs
        ) if runs else "Nothing is awaiting review."
        self.add_item(ui.Container(
            ui.TextDisplay("## 📝 Pending owner reviews"),
            ui.TextDisplay("Use `/runs inspect run_id` to review evidence and decide."),
            ui.Separator(),
            ui.TextDisplay(body),
            accent_colour=ACCENT,
        ))
