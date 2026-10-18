"""Velocity's Discord Components V2 screens for running activity."""

from math import ceil

import discord
from discord import ui

from bot.utils.running import calculate_pace, format_distance, format_duration, validate_run
from classes.database import Database

ACCENT = discord.Colour.from_rgb(46, 204, 113)
PAGE_SIZE = 5


def clean_text(value: str) -> str:
    """Avoid treating user-provided run names as Markdown or mentions."""
    return discord.utils.escape_markdown(discord.utils.escape_mentions(value))


class OwnedLayout(ui.LayoutView):
    def __init__(self, user_id: int, *, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is someone else's running panel. Use `/runs panel` for your own.", ephemeral=True)
            return False
        return True


class RunReceiptView(ui.LayoutView):
    def __init__(self, name: str, meters: int, seconds: int):
        super().__init__(timeout=None)
        self.add_item(ui.Container(
            ui.TextDisplay("## ✅ Run logged"),
            ui.TextDisplay(f"**{clean_text(name)}**"),
            ui.Separator(),
            ui.TextDisplay(
                f"🏃 **Distance:** {format_distance(meters)}\n"
                f"⏱️ **Time:** {format_duration(seconds)}\n"
                f"⚡ **Average pace:** {format_duration(calculate_pace(meters, seconds))} /km"
            ),
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
                f"**{clean_text(run['name'])}**\n"
                f"{format_distance(run['distance'])} • {format_duration(run['duration'])} • "
                f"{format_duration(calculate_pace(run['distance'], run['duration']))} /km"
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

    def __init__(self, db: Database):
        super().__init__()
        self.db = db

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            name, meters, seconds = validate_run(
                self.run_name.value, self.distance.value, self.duration.value
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await self.db.add_run(interaction.user.id, name, meters, seconds)
        await interaction.response.send_message(
            view=RunReceiptView(name, meters, seconds), ephemeral=True
        )


class RunPanelButtons(ui.ActionRow):
    def __init__(self, db: Database, user_id: int):
        super().__init__()
        self.db = db
        self.user_id = user_id

    @ui.button(label="➕ Log run", style=discord.ButtonStyle.success)
    async def log_run(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(LogRunModal(self.db))

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
    def __init__(self, db: Database, user_id: int, stats: dict):
        super().__init__(user_id)
        run_count = stats["run_count"]
        headline = (
            f"**{run_count} runs** logged • **{format_distance(stats['total_distance'])}** total"
            if run_count else "Your training starts here. Log your first run!"
        )
        self.add_item(ui.Container(
            ui.TextDisplay("## ⚡ Velocity | Running dashboard"),
            ui.TextDisplay("Track your runs, review your progress, and keep moving."),
            ui.Separator(),
            ui.TextDisplay(headline),
            RunPanelButtons(db, user_id),
            accent_colour=ACCENT,
        ))
