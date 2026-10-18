"""The single Components V2 interface for every Velocity sport.

All interactions are ephemeral and user-bound. One slash command opens this
dashboard; everything else is navigation, selects, buttons and modals.
"""

from math import ceil

import discord
from discord import ui

from bot.utils.activity import SPORT_ICONS, SPORT_LABELS, activity_metric, validate_activity
from bot.utils.running import format_distance, format_duration
from bot.utils.evidence import save_private_proof, validate_proof, find_private_proof
from bot.utils.location import LocationLookupError

SPORTS = ("running", "cycling", "swimming")
ACCENTS = {
    "running": discord.Colour.from_rgb(68, 197, 141),
    "cycling": discord.Colour.from_rgb(72, 158, 239),
    "swimming": discord.Colour.from_rgb(119, 111, 240),
}
HOME_COLOUR = discord.Colour.from_rgb(37, 190, 185)
PAGE_SIZE = 5
STATES = {"pending": "🟡 Awaiting review", "verified": "✅ Verified",
          "rejected": "🔴 Rejected"}


def safe(text: str) -> str:
    return discord.utils.escape_markdown(discord.utils.escape_mentions(str(text)))


def label_for(record: dict) -> str:
    return f"{SPORT_ICONS[record['sport']]} {safe(record['name'])}"


def performance(record: dict) -> str:
    sport = record["sport"]
    parts = [
        f"**{format_distance(record['distance'])}**",
        f"{format_duration(record['duration'])}",
        activity_metric(sport, record["distance"], record["duration"]),
    ]
    return "  •  ".join(parts)


class MoveButton(ui.Button):
    def __init__(self, parent, name: str, *, screen: str, sport: str | None = None,
                 emoji: str | None = None, style=discord.ButtonStyle.secondary,
                 page: int = 0, period: str | None = None, activity_id: int | None = None):
        super().__init__(label=name, emoji=emoji, style=style)
        self.hub = parent
        self.destination = screen
        self.sport = sport
        self.page = page
        self.period = period
        self.activity_id = activity_id

    async def callback(self, interaction: discord.Interaction):
        await self.hub.navigate(
            interaction, self.destination, sport=self.sport, page=self.page,
            period=self.period, activity_id=self.activity_id,
        )


