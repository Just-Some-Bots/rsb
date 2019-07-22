import os
import asyncio

from rh1 import RH1
os.environ["PYTHONUNBUFFERED"] = "1"
RH1().run()