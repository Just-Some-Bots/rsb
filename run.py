import os
import asyncio

from steelersbot import SteelersBot
os.environ["PYTHONUNBUFFERED"] = "1"
SteelersBot().run()