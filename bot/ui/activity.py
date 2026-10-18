"""Multisport Components V2 interfaces: dashboard, receipts, history and rankings."""

from math import ceil

import discord
from discord import ui

from bot.utils.activity import (
    SPORT_ICONS, SPORT_LABELS, activity_display, activity_metric,
)
from bot.utils.running import format_distance, format_duration
from bot.ui.running import OwnedLayout, clean_text, LogRunModal
from classes.database import Database

ACCENT = discord.Colour.from_rgb(38, 180, 184)
PAGE_SIZE = 5

STATUS = {
    "pending": "🟡 Pending owner review",
    "verified": "✅ Owner verified",
    "rejected": "❌ Rejected",
}


def entry_text(activity: dict) -> str:
    sport = activity.get("sport", "running")
    result = (
        f"**#{activity['id']} {clean_text(activity['name'])}** "
        f"— {STATUS.get(activity['verification_status'], 'Pending')}\n"
        + activity_display(sport, activity["distance"], activity["duration"])
    )
    if activity.get("elevation_gain_m") is not None:
        result += f" · ⛰️ {activity['elevation_gain_m']} m"
    if activity.get("location_name"):
        result += f"\n📍 {clean_text(activity['location_name'])}"
    if activity.get("swim_type"):
        kind = "Pool" if activity["swim_type"] == "pool" else "Open water"
        result += f"\n🌊 {kind}"
        if activity.get("pool_length_m"):
            result += f" ({activity['pool_length_m']} m pool)"
    if activity.get("proof_message_id"):
        result += "\n🖼️ Proof submitted privately"
    if activity.get("notes"):
        result += f"\n📝 {clean_text(activity['notes'])[:200]}"
    return result


class ActivityReceiptView(ui.LayoutView):
    def __init__(self, activity: dict):
        super().__init__(timeout=None)
        sport = activity["sport"]
        self.add_item(ui.Container(
            ui.TextDisplay(f"## {SPORT_ICONS[sport]} {SPORT_LABELS[sport]} logged"),
            ui.TextDisplay(entry_text(activity)),
            ui.Separator(),
            ui.TextDisplay(
                f"Add optional evidence with `/velocity proof activity_id:{activity['id']}`. "
                "Only the bot owner can verify activities."
            ),
            accent_colour=ACCENT,
        ))


class ActivityHistoryButtons(ui.ActionRow):
    def __init__(self, view: "ActivityHistoryView"):
        super().__init__()
        self.history = view
        self.previous.disabled = view.page == 0
        self.next.disabled = view.page >= view.last_page

    @ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: ui.Button):
        await self.history.change_page(interaction, -1)

    @ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: ui.Button):
        await self.history.change_page(interaction, 1)


class ActivityHistoryView(OwnedLayout):
    def __init__(self, db: Database, user_id: int, sport: str,
                 activities: list[dict], total: int, page: int = 0):
        super().__init__(user_id)
        self.db = db
        self.sport = sport
        self.activities = activities
        self.total = total
        self.page = page
        self.last_page = max(0, ceil(total / PAGE_SIZE) - 1)
        self.render()

    def render(self):
        self.clear_items()
        body = "\n\n".join(map(entry_text, self.activities)) or "No activities logged yet."
        self.add_item(ui.Container(
            ui.TextDisplay(f"## {SPORT_ICONS[self.sport]} {SPORT_LABELS[self.sport]} history"),
            ui.TextDisplay(f"{self.total} activities • Page {self.page + 1}/{self.last_page + 1}"),
            ui.Separator(),
            ui.TextDisplay(body),
            ActivityHistoryButtons(self),
            accent_colour=ACCENT,
        ))

    async def change_page(self, interaction: discord.Interaction, direction: int):
        page = max(0, min(self.last_page, self.page + direction))
        if page != self.page:
            self.activities = await self.db.get_activities(
                self.user_id, sport=self.sport, limit=PAGE_SIZE, offset=page * PAGE_SIZE
            )
            self.page = page
            self.render()
        await interaction.response.edit_message(view=self)