class SportSelect(ui.Select):
    def __init__(self, hub):
        self.hub = hub
        super().__init__(
            placeholder="Choose a sport",
            options=[
                discord.SelectOption(label=SPORT_LABELS[s], value=s, emoji=SPORT_ICONS[s],
                                     default=hub.sport == s)
                for s in SPORTS
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        destination = "rankings" if self.hub.screen == "rankings" else "sport"
        await self.hub.navigate(interaction, destination, sport=self.values[0])


class PeriodSelect(ui.Select):
    def __init__(self, hub):
        self.hub = hub
        super().__init__(
            placeholder="Leaderboard period",
            options=[
                discord.SelectOption(label=title, value=period,
                                     default=hub.period == period)
                for period, title in (
                    ("week", "Last 7 days"), ("month", "Last 30 days"), ("all", "All time")
                )
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        await self.hub.navigate(interaction, "rankings", period=self.values[0])


class ActivitySelect(ui.Select):
    def __init__(self, hub, records):
        self.hub = hub
        super().__init__(
            placeholder="Open an activity for details / proof",
            options=[
                discord.SelectOption(
                    label=f"#{r['id']} {r['name'][:50]}",
                    description=f"{format_distance(r['distance'])} • {STATES[r['verification_status']][:35]}",
                    value=str(r["id"]), emoji=SPORT_ICONS[r["sport"]],
                )
                for r in records
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        await self.hub.navigate(
            interaction, "detail", activity_id=int(self.values[0])
        )


class LogButton(ui.Button):
    def __init__(self, hub):
        super().__init__(label="Log activity", emoji="➕", style=discord.ButtonStyle.success)
        self.hub = hub

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LogModal(self.hub))


class ProofButton(ui.Button):
    def __init__(self, hub):
        super().__init__(label="Add proof", emoji="📸", style=discord.ButtonStyle.primary)
        self.hub = hub

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ProofModal(self.hub))


class DetailsButton(ui.Button):
    def __init__(self, hub):
        super().__init__(label="Place / notes", emoji="📝", style=discord.ButtonStyle.secondary)
        self.hub = hub

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(DetailsModal(self.hub))


class ExportButton(ui.Button):
    def __init__(self, hub):
        super().__init__(label="Export my data", emoji="📥", style=discord.ButtonStyle.secondary)
        self.hub = hub

    async def callback(self, interaction: discord.Interaction):
        import csv
        import io

        records = await self.hub.bot.db.export_user_activities(interaction.user.id)
        if not records:
            await interaction.response.send_message(
                "No activity history to export yet.", ephemeral=True
            )
            return
        buffer = io.StringIO(newline="")
        columns = list(records[0])
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        for record in records[:10000]:
            # Do not let untrusted activity names become spreadsheet formulas.
            writer.writerow({
                key: "'" + value if isinstance(value, str)
                and value.lstrip().startswith(("=", "+", "-", "@")) else value
                for key, value in record.items()
            })
        file = discord.File(
            io.BytesIO(buffer.getvalue().encode("utf-8-sig")),
            filename="velocity-my-activities.csv",
        )
        suffix = " (first 10,000)" if len(records) > 10000 else ""
        await interaction.response.send_message(
            content="Your private activity export" + suffix, file=file, ephemeral=True
        )


class ReviewButton(ui.Button):
    def __init__(self, hub, status: str):
        super().__init__(
            label="Verify" if status == "verified" else "Reject",
            emoji="✅" if status == "verified" else "❌",
            style=discord.ButtonStyle.success if status == "verified" else discord.ButtonStyle.danger,
        )
        self.hub = hub
        self.status = status

    async def callback(self, interaction: discord.Interaction):
        if not self.hub.owner:
            await interaction.response.send_message("Only the owner can review activities.",
                                                    ephemeral=True)
            return
        applied = await self.hub.bot.db.review_run(
            self.hub.activity_id, self.hub.bot.owner_id, self.status
        )
        if not applied:
            await interaction.response.send_message(
                "This activity was already reviewed. Reload the review screen.",
                ephemeral=True,
            )
            return
        await self.hub.navigate(interaction, "review_detail")


class LogModal(ui.Modal):
    def __init__(self, hub):
        self.hub = hub
        sport = hub.sport
        super().__init__(title=f"{SPORT_ICONS[sport]} Log {SPORT_LABELS[sport]}")
        self.name = ui.TextInput(placeholder="Morning session", max_length=20)
        self.distance = ui.TextInput(
            placeholder="5km, 20km or 1500m", max_length=20
        )
        self.duration = ui.TextInput(placeholder="MM:SS or HH:MM:SS", max_length=20)
        self.extra = (
            ui.Select(
                options=[
                    discord.SelectOption(label="Pool", value="pool", emoji="🏊"),
                    discord.SelectOption(label="Open water", value="open_water", emoji="🌊"),
                ], required=True
            ) if sport == "swimming" else
            ui.TextInput(placeholder="Meters climbed (optional)", required=False, max_length=5)
        )
        self.last = ui.TextInput(
            placeholder="25 or 50 (optional)", required=False, max_length=4
        ) if sport == "swimming" else ui.TextInput(
            placeholder="City, region, country (optional)", required=False, max_length=100
        )
        for title, widget, desc in [
            ("Session name", self.name, "A short title for this activity"),
            ("Distance", self.distance, "Examples: 5km, 20km or 1500m"),
            ("Moving time", self.duration, "Minutes:seconds or hours:minutes:seconds"),
            ("Water type" if sport == "swimming" else "Elevation gain", self.extra,
             "Pool or open water" if sport == "swimming" else "Optional climbing in meters"),
            ("Pool length" if sport == "swimming" else "Location", self.last,
             "Meters; for pool swims only" if sport == "swimming" else "Optional city / neighborhood"),
        ]:
            self.add_item(ui.Label(text=title, component=widget, description=desc))

    async def on_submit(self, interaction: discord.Interaction):
        sport = self.hub.sport
        try:
            elevation = None
            water = None
            pool = None
            location = None
            if sport == "swimming":
                water = self.extra.values[0]
                pool = int(self.last.value) if self.last.value.strip() else None
            else:
                elevation = int(self.extra.value) if self.extra.value.strip() else None
                location = self.last.value.strip() or None
            name, meters, seconds, elevation, water, pool, _ = validate_activity(
                sport, self.name.value, self.distance.value, self.duration.value,
                elevation_m=elevation, swim_type=water, pool_length_m=pool,
            )
        except (ValueError, IndexError) as exc:
            await interaction.response.send_message(str(exc) or "Invalid activity fields.",
                                                    ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            place = await self.hub.bot.location_resolver.resolve(location)
        except LocationLookupError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        activity_id = await self.hub.bot.db.add_activity(
            interaction.user.id, sport, name, meters, seconds,
            guild_id=interaction.guild_id,
            elevation_gain_m=elevation, location_name=place,
            location_status="found" if place else "not_provided",
            swim_type=water, pool_length_m=pool,
        )
        new_view = await HubView.build(
            self.hub.bot, interaction.user.id, interaction.guild_id,
            screen="detail", sport=sport, activity_id=activity_id,
        )
        await interaction.followup.send(
            view=new_view, ephemeral=True,
        )


class ProofModal(ui.Modal):
    def __init__(self, hub):
        self.hub = hub
        super().__init__(title="📸 Add private run / ride / swim proof")
        self.upload = ui.FileUpload(required=True, min_values=1, max_values=1)
        self.add_item(ui.Label(
            text="Proof screenshot or photo",
            description="JPG/PNG/WEBP/GIF up to 10MB; only the bot owner can review",
            component=self.upload,
        ))

    async def on_submit(self, interaction: discord.Interaction):
        item = await self.hub.bot.db.get_run(self.hub.activity_id)
        if not item or item["user_id"] != interaction.user.id or item["verification_status"] != "pending":
            await interaction.response.send_message("Activity is no longer editable.", ephemeral=True)
            return
        if item.get("proof_message_id"):
            await interaction.response.send_message("This activity already has proof.", ephemeral=True)
            return
        try:
            attachment = self.upload.values[0]
            validate_proof(attachment)
            if not self.hub.bot.proof_channel_id:
                raise ValueError("Owner must configure PROOF_CHANNEL_ID before proof uploads.")
        except (ValueError, IndexError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            channel_id, message_id = await save_private_proof(
                self.hub.bot, item["id"], interaction.user.id, attachment
            )
            saved = await self.hub.bot.db.attach_proof(
                item["id"], interaction.user.id, channel_id, message_id
            )
        except (ValueError, discord.DiscordException, OSError):
            await interaction.followup.send(
                "Could not store proof in the private review channel.", ephemeral=True
            )
            return
        if not saved:
            await interaction.followup.send(
                "The activity changed while the image was uploading. Contact the owner.",
                ephemeral=True,
            )
            return
        view = await HubView.build(
            self.hub.bot, interaction.user.id, interaction.guild_id,
            screen="detail", sport=item["sport"], activity_id=item["id"],
        )
        await interaction.followup.send(view=view, ephemeral=True)


class DetailsModal(ui.Modal):
    def __init__(self, hub):
        self.hub = hub
        super().__init__(title="📝 Activity details")
        self.location = ui.TextInput(
            placeholder="City or neighborhood (optional)", max_length=100, required=False
        )
        self.notes = ui.TextInput(
            style=discord.TextStyle.paragraph, placeholder="Optional personal notes",
            max_length=200, required=False,
        )
        self.add_item(ui.Label(text="Place name", component=self.location,
                               description="Matches a real place; does not prove GPS movement"))
        self.add_item(ui.Label(text="Session notes", component=self.notes))

    async def on_submit(self, interaction: discord.Interaction):
        record = await self.hub.bot.db.get_run(self.hub.activity_id)
        if not record or record["user_id"] != interaction.user.id or record["verification_status"] != "pending":
            await interaction.response.send_message("Activity is no longer editable.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            place = await self.hub.bot.location_resolver.resolve(
                self.location.value.strip() or None
            )
        except LocationLookupError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        saved = await self.hub.bot.db.update_activity_details(
            record["id"], interaction.user.id,
            location_name=place, location_status="found" if place else "not_provided",
            notes=self.notes.value.strip() or None,
        )
        if not saved:
            await interaction.followup.send("Activity was already reviewed.", ephemeral=True)
            return
        view = await HubView.build(
            self.hub.bot, interaction.user.id, interaction.guild_id,
            screen="detail", sport=record["sport"], activity_id=record["id"]
        )
        await interaction.followup.send(view=view, ephemeral=True)


class HubView(ui.LayoutView):
    def __init__(self, bot, user_id: int, guild_id: int | None, *,
                 screen: str, sport: str, period: str, page: int,
                 activity_id: int | None, payload):
        super().__init__(timeout=600)
        self.bot, self.user_id, self.guild_id = bot, user_id, guild_id
        self.screen, self.sport, self.period = screen, sport, period
        self.page, self.activity_id, self.payload = page, activity_id, payload
        self.owner = bool(bot.owner_id and user_id == bot.owner_id)
        self.render()

    @classmethod
    async def build(cls, bot, user_id, guild_id, *, screen="home",
                    sport="running", period="week", page=0, activity_id=None):
        if sport not in SPORTS:
            sport = "running"
        if period not in ("week", "month", "all"):
            period = "week"
        db = bot.db
        payload = None
        if screen in ("home", "profile"):
            payload = {
                s: await db.get_activity_stats(user_id, sport=s) for s in SPORTS
            }
        elif screen == "sport":
            payload = {
                "stats": await db.get_activity_stats(user_id, sport=sport),
                "records": await db.get_personal_records(user_id, sport),
            }
        elif screen == "history":
            total = await db.count_activities(user_id, sport=sport)
            page = min(max(page, 0), max(0, ceil(total / PAGE_SIZE) - 1))
            payload = {
                "total": total,
                "records": await db.get_activities(
                    user_id, sport=sport, limit=PAGE_SIZE, offset=page * PAGE_SIZE
                ),
            }
        elif screen in ("detail", "review_detail"):
            payload = await db.get_run(activity_id) if activity_id is not None else None
            if payload and screen == "detail" and payload["user_id"] != user_id:
                payload = None
            if screen == "review_detail" and user_id != bot.owner_id:
                payload = None
            if screen == "review_detail" and payload and user_id == bot.owner_id:
                try:
                    proof_url, proof_link = await find_private_proof(bot, payload)
                except (discord.DiscordException, ValueError):
                    proof_url, proof_link = None, None
                payload["_proof_url"] = proof_url
                payload["_proof_link"] = proof_link
        elif screen == "rankings":
            payload = await db.get_leaderboard(guild_id, sport, period) if guild_id else []
        elif screen == "reviews":
            if user_id == bot.owner_id:
                count = await db.count_pending_runs()
                page = min(max(page, 0), max(0, ceil(count / PAGE_SIZE) - 1))
                payload = {
                    "total": count,
                    "records": await db.get_pending_runs(
                        limit=PAGE_SIZE, offset=page * PAGE_SIZE
                    ),
                }
            else:
                payload = {"total": 0, "records": []}
        elif screen == "weekly":
            payload = await db.get_weekly_summary(user_id)
        return cls(bot, user_id, guild_id, screen=screen, sport=sport,
                   period=period, page=page, activity_id=activity_id, payload=payload)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This is a private dashboard. Open \`/velocity\` for your own.",
                ephemeral=True,
            )
            return False
        return True

    async def navigate(self, interaction, screen, *, sport=None, page=0,
                       period=None, activity_id=None):
        view = await HubView.build(
            self.bot, self.user_id, self.guild_id, screen=screen,
            sport=sport or self.sport, period=period or self.period,
            page=page, activity_id=activity_id
        )
        await interaction.response.edit_message(view=view)

    def nav(self):
        row = ui.ActionRow()
        for name, emoji, screen in (
            ("Home", "🏠", "home"),
            ("Sports", "🏃", "sport"),
            ("Rankings", "🏆", "rankings"),
            ("Profile", "👤", "profile"),
        ):
            row.add_item(MoveButton(self, name, screen=screen, emoji=emoji))
        if self.owner:
            row.add_item(MoveButton(self, "Review", screen="reviews", emoji="🛡️"))
        return row

    def render(self):
        self.clear_items()
        self.add_item(ui.Container(
            ui.TextDisplay("## ⚡ VELOCITY  ·  ACTIVITY HUB"),
            ui.TextDisplay("Running  🏃  •  Cycling  🚴  •  Swimming  🏊"),
            self.nav(),
            accent_colour=HOME_COLOUR,
        ))
        if self.screen == "home":
            stats = self.payload
            total = sum(stats[s]["run_count"] for s in SPORTS)
            self.add_item(ui.Container(
                ui.TextDisplay("### 👋 Your activity space"),
                ui.TextDisplay(f"**{total}** logged activities across all sports. "
                               "Choose a sport to explore, log a session or review progress."),
                ui.Separator(),
                *(
                    ui.Section(
                        ui.TextDisplay(
                            f"### {SPORT_ICONS[s]} {SPORT_LABELS[s]}\n"
                            f"**{format_distance(stats[s]['total_distance'])}** overall"
                            f"  •  {stats[s]['run_count']} sessions  •  "
                            f"{stats[s]['verified_runs']} verified"
                        ),
                        accessory=MoveButton(self, "Open", screen="sport", sport=s,
                                             emoji=SPORT_ICONS[s]),
                    ) for s in SPORTS
                ),
                accent_colour=HOME_COLOUR,
            ))
        elif self.screen == "sport":
            stats, records = self.payload["stats"], self.payload["records"]
            longest = records["longest"]
            best = records["fastest"]
            bench = {"running": "5 km", "cycling": "20 km", "swimming": "100 m"}[self.sport]
            body = (
                f"**{stats['run_count']}** sessions  •  "
                f"**{format_distance(stats['total_distance'])}** total\n"
                f"⏱️ {format_duration(stats['total_duration'])} moving time  •  "
                f"✅ {stats['verified_runs']} verified\n"
                f"⚡ {activity_metric(self.sport, stats['total_distance'], stats['total_duration'])}"
                f" combined average\n"
                f"🏅 Longest: {format_distance(longest['distance']) if longest else '—'}\n"
                f"🏁 Fastest exactly {bench}: "
                f"{format_duration(best['duration']) if best else '—'}"
            )
            if self.sport != "swimming" and stats.get("total_elevation"):
                body += f"\n⛰️ {stats['total_elevation']} m total climbing"
            actions = ui.ActionRow()
            actions.add_item(LogButton(self))
            actions.add_item(MoveButton(self, "History", screen="history",
                                       emoji="📚", sport=self.sport))
            self.add_item(ui.Container(
                ui.TextDisplay(f"## {SPORT_ICONS[self.sport]} {SPORT_LABELS[self.sport]}"),
                ui.TextDisplay(body),
                ui.Separator(),
                actions,
                accent_colour=ACCENTS[self.sport],
            ))
            self.add_item(ui.ActionRow(SportSelect(self)))
        elif self.screen == "history":
            data = self.payload
            pages = max(1, ceil(data["total"] / PAGE_SIZE))
            rows = data["records"]
            lines = [
                f"**#{r['id']}  {safe(r['name'])}**  ·  "
                f"{STATES.get(r['verification_status'], 'Pending')}\n"
                f"{performance(r)}"
                for r in rows
            ]
            content = [
                ui.TextDisplay(f"## 📚 {SPORT_LABELS[self.sport]} history"),
                ui.TextDisplay(f"Page {self.page + 1} / {pages}  •  {data['total']} activities"),
                ui.Separator(),
                ui.TextDisplay("\n\n".join(lines) if lines else "No activities logged yet."),
            ]
            if rows:
                content.append(ui.ActionRow(ActivitySelect(self, rows)))
            buttons = ui.ActionRow()
            previous = MoveButton(self, "Previous", screen="history", sport=self.sport,
                                  page=max(self.page - 1, 0), emoji="◀️")
            previous.disabled = self.page == 0
            nxt = MoveButton(self, "Next", screen="history", sport=self.sport,
                             page=min(self.page + 1, pages - 1), emoji="▶️")
            nxt.disabled = self.page >= pages - 1
            buttons.add_item(previous)
            buttons.add_item(nxt)
            buttons.add_item(MoveButton(self, "Sport", screen="sport", emoji="↩️"))
            content.append(buttons)
            self.add_item(ui.Container(*content, accent_colour=ACCENTS[self.sport]))
        elif self.screen in ("detail", "review_detail"):
            r = self.payload
            if not r:
                self.add_item(ui.Container(ui.TextDisplay("Activity not found or inaccessible.")))
                return
            sport = r["sport"]
            details = [
                f"**#{r['id']}  {safe(r['name'])}**",
                performance(r),
                STATES[r["verification_status"]],
            ]
            if r.get("elevation_gain_m") is not None:
                details.append(f"⛰️ {r['elevation_gain_m']} m ascent")
            if r.get("location_name"):
                details.append(f"📍 {safe(r['location_name'])}  ·  Place name matched")
            if r.get("swim_type"):
                details.append(f"🌊 {r['swim_type'].replace('_', ' ')}")
            if r.get("pool_length_m"):
                details.append(f"🏊 {r['pool_length_m']} m pool")
            if r.get("notes"):
                details.append(f"📝 {safe(r['notes'])[:200]}")
            details.append("🖼️ Proof: " + ("Submitted privately" if r.get("proof_message_id")
                                          else "Not submitted"))
            if self.screen == "review_detail":
                details.insert(1, f"Runner: <@{r['user_id']}>")
            content = [
                ui.TextDisplay(f"## {SPORT_ICONS[sport]} Activity details"),
                ui.TextDisplay("\n".join(details)),
            ]
            actions = ui.ActionRow()
            if self.screen == "detail":
                if r["verification_status"] == "pending":
                    if not r.get("proof_message_id"):
                        actions.add_item(ProofButton(self))
                    actions.add_item(DetailsButton(self))
                actions.add_item(MoveButton(self, "History", screen="history",
                                            sport=sport, emoji="↩️"))
            else:
                if r["verification_status"] == "pending":
                    actions.add_item(ReviewButton(self, "verified"))
                    actions.add_item(ReviewButton(self, "rejected"))
                actions.add_item(MoveButton(self, "Queue", screen="reviews", emoji="↩️"))
            content.append(ui.Separator())
            content.append(actions)
            self.add_item(ui.Container(*content, accent_colour=ACCENTS[sport]))
            if self.screen == "review_detail" and r.get("_proof_url"):
                self.add_item(ui.MediaGallery(discord.MediaGalleryItem(
                    r["_proof_url"], description="Private evidence for owner review"
                )))
        elif self.screen == "rankings":
            self.add_item(ui.Container(
                ui.TextDisplay(f"## 🏆 {SPORT_LABELS[self.sport]} rankings"),
                ui.TextDisplay(f"**{self.period.upper()}** · "
                               "Owner-verified distances from this server only"),
                ui.Separator(),
                ui.TextDisplay(
                    "\n".join(
                        f"**{i}.** <@{r['user_id']}> — "
                        f"**{format_distance(r['meters'])}**  ·  {r['count']} sessions"
                        for i, r in enumerate(self.payload, 1)
                    ) if self.payload else (
                        "No verified activities here for this period."
                        if self.guild_id else "Rankings are available inside servers only."
                    )
                ),
                ui.ActionRow(SportSelect(self)),
                ui.ActionRow(PeriodSelect(self)),
                accent_colour=ACCENTS[self.sport],
            ))
        elif self.screen == "weekly":
            parts = [
                f"{SPORT_ICONS[r['sport']]} **{SPORT_LABELS[r['sport']]}**"
                f"  ·  {r['count']} sessions\n"
                f"{format_distance(r['meters'])}  •  {format_duration(r['seconds'])}"
                for r in self.payload
            ]
            self.add_item(ui.Container(
                ui.TextDisplay("## 📅 Last seven days"),
                ui.TextDisplay("\n\n".join(parts) if parts else
                               "No sessions logged in the last seven days."),
                accent_colour=HOME_COLOUR,
            ))
        elif self.screen == "profile":
            data = self.payload
            total = sum(data[s]["run_count"] for s in SPORTS)
            verified = sum(data[s]["verified_runs"] for s in SPORTS)
            achieved = [f"{SPORT_ICONS[s]} {SPORT_LABELS[s]}: {data[s]['run_count']} sessions"
                        for s in SPORTS]
            if all(data[s]["run_count"] for s in SPORTS):
                achieved.append("✨ Multisport explorer — activities in all three sports")
            self.add_item(ui.Container(
                ui.TextDisplay("## 👤 Your Velocity profile"),
                ui.TextDisplay(f"**{total}** sessions  •  **{verified}** owner verified"),
                ui.Separator(),
                ui.TextDisplay("\n".join(achieved)),
                ui.TextDisplay("Enjoy moving your way. Rest and recovery matter too."),
                ui.ActionRow(MoveButton(self, "7-day recap", screen="weekly", emoji="📅"),
                             ExportButton(self)),
                accent_colour=HOME_COLOUR,
            ))
        elif self.screen == "reviews":
            rows = self.payload["records"]
            pages = max(1, ceil(self.payload["total"] / PAGE_SIZE))
            text = "\n\n".join(
                f"**#{r['id']}** {SPORT_ICONS[r['sport']]} {safe(r['name'])}\n"
                f"<@{r['user_id']}>  •  {performance(r)}"
                f"  •  {'📸 Photo' if r.get('proof_message_id') else 'No photo'}"
                for r in rows
            ) or "✅ Review queue is clear."
            content = [ui.TextDisplay("## 🛡️ Owner review queue"),
                       ui.TextDisplay(f"Page {self.page + 1}/{pages} • {self.payload['total']} pending • Owner only"),
                       ui.Separator(), ui.TextDisplay(text)]
            if rows:
                content.append(ui.ActionRow(ReviewSelect(self, rows)))
            buttons = ui.ActionRow()
            back = MoveButton(self, "Previous", screen="reviews",
                              page=max(0, self.page - 1), emoji="◀️")
            back.disabled = self.page == 0
            forward = MoveButton(self, "Next", screen="reviews",
                                 page=min(pages - 1, self.page + 1), emoji="▶️")
            forward.disabled = self.page >= pages - 1
            buttons.add_item(back)
            buttons.add_item(forward)
            content.append(buttons)
            self.add_item(ui.Container(*content, accent_colour=HOME_COLOUR))


class ReviewSelect(ui.Select):
    def __init__(self, hub, records):
        self.hub = hub
        super().__init__(
            placeholder="Inspect a pending activity",
            options=[
                discord.SelectOption(
                    label=f"#{r['id']} {r['name'][:60]}",
                    description=f"Runner {r['user_id']}",
                    emoji=SPORT_ICONS[r["sport"]], value=str(r["id"])
                ) for r in records
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.hub.owner:
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return
        await self.hub.navigate(
            interaction, "review_detail", activity_id=int(self.values[0])
        )
