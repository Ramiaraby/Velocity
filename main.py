from bot.bot import Bot
from dotenv import load_dotenv
import os

load_dotenv()
bot = Bot()
bot.run(os.getenv('BOT_TOKEN'))