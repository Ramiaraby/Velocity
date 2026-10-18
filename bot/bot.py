from discord.ext import commands
from classes.database import db
import discord

class Bot(commands.Bot):
    def __init__(self):
        self.db = db
        super().__init__(command_prefix='?', intents=discord.Intents.default())

    UNLOADED_COGS = ['running']

    async def setup_hook(self):
        await self.db.create_tables()
        print('Database Connected')
        for cog_file in self.UNLOADED_COGS:
            try:
                await self.load_extension(f'bot.cogs.{cog_file}')
                self.UNLOADED_COGS.remove(cog_file)
            except Exception as Error:
                print(Exception)
        await self.tree.sync()
        print('Unloaded Cogs: ' + ', '.join(self.UNLOADED_COGS) if self.UNLOADED_COGS else 'All cogs loaded succesfully')

    async def on_ready(self):
        print(f'Logged in as {self.user.name}')
