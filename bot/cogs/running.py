from discord.ext import commands
from discord import app_commands
from bot.bot import Bot
import discord
import re

def to_meters(distance: str) -> int:
    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*(km|k|m)\s*",
        distance.lower()
    )

    if not match:
        raise ValueError("Invalid distance format")

    value = float(match.group(1))
    unit = match.group(2)

    meters = value * 1000 if unit in ("km", "k") else value

    if meters <= 0 or not meters.is_integer():
        raise ValueError("Distance must be a positive whole number of meters")

    return int(meters)

def to_seconds(duration: str) -> int:
    parts = duration.strip().split(":")

    if len(parts) not in (2, 3):
        raise ValueError("Use MM:SS or HH:MM:SS")

    if not all(part.isascii() and part.isdigit() for part in parts):
        raise ValueError("Invalid duration")

    numbers = list(map(int, parts))

    if any(n >= 60 for n in numbers[1:]):
        raise ValueError("Minutes and seconds must be below 60")

    return sum(
        value * 60**i
        for i, value in enumerate(reversed(numbers))
    )

def format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes}:{seconds:02d}"

def format_distance(meters: int) -> str:
    return f"{meters / 1000:g}km"

def calculate_pace(meters: int, seconds: int):
    return round(seconds * 1000 / meters)


class RunningCog(commands.Cog, name='Running'):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.connection = bot.db.connection

    runs = app_commands.Group(
        name='runs',
        description='Running Commands.'
    )


    @runs.command(name='log')
    async def log(self, interaction: discord.Interaction, name: str, distance: str, duration: str):
        """
        Log your runs.
        """
        try:
            distance_meters = to_meters(distance)
            duration_seconds = to_seconds(duration)
            pace_seconds = calculate_pace(distance_meters, duration_seconds)

            if distance_meters < 1000:
                raise ValueError('Run must be 1km or longer!')
            if pace_seconds < 2.1*60:
                raise ValueError('You can NOT run that fast gang :joy:')
            if pace_seconds > 20*60:
                raise ValueError('I do not think this one should go in the books :broken_heart:')
            if len(name) > 20:
                raise ValueError('Name can not exceed 20 charactors.')

            async with self.connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO runs (user_id, distance, duration, name)
                    VALUES (?, ?, ?, ?)
                    """, (interaction.user.id, distance_meters, duration_seconds, name)
                )
            await self.connection.commit()


            pace = format_duration(pace_seconds)
            distance = format_distance(distance_meters)
            duration = format_duration(duration_seconds)
            

            await interaction.response.send_message(f':athletic_shoe: RUN LOGGED: {distance} in {duration}.\npace: {pace}')
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)

    @runs.command(name='all')
    async def all(self, interaction: discord.Interaction):
        async with self.connection.execute("""
            SELECT * FROM runs
            WHERE user_id = ?    
        """,(interaction.user.id,)) as cursor:
            runs = [dict(row) for row in await cursor.fetchall()]
        if not runs:
            await interaction.response.send_message('No logged runs, use `/run log` to add your runs.', ephemeral=True)
        else:
            embed = discord.Embed(
                title='Your Runs!',
                description='\n\n'.join([f'**{run["name"]}**:\n-# {format_distance(run["distance"])} in {format_duration(run["duration"])}.' for run in runs]),
                color=interaction.user.color
            )
            embed.set_author(name=interaction.user.display_name,icon_url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(RunningCog(bot))