class ActivityStatsView(ui.LayoutView):
    def __init__(self, sport: str, stats: dict):
        super().__init__(timeout=None)
        count, meters, secs = stats["run_count"], stats["total_distance"], stats["total_duration"]
        body = (
            f"**Activities:** {count}\n"
            f"✅ **Owner verified:** {stats['verified_runs']}\n"
            f"📍 **Total distance:** {format_distance(meters)}\n"
            f"⏱️ **Total time:** {format_duration(secs)}\n"
            f"⚡ **Combined average:** {activity_metric(sport, meters, secs)}\n"
            f"🏅 **Longest activity:** {format_distance(stats['longest_distance'])}"
        ) if count else "No activities yet. Your dashboard is ready whenever you are."
        if sport != "swimming" and stats.get("total_elevation"):
            body += f"\n⛰️ **Total climbing:** {stats['total_elevation']} m"
        self.add_item(ui.Container(
            ui.TextDisplay(f"## {SPORT_ICONS[sport]} {SPORT_LABELS[sport]} stats"),
            ui.TextDisplay(body),
            accent_colour=ACCENT,
        ))


class RecordsView(ui.LayoutView):
    def __init__(self, sport: str, records: dict):
        super().__init__(timeout=None)
        longest = records["longest"]
        fastest = records["fastest"]
        distance = records["distance"]
        header = {
            "running": "Fastest 5 km",
            "cycling": "Fastest 20 km",
            "swimming": "Fastest 100 m",
        }[sport]
        body = (
            "**Longest logged activity**\n"
            + (
                f"{format_distance(longest['distance'])} — "
                f"{format_duration(longest['duration'])} (#{longest['id']})"
                if longest else "No activities yet"
            )
            + f"\n\n**{header}**\n"
            + (
                f"{format_duration(fastest['duration'])} (#{fastest['id']})"
                if fastest else f"No exactly {format_distance(distance)} activities yet"
            )
        )
        self.add_item(ui.Container(
            ui.TextDisplay(f"## 🏅 Your {SPORT_LABELS[sport].lower()} records"),
            ui.TextDisplay("Based on your logged activities; not independently verified."),
            ui.Separator(),
            ui.TextDisplay(body),
            accent_colour=ACCENT,
        ))


class LeaderboardView(ui.LayoutView):
    def __init__(self, sport: str, period: str, rows: list[dict]):
        super().__init__(timeout=None)
        titles = {"week": "Last 7 days", "month": "Last 30 days", "all": "All time"}
        lines = [
            f"**{i}.** <@{item['user_id']}> — **{format_distance(item['meters'])}** "
            f"({item['count']} activities)"
            for i, item in enumerate(rows, 1)
        ]
        self.add_item(ui.Container(
            ui.TextDisplay(f"## 🏆 {SPORT_LABELS[sport]} leaderboard"),
            ui.TextDisplay(f"{titles[period]} • Only owner-verified activities in this server"),
            ui.Separator(),
            ui.TextDisplay("\n".join(lines) if lines else
                           "No verified activities in this server and time period yet."),
            accent_colour=ACCENT,
        ))


class WeeklyView(ui.LayoutView):
    def __init__(self, summary: list[dict]):
        super().__init__(timeout=None)
        body = "\n\n".join(
            f"**{SPORT_ICONS[row['sport']]} {SPORT_LABELS[row['sport']]}**\n"
            f"{row['count']} activities · {format_distance(row['meters'])} · "
            f"{format_duration(row['seconds'])} · {row['verified']} verified"
            for row in summary
        ) or "No activities over the last seven days."
        self.add_item(ui.Container(
            ui.TextDisplay("## 📅 Your last 7 days"),
            ui.TextDisplay("A recap of what you logged, at your own pace."),
            ui.Separator(),
            ui.TextDisplay(body),
            accent_colour=ACCENT,
        ))


