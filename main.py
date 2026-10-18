import logging
import os

from dotenv import load_dotenv

load_dotenv()

from bot.bot import Bot

logging.basicConfig(level=logging.INFO)

token = os.getenv("BOT_TOKEN")
if not token:
    raise RuntimeError("Set BOT_TOKEN in your environment or .env file")

Bot().run(token)
