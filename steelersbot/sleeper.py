# WIP: I never finished fully implementing this because I got lazy and un-encouraged by how hacky sleepers event system works.
# They love to send out an event and then instead of issuing out an updated event, reissue the event with updated values.
# The whole reason I was writing this was to live stream data to a channel as it occurs but some big changes were made in these update events.
# Thus leading me to abandon my fork of how discord.py handles its websocket. Danny ur a great architect even if this websocket was baby shit.


import asyncio
from collections import namedtuple
import concurrent.futures
import json
import logging
import struct
import sys
import time
import threading
import zlib

import websockets

from . import utils
from .activity import _ActivityTag
from .enums import SpeakingState
from .errors import ConnectionClosed, InvalidArgument

log = logging.getLogger(__name__)

__all__ = (
    'DiscordWebSocket',
    'KeepAliveHandler',
    'VoiceKeepAliveHandler',
    'DiscordVoiceWebSocket',
    'ResumeWebSocket',
)

class ResumeWebSocket(Exception):
    """Signals to initialise via RESUME opcode instead of IDENTIFY."""
    def __init__(self):

GameEvent = namedtuple('GameEvent', 'game_id data result future')

class KeepAliveHandler(threading.Thread):
    def __init__(self, *args, **kwargs):
        ws = kwargs.pop('ws', None)
        interval = kwargs.pop('interval', None)
        threading.Thread.__init__(self, *args, **kwargs)
        self.ws = ws
        self.interval = interval
        self.daemon = True
        self.block_msg = 'Heartbeat blocked for more than {} seconds.'
        self.behind_msg = 'Can\'t keep up, websocket is {:.1f}s behind.'
        self._stop_ev = threading.Event()
        self._last_ack = time.perf_counter()
        self._last_send = time.perf_counter()
        self.latency = float('inf')
        self.heartbeat_timeout = ws._max_heartbeat_timeout

    def run(self):
        while not self._stop_ev.wait(self.interval):
            if self._last_ack + self.heartbeat_timeout < time.perf_counter():
                log.warning("Sleeper WS has stopped responding to the gateway. Closing and restarting.")
                coro = self.ws.close(4000)
                f = asyncio.run_coroutine_threadsafe(coro, loop=self.ws.loop)

                try:
                    f.result()
                except Exception:
                    pass
                finally:
                    self.stop()
                    return

            data = self.get_payload()
            coro = self.ws.send_as_json(data)
            f = asyncio.run_coroutine_threadsafe(coro, loop=self.ws.loop)
            try:
                # block until sending is complete
                total = 0
                while True:
                    try:
                        f.result(5)
                        break
                    except concurrent.futures.TimeoutError:
                        total += 5
                        print(self.block_msg.format(total))

            except Exception:
                self.stop()
            else:
                self._last_send = time.perf_counter()

    def get_payload(self):
        self.ws.message_count += 1
        return [
            None,
            self.ws.message_count,
            "phoenix",
            "heartbeat",
            {}
        ]

    def stop(self):
        self._stop_ev.set()

    def ack(self):
        ack_time = time.perf_counter()
        self._last_ack = ack_time
        self.latency = ack_time - self._last_send
        if self.latency > 10:
            print(self.behind_msg.format(self.latency))

class SleeperWebSocket(websockets.client.WebSocketClientProtocol):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bot = kwargs.pop('bot', None)
        self.max_size = None
        # an empty dispatcher to prevent crashes
        self._dispatch = lambda *args: None
        # the keep alive
        self._keep_alive = None

        # ws related stuff
        self.message_count = 0
        self.event_queue = {}

    async def received_message(self, msg):

        msg = json.loads(msg)

        msg_1  = msg.pop(0) # Only populated when client sends a message
        msg_2  = msg.pop(0) # Only populated when client is recieveing a response to a message
        source = msg.pop(0) # We only care about "phoenix" and "score:nfl" for now
        event  = msg.pop(0) # We only care about "score_updated" and "phx_reply" for now
        data   = msg.pop(0) # Only populated by server, not client (I think)

        print(f"recieved message... {msg}")

        if msg_1:
            print(f"Got a message where both msg fields were populated... {msg}")

        if event == 'phx_reply':
            # For now this is only heartbeat acks
            self._keep_alive.ack()

        elif event == "score_updated":
            game_id = data.get("game_id")
            self.event_queue


    @property
    def latency(self):
        """:class:`float`: Measures latency between a HEARTBEAT and a HEARTBEAT_ACK in seconds."""
        heartbeat = self._keep_alive
        return float('inf') if heartbeat is None else heartbeat.latency

    def _can_handle_close(self, code):
        return code not in (1000, 4004, 4010, 4011)

    async def poll_event(self):
        """Polls for a DISPATCH event and handles the general gateway loop.

        Raises
        ------
        ConnectionClosed
            The websocket connection was terminated for unhandled reasons.
        """
        try:
            msg = await self.recv()
            await self.received_message(msg)
        except websockets.exceptions.ConnectionClosed as exc:
            if self._can_handle_close(exc.code):
                log.info('Websocket closed with %s (%s), attempting a reconnect.', exc.code, exc.reason)
                raise ResumeWebSocket() from exc
            else:
                log.info('Websocket closed with %s (%s), cannot reconnect.', exc.code, exc.reason)
                raise websockets.exceptions.ConnectionClosed() from exc

    async def send(self, data):
        await super().send(data)

    async def send_as_json(self, data):
        try:
            await self.send(utils.to_json(data))
        except websockets.exceptions.ConnectionClosed as exc:
            if not self._can_handle_close(exc.code):
                raise ConnectionClosed() from exc

    async def request_league_events(self):
        self.message_count += 1
        payload = [self.message_count,
                   self.message_count, 
                   "league:462395713448308736",
                   "phx_join",
                   {}
        ]
        await self.send_as_json(payload)

    async def request_nfl_score_events(self):
        self.message_count += 1
        payload = [self.message_count,
                   self.message_count,
                   "score:nfl",
                   "phx_join",
                   {}
        ]
        await self.send_as_json(payload)

    async def close(self, code=1000, reason=''):
        if self._keep_alive:
            self._keep_alive.stop()

        await super().close(code, reason)

    async def close_connection(self, *args, **kwargs):
        if self._keep_alive:
            self._keep_alive.stop()

        await super().close_connection(*args, **kwargs)