class ActivityLogModal(ui.Modal):
    def __init__(self, bot, sport: str):
        super().__init__(title=f"Log {SPORT_LABELS[sport].lower()}")
        self.bot = bot
        self.sport = sport
        self.name_input = ui.TextInput(
            label="Activity name", placeholder="Morning session", max_length=20
        )
        self.distance_input = ui.TextInput(
            label="Distance", placeholder="20km or 1500m", max_length=20
        )
        self.duration_input = ui.TextInput(
            label="Duration", placeholder="45:00 or 1:25:00", max_length=20
        )
        self.extra_input = ui.TextInput(
            label=("Elevation gained in meters (optional)" if sport == "cycling"
                   else "Pool or open_water"),
            placeholder=("250" if sport == "cycling" else "pool"),
            required=(sport == "swimming"), max_length=20,
        )
        self.final_input = ui.TextInput(
            label=("City/area (optional)" if sport == "cycling" else "Pool length in meters (optional)"),
            placeholder=("Beirut, Lebanon" if sport == "cycling" else "25"),
            required=False, max_length=100 if sport == "cycling" else 5,
        )
        for field in (self.name_input, self.distance_input, self.duration_input,
                      self.extra_input, self.final_input):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        from bot.services.activities import log_activity
        from bot.utils.activity import validate_activity
        try:
            elev = int(self.extra_input.value) if self.sport == "cycling" and self.extra_input.value else None
            swim_type = self.extra_input.value.strip().casefold() if self.sport == "swimming" else None
            pool = int(self.final_input.value) if self.sport == "swimming" and self.final_input.value else None
            name, meters, seconds, elev, swim_type, pool, note = validate_activity(
                self.sport, self.name_input.value, self.distance_input.value,
                self.duration_input.value, elevation_m=elev,
                swim_type=swim_type, pool_length_m=pool,
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        location = self.final_input.value if self.sport == "cycling" else None
        await log_activity(
            self.bot, interaction, sport=self.sport, name=name, meters=meters,
            seconds=seconds, elevation_m=elev, location=location,
            swim_type=swim_type, pool_length_m=pool, notes=note,
        )


class DashboardButtons(ui.ActionRow):
    def __init__(self, bot, user_id: int):
        super().__init__()
        self.bot, self.user_id = bot, user_id

    @ui.button(label="Run", emoji="🏃", style=discord.ButtonStyle.success)
    async def run(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(
            LogRunModal(self.bot.db, self.bot.location_resolver)
        )

    @ui.button(label="Cycle", emoji="🚴", style=discord.ButtonStyle.primary)
    async def cycle(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ActivityLogModal(self.bot, "cycling"))

    @ui.button(label="Swim", emoji="🏊", style=discord.ButtonStyle.primary)
    async def swim(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ActivityLogModal(self.bot, "swimming"))

    @ui.button(label="Weekly recap", emoji="📅", style=discord.ButtonStyle.secondary)
    async def weekly(self, interaction: discord.Interaction, button: ui.Button):
        summary = await self.bot.db.get_weekly_summary(self.user_id)
        await interaction.response.send_message(view=WeeklyView(summary), ephemeral=True)


class DashboardView(OwnedLayout):
    def __init__(self, bot, user_id: int, stats: dict[str, dict]):
        super().__init__(user_id)
        lines = [
            f"{SPORT_ICONS[sport]} **{SPORT_LABELS[sport]}:** "
            f"{stats[sport]['run_count']} activities · "
            f"{format_distance(stats[sport]['total_distance'])} · "
            f"{stats[sport]['verified_runs']} verified"
            for sport in SPORT_LABELS
        ]
        self.add_item(ui.Container(
            ui.TextDisplay("## ⚡ VELOCITY | Your multisport hub"),
            ui.TextDisplay("Track running, cycling and swimming. Review progress in one place."),
            ui.Separator(),
            ui.TextDisplay("\n".join(lines)),
            ui.Separator(),
            ui.TextDisplay("Choose a sport to log a session, or open your weekly recap."),
            DashboardButtons(bot, user_id),
            accent_colour=ACCENT,
        ))
