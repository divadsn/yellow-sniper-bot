import asyncio

from glovobot.bot import GlovoBot
from glovobot.client import GlovoAPIClient

client = GlovoAPIClient.load("device.json")
bot = GlovoBot(client)

try:
    asyncio.run(bot.run())
except KeyboardInterrupt:
    pass
