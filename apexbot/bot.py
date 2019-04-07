import re
import os
import sys
import json
import shlex
import random
import inspect
import asyncio
import discord
import aiohttp
import logging
import argparse
# import ffmpeg
import textwrap
import traceback
import concurrent
import subprocess
import collections

from functools import wraps
from itertools import islice
from operator import itemgetter
from io import BytesIO, StringIO
from TwitterAPI import TwitterAPI
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from timeit import default_timer as timer
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .constants import *
from .exceptions import CommandError
from discord.http import HTTPClient, Route
from .creds import BOT_TOKEN, TWITCH_CREDS, USER_TOKEN, TWITTER_CON_KEY, TWITTER_CON_SECRET, TWITTER_TOKEN_KEY, TWITTER_TOKEN_SECRET
from .utils import clean_string, write_json, load_json, clean_bad_pings, datetime_to_utc_ts, timestamp_to_seconds, strfdelta, _get_variable, snowflake_time, MemberConverter, UserConverter

# logger = logging.getLogger('discord')
# logger.setLevel(logging.INFO)
# handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
# handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
# logger.addHandler(handler)

ROOT = os.path.abspath(os.path.dirname(__file__))
ASSETS = os.path.join(ROOT, 'assets')
ADJECTIVES = os.path.join(ASSETS, 'adjectives')
MONSTERS = os.path.join(ASSETS, 'monsters')

with open(ADJECTIVES) as f:
    adjectives = f.read().splitlines()
    
with open(MONSTERS) as f:
    monsters = f.read().splitlines()
    
def get_monster():
    adjective = random.choice(adjectives)
    monster = random.choice(monsters)
    return f"{adjective}{monster}"

def cleanup_code(content):
    """Automatically removes code blocks from the code."""
    # remove ```py\n```
    matches = list(re.finditer("(```)", content))
    if len(matches) > 1:
        return '\n'.join(content[matches[0].pos:matches[-1].endpos].split('\n')[1:-1])

    # remove `foo`
    return content.strip('` \n')

def cleanup_blocks(content):
    """Automatically removes code blocks from the code."""
    # remove ```py\n```
    matches = list(re.finditer("(```)", content))
    if len(matches) > 1:
        return content[(matches[0].end()):(matches[-1].start())]

    # remove `foo`
    return content.strip('` \n')

def doc_string(docobj, prefix):
    docs = '\n'.join(l.strip() for l in docobj.split('\n'))
    return '```\n%s\n```' % docs.format(command_prefix=prefix)

class Response(object):
    def __init__(self, content, reply=False, delete_after=0):
        self.content = content
        self.reply = reply
        self.delete_after = delete_after

class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeError(message)

class ApexBot(discord.Client):
    def __init__(self):
        super().__init__(max_messages=50000)
        # Auth Related 
        self.prefix = '!'
        self.prefix_aliases = [self.prefix, '!!']
        self.token = BOT_TOKEN
        self.user_token = USER_TOKEN
        
        # Local JSON Storage
        self.messages_log = {}
        self.tags = load_json('tags.json')
        self.tagblacklist = load_json('tagbl.json')
        self.twitch_watch_list = load_json('twitchwatchlist.json')
        self.twitter_watch_list = load_json('twitterwatchlist.json')
        self.channel_bans = {int(key): {int(k): v for k, v in value.items()} if value else value for key, value in load_json('channel_banned.json').items()}
        self.cban_role_aliases = {key: int(value) for key, value in load_json('cbanrolealiases.json').items()}
        
        # Instance Storage (nothing saved between bot
        self.vc_tracker = {}
        self.vc_categories = {}
        self.vc_queued_2s = []
        self.vc_moved_2s = []
        self.vc_num_locks = {}
        self.twitch_is_live = {}
        self.twitter_id_cache = {}
        self.watched_messages = {}
        
        # Variables used as storage of information between commands
        self._last_result = None
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        
        # Used to make RESTful calls using the User Token.
        self.user_http = HTTPClient(None, proxy=None, proxy_auth=None, loop=asyncio.get_event_loop())
        
        # Debug Garbage / work arounds for bugs I saw.
        self.twitch_debug = True
        self.twitter_debug = False
        self.lfg_vc_debug = False
        self.slow_mode_debug = False
        self.ready_check = False
        self.vc_ready = False
        self.use_reactions = True
                
        #scheduler garbage
        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(self.backup_messages_log, 'cron', id='backup_msgs',  minute='*/10')
        self.scheduler.add_job(self.backup_role_trackers, 'cron', id='backup_role_trackers',  minute='*/1')
        self.scheduler.start()
        
        print('past init')

    # noinspection PyMethodOverriding
    def run(self):
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.start(self.token))
            loop.run_until_complete(self.connect())
        except Exception:
            for task in asyncio.Task.all_tasks():
                task.cancel()
        finally:
            loop.close()
            
    async def queue_timed_ban_role(self, sec_time, user, timed_role, role_id, user_id):
        await asyncio.sleep(sec_time)
        if self.channel_bans[role_id][user_id]:
            datetime_timestamp = datetime.fromtimestamp(self.channel_bans[role_id][user_id])
            if datetime.utcnow() < datetime_timestamp:
                return
                print('Mute extended for {} for {} more seconds'.format(user.name if user != None else user_id, (datetime_timestamp - datetime.utcnow()).total_seconds()))
        else:
            return
        if not user:
            self.channel_bans[role_id].pop(user_id, None)
            write_json('channel_banned.json', self.channel_bans)
            return
        try:
            user = discord.utils.get(self.guilds, id=SERVERS['main']).get_member(user.id)
            if user:
                self.channel_bans[role_id].pop(user.id, None)
                write_json('channel_banned.json', self.channel_bans)
                if not timed_role:
                    timed_role = discord.utils.get(discord.utils.get(self.guilds, id=SERVERS['main']).roles, id=role_id)
                if timed_role in user.roles:
                    if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await user.remove_roles(timed_role, atomic = True)
        except:
            traceback.print_exc()            
            
    async def generate_streaming_embed(self, resp, streamer):
        em = discord.Embed(colour=discord.Colour(0x56d696), description=resp["stream"]["channel"]["status"], timestamp=datetime.strptime(resp["stream"]["created_at"], "%Y-%m-%dT%H:%M:%SZ"))
        if resp["stream"]["channel"]["logo"]:
            prof_pic = resp["stream"]["channel"]["logo"]
        else:
            prof_pic = 'http://i.imgur.com/IyuxtDT.jpg'
        async with aiohttp.ClientSession() as sess:
            async with sess.get(str(resp["stream"]["preview"]["large"])) as r:
                data = await r.read()
                with open("img.png", "wb") as f:
                    f.write(data)
        file = discord.File("/home/bots/anthembot/img.png", filename="img.png")
        em.set_image(url="attachment://img.png")
        em.set_author(name=streamer, url='https://www.twitch.tv/{}'.format(streamer), icon_url=prof_pic)
        em.set_footer(text="Language: {}".format(resp["stream"]["channel"]["language"].upper()))

        em.add_field(name="Status", value="LIVE", inline=True)
        em.add_field(name="Viewers", value=resp["stream"]["viewers"], inline=True)
        return em
            
    async def backup_messages_log(self):
        for filename, contents in self.messages_log.items():
            try:
                write_json('channel_logs/%s.json' % str(filename), contents)
            except:
                pass
            
    async def backup_role_trackers(self):
        # write_json('muted.json', self.muted_dict)
        write_json('channel_banned.json', self.channel_bans)
            
    async def lfg_channel_informer(self):
        for channel_id in TEXT_CATS.values():
            category = self.get_channel(channel_id)
            for channel in category.channels:
                has_recent_msg = await channel.history(limit=15).get(author__id=self.user.id, content=MSGS['lfg_awareness'])
                if not has_recent_msg:
                    await self.safe_send_message(channel, content=MSGS['lfg_awareness'])
            
    async def reorder_small_lfg_channels(self):
        for cat_id in LOOP_CATS:
            cat = self.get_channel(cat_id)
            if not cat:
                continue
            empty_vcs = [channel for channel in cat.channels if isinstance(channel, discord.VoiceChannel) and len(channel.members) == 0]
            for channel in empty_vcs:
                await channel.edit(position=1)
            
                        
    async def reorder_lfg_categories(self):
        while True:
            if not self.vc_ready:
                await asyncio.sleep(2)
                continue
            try:
                for cat_id in DOUBLE_SORTED_CATS:
                    await asyncio.sleep(2)
                    main_cat = self.get_channel(cat_id)
                    empty_cat = self.get_channel((MAIN_TO_EMPTY[cat_id]))
                    secondary_cat = self.get_channel((MAIN_TO_OVERSPILL_CATS[main_cat.id]))
                    tertiery_cat = self.get_channel((MAIN_TO_OVERSPILL_CATS[secondary_cat.id]))
                    if tertiery_cat:
                        combined_channel_ids = [channel_id for channel_id in self.vc_tracker[main_cat.id] if self.vc_tracker[main_cat.id] and (self.vc_tracker[main_cat.id][channel_id]["mem_len"] < 2 or (self.vc_tracker[main_cat.id][channel_id]["mem_len"] == 2 and channel_id not in self.vc_moved_2s))]
                        combined_channel_ids = combined_channel_ids + [channel_id for channel_id in self.vc_tracker[secondary_cat.id] if self.vc_tracker[secondary_cat.id]  and (self.vc_tracker[secondary_cat.id][channel_id]["mem_len"] < 2 or (self.vc_tracker[secondary_cat.id][channel_id]["mem_len"] == 2 and channel_id not in self.vc_moved_2s))]
                        combined_channel_ids = combined_channel_ids + [channel_id for channel_id in self.vc_tracker[tertiery_cat.id] if self.vc_tracker[tertiery_cat.id]  and (self.vc_tracker[tertiery_cat.id][channel_id]["mem_len"] < 2 or (self.vc_tracker[tertiery_cat.id][channel_id]["mem_len"] == 2 and channel_id not in self.vc_moved_2s))]
                    else:
                        combined_channel_ids = [channel_id for channel_id in self.vc_tracker[main_cat.id] if self.vc_tracker[main_cat.id] and (self.vc_tracker[main_cat.id][channel_id]["mem_len"] < 2 or (self.vc_tracker[main_cat.id][channel_id]["mem_len"] == 2 and channel_id not in self.vc_moved_2s))]
                        combined_channel_ids = combined_channel_ids + [channel_id for channel_id in self.vc_tracker[secondary_cat.id] if self.vc_tracker[secondary_cat.id] and (self.vc_tracker[secondary_cat.id][channel_id]["mem_len"] < 2 or (self.vc_tracker[secondary_cat.id][channel_id]["mem_len"] == 2 and channel_id not in self.vc_moved_2s))]

                    for channel_id in combined_channel_ids:
                        channel = self.get_channel(channel_id)
                        if not channel: continue
                        if self.vc_tracker[channel.category.id][channel.id]["mem_len"] == 2:
                            asyncio.ensure_future(self.vc_2s_queuer(channel))
                        try:
                            item = self.vc_tracker[channel.category.id][channel.id]
                            self.vc_tracker[channel.category.id].pop(channel.id, None)
                            await channel.edit(category=empty_cat, sync_permissions=True, user_limit=3 if channel.id not in self.vc_num_locks.values() else len(channel.members))
                            self.vc_tracker[empty_cat.id][channel.id] = item
                        except:
                            self.vc_tracker[channel.category.id].pop(channel.id, None)
                            await channel.edit(category=empty_cat, sync_permissions=True, user_limit=3 if channel.id not in self.vc_num_locks.values() else len(channel.members))
                            self.vc_tracker[empty_cat.id][channel.id] = {"mem_len": len(channel.members), "last_event": datetime.utcnow(), "pending_future": None}
                            
                    filled_vcs_in_empty = [channel_id for channel_id in self.vc_tracker[empty_cat.id] if self.vc_tracker[empty_cat.id] and (self.vc_tracker[empty_cat.id][channel_id]["mem_len"] > 2 or (self.vc_tracker[empty_cat.id][channel_id]["mem_len"] == 2 and channel_id in self.vc_moved_2s))]
                    for channel_id in filled_vcs_in_empty:
                        channel = self.get_channel(channel_id)
                        cat_to_move = None
                        if len(main_cat.channels) < 48:
                            cat_to_move = main_cat
                        elif secondary_cat and len(secondary_cat.channels) < 48:
                            cat_to_move = secondary_cat
                        elif tertiery_cat and len(tertiery_cat.channels) < 48:
                            cat_to_move = tertiery_cat
                        if cat_to_move:
                            try:
                                item = self.vc_tracker[channel.category.id][channel.id]
                                self.vc_tracker[channel.category.id].pop(channel.id, None)
                                await channel.edit(category=cat_to_move, sync_permissions=True, user_limit=3 if channel.id not in self.vc_num_locks.values() else len(channel.members))
                                self.vc_tracker[cat_to_move.id][channel.id] = item
                            except:
                                self.vc_tracker[channel.category.id].pop(channel.id, None)
                                await channel.edit(category=cat_to_move, sync_permissions=True, user_limit=3 if channel.id not in self.vc_num_locks.values() else len(channel.members))
                                self.vc_tracker[cat_to_move.id][channel.id] = {"mem_len": len(channel.members), "last_event": datetime.utcnow(), "pending_future": None}
                        else:
                            print("fucking cat cant move fuck this shit")
                            if tertiery_cat:
                                print(f"{len(main_cat.channels)} - {main_cat.name} {len(secondary_cat.channels)} - {secondary_cat.name} {len(tertiery_cat.channels)} - {tertiery_cat.name}")
                            else:
                                print(f"{len(main_cat.channels)} - {main_cat.name} {len(secondary_cat.channels)} - {secondary_cat.name}")
            except:
                traceback.print_exc()
            
    async def wait_until_really_ready(self):
        while not self.ready_check:
            await asyncio.sleep(1)
            
    async def voice_channel_resizing(self):
        while True:
            if not self.vc_ready: 
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(1)
            for category_id in self.vc_tracker:
                try:
                    # if self.lfg_vc_debug: print(f"RESIZER: ----New Category {VC_CATS_REV[category_id]}----")
                    
                    if category_id in OVERSPILL_CATS:
                        baseline_channel_bucket = 0
                        empty_channel_bucket = 0
                    else:
                        if category_id in DOUBLE_SORTED_CATS:
                            check_cat_id = MAIN_TO_EMPTY[category_id]
                        else:
                            check_cat_id = category_id
                        baseline_channel_bucket = len(self.vc_tracker[check_cat_id]) if len(self.vc_tracker[check_cat_id]) < 9 else 9
                        # if self.lfg_vc_debug: print(f"RESIZER: Cat {VC_CATS_REV[category_id]} baseline chan bucket - {baseline_channel_bucket}")
                        if baseline_channel_bucket < 9:
                            for _ in range(9-baseline_channel_bucket):
                                await self.queue_channel_for_creation(check_cat_id)
                                baseline_channel_bucket += 1
                                
                        empty_channel_bucket = len(self.vc_tracker[check_cat_id]) - len([item for item in self.vc_tracker[check_cat_id] if self.vc_tracker[check_cat_id] and self.vc_tracker[check_cat_id][item]["mem_len"] > 0])
                        empty_channel_bucket = empty_channel_bucket if empty_channel_bucket < 5 else 5
                        # if self.lfg_vc_debug: print(f"RESIZER: Cat {VC_CATS_REV[category_id]} empty chan bucket - {empty_channel_bucket}")
                        if empty_channel_bucket < 5:
                            for _ in range(5-empty_channel_bucket): 
                                await self.queue_channel_for_creation(check_cat_id)
                                empty_channel_bucket += 1
                    for channel_id in self.vc_tracker[category_id]:
                        channel_obj = self.vc_tracker[category_id][channel_id]
                        if not channel_obj: 
                            del self.vc_tracker[category_id][channel_id]
                            continue
                        if channel_obj["mem_len"] < 1 and empty_channel_bucket != 0:
                            # if self.lfg_vc_debug: print(f"RESIZER: Channel {channel_id} put in empty chan bucket")
                            if channel_obj["pending_future"]:
                                check = channel_obj["pending_future"].cancel()
                                # if self.lfg_vc_debug: print(f"DELETOR: Chan ID {channel_id}:{category_id} task delete? {check}")
                                self.vc_tracker[category_id][channel_id]["pending_future"] = None
                            empty_channel_bucket -= 1
                            if baseline_channel_bucket != 0:
                                # if self.lfg_vc_debug: print(f"RESIZER: ALSO Channel {channel_id} put in basline chan bucket")
                                baseline_channel_bucket -= 1
                        elif baseline_channel_bucket != 0:
                            # if self.lfg_vc_debug: print(f"RESIZER: Channel {channel_id} put in baseline chan bucket")
                            if channel_obj["pending_future"]:
                                check = channel_obj["pending_future"].cancel()
                                # if self.lfg_vc_debug: print(f"DELETOR: Chan ID {channel_id}:{category_id} task delete? {check}")
                                self.vc_tracker[category_id][channel_id]["pending_future"] = None
                            baseline_channel_bucket -= 1
                        elif channel_obj["mem_len"] < 1 and not channel_obj["pending_future"]:
                            self.vc_tracker[category_id][channel_id]["pending_future"] = asyncio.ensure_future(self.queue_channel_for_deletion(category_id, channel_id, channel_obj["last_event"]))
                        elif channel_obj["mem_len"] < 2 and not channel_obj["pending_future"]:
                            self.vc_tracker[category_id][channel_id]["pending_future"] = asyncio.ensure_future(self.queue_channel_for_deletion(category_id, channel_id, channel_obj["last_event"], empty=False))
                        elif channel_obj["mem_len"] > 1 and channel_obj["pending_future"]:
                            check = channel_obj["pending_future"].cancel()
                            # if self.lfg_vc_debug: print(f"DELETOR: Chan ID {channel_id}:{category_id} task delete? {check}")
                            self.vc_tracker[category_id][channel_id]["pending_future"] = None
                except:
                    traceback.print_exc()
    
    async def queue_channel_for_creation(self, category_id):
        if self.lfg_vc_debug: print(f"CREATOR: channel queued in {category_id}")
        cat = self.get_channel(category_id)
        if self.lfg_vc_debug: print(f"CREATOR: {cat.name}")
        chan_name = CAT_LFG_NAMING[VC_CATS_REV[category_id]].format(get_monster())
        try:
            chan = await discord.utils.get(self.guilds, id=SERVERS['main']).create_voice_channel(chan_name, category=cat)
        except discord.HTTPException:
            if category_id in DOUBLE_SORTED_CATS:
                secondary_cat = self.get_channel((MAIN_TO_OVERSPILL_CATS[category_id]))
                try:
                    chan = await discord.utils.get(self.guilds, id=SERVERS['main']).create_voice_channel(chan_name, category=secondary_cat)
                except discord.HTTPException:
                    
                    tertiery_cat = self.get_channel((MAIN_TO_OVERSPILL_CATS[secondary_cat.id]))
                    try:
                        chan = await discord.utils.get(self.guilds, id=SERVERS['main']).create_voice_channel(chan_name, category=tertiery_cat)
                    except discord.HTTPException:
                        return
            
        if self.lfg_vc_debug: print(f"CREATOR: new chan created: {chan.name}")
        await chan.edit(user_limit=3, bitrate=96000, sync_permissions=True)
        self.vc_tracker[cat.id][chan.id] = {"mem_len": len(chan.members), "last_event": datetime.utcnow(), "pending_future": None}
        if self.lfg_vc_debug: print(f"CREATOR: new chan {chan.name} added to tracker")
    
    async def queue_channel_for_deletion(self, category_id, channel_id, last_event, empty=True):
        if self.lfg_vc_debug: print(f"DELETOR: Chan ID {channel_id}:{category_id} added to deletor")
        if empty:
            await asyncio.sleep(60)
        else:
            await asyncio.sleep(600)
        if self.lfg_vc_debug: print(f"DELETOR: Chan ID {channel_id}:{category_id} timed out in deletor, checking for deletion")
        channel_obj = self.vc_tracker[category_id][channel_id]
        if channel_obj["last_event"] == last_event or channel_obj["mem_len"] < 2:
            if self.lfg_vc_debug: print(f"DELETOR: if statement passed, deleting")
            chan = self.get_channel(channel_id)
            if self.lfg_vc_debug: print(f"DELETOR: chan name {chan.name}")
            await chan.delete(reason="Resizing LFG")
            if self.lfg_vc_debug: print(f"DELETOR: deleted")
        else:
            if self.lfg_vc_debug: print(f"DELETOR: if statement didn't pass")
            
    async def vc_member_num_buffer(self, channel, timestamp, member_count):
        if self.lfg_vc_debug: print(f"BUFFER: Waiting for write for {channel.name} - {channel.id}")
        await asyncio.sleep(3)
        if self.vc_tracker[channel.category.id] and channel.id in self.vc_tracker[channel.category.id] and self.vc_tracker[channel.category.id][channel.id]["last_event"] == timestamp:
            if self.lfg_vc_debug: print(f"BUFFER: {channel.name} buffer passed, writing to tracker")
            self.vc_tracker[channel.category.id][channel.id]["mem_len"] = member_count
            
    async def vc_2s_queuer(self, channel):
        if channel.id not in self.vc_queued_2s and channel.id not in self.vc_moved_2s:
            self.vc_queued_2s.append(channel.id)
            await asyncio.sleep(120)
            self.vc_queued_2s.remove(channel.id)
            self.vc_moved_2s.append(channel.id)
        
    async def get_tweets(self):
        await self.wait_until_really_ready()
        
        if self.twitter_debug: print('starting tweet fetching')
        
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        loop = asyncio.get_event_loop()
        
        def get_twitter_data(twitter_handle):
            return self.twitAPI.request('statuses/user_timeline', {'screen_name': twitter_handle,
                                                                    'include_rts': False,
                                                                    'tweet_mode': "extended",
                                                                    'count': 15})
        for handle in self.twitter_watch_list:
            future = loop.run_in_executor(executor, get_twitter_data, handle)
                        
            r = await future
            highest_id = 0
            for item in r.get_iterator():
                if item['id'] > highest_id:
                    highest_id = item['id']
            if self.twitter_debug: print(f"{handle}: {highest_id}")
            self.twitter_id_cache[handle] = highest_id
                
        while True:
            try:
                for handle in self.twitter_watch_list:
                    if self.twitter_debug: print('checking ' + handle)
                    future = loop.run_in_executor(executor, get_twitter_data, handle)
                    
                    r = await future
                    if handle not in self.twitter_id_cache:
                        self.twitter_id_cache[handle] = 0
                    highest_id = self.twitter_id_cache[handle]
                    for item in reversed(list(r.get_iterator())):
                        if self.twitter_debug: print(f"Handle: {handle}\nShould be posted: {item['id'] > self.twitter_id_cache[handle]}\nNew ID: {item['id']}\nStored ID: {self.twitter_id_cache[handle]}")
                        if self.twitter_debug: print()
                        if self.twitter_debug: print(f"{item}")
                        if self.twitter_debug: print()
                        if "full_text" in item and item['id'] > self.twitter_id_cache[handle]:
                            if self.twitter_debug: print('new tweet found!')
                            if item['in_reply_to_screen_name'] and item['in_reply_to_screen_name'] != handle:
                                if self.twitter_debug: print('tweet is a reply to another, not in thread. skipping...')
                                continue
                            blacklist_strings = ['RT @']
                            whitelist_strings = ['anthem']
                            if not any(x.lower() in item['full_text'].lower() for x in blacklist_strings): # or any(x.lower() in item['full_text'].lower() for x in whitelist_strings):
                                if self.twitter_debug: print('posting tweet by ' + handle)
                                if item['id'] > highest_id:
                                    highest_id = item['id']
                                embed = await self.generate_new_tweet_embed(item)
                                await self.safe_send_message(self.get_channel(CHANS['tweets']), embed=embed)
                    self.twitter_id_cache[handle] = highest_id
                    await asyncio.sleep(5)
            except RuntimeError:
                traceback.print_exc()
                return
            except:
                traceback.print_exc()
                print('error within twitter loop, handled to prevent breaking')

                
                
    async def generate_new_tweet_embed(self, resp):
        final_text = None
        image_url = None
        
        if 'media' in resp["entities"]:
            if len(resp["entities"]["media"]) == 1:
                for media in resp["entities"]["media"]:
                    if not final_text:
                        final_text = clean_string(resp["full_text"]).replace(media["url"], '')
                    else:
                        final_text = final_text.replace(media["url"], '')
                    image_url = media["media_url_https"]
        if 'urls' in resp["entities"]:
            for url in resp["entities"]["urls"]:
                if resp["is_quote_status"] and url["url"] == resp["quoted_status_permalink"]["url"]:
                    if not final_text:
                        final_text = clean_string(resp["full_text"]).replace(url["url"], '')
                    else:
                        final_text = final_text.replace(url["url"], '')
                else:
                    if not final_text:
                        final_text = clean_string(resp["full_text"]).replace(url["url"], '[{0}]({1})'.format(url["display_url"], url["expanded_url"]))
                    else:
                        final_text = final_text.replace(url["url"], '[{0}]({1})'.format(url["display_url"], url["expanded_url"]))
        if not final_text:
            final_text = clean_string(resp["full_text"])
        
        date_time = datetime.strptime(resp["created_at"], "%a %b %d %H:%M:%S +0000 %Y")
        em = discord.Embed(colour=discord.Colour(0x00aced), description=final_text, timestamp=date_time)
        if image_url:
            em.set_image(url=image_url)
        em.set_author(name=resp["user"]['screen_name'], url='https://twitter.com/{}/status/{}'.format(resp["user"]["screen_name"], resp["id"]), icon_url=resp["user"]["profile_image_url_https"])
        if resp["is_quote_status"]:
            em.add_field(name='~~                    ~~', value=clean_string(f'→*[**`@{resp["quoted_status"]["user"]["screen_name"]}`**]({resp["quoted_status_permalink"]["expanded"]}):*\n```{resp["quoted_status"]["full_text"]}```'), inline=False)
        return em
        
    async def generate_tweet_embed(self, resp):
        final_text = None
        image_url = None
        
        if 'media' in resp["entities"]:
            if len(resp["entities"]["media"]) == 1:
                for media in resp["entities"]["media"]:
                    if not final_text:
                        final_text = clean_string(resp["full_text"]).replace(media["url"], '')
                    else:
                        final_text = final_text.replace(media["url"], '')
                    image_url = media["media_url_https"]
        if 'urls' in resp["entities"]:
            for url in resp["entities"]["urls"]:
                if not final_text:
                    final_text = clean_string(resp["full_text"]).replace(url["url"], '[{0}]({1})'.format(url["display_url"], url["expanded_url"]))
                else:
                    final_text = final_text.replace(url["url"], '[{0}]({1})'.format(url["display_url"], url["expanded_url"]))
        if not final_text:
            final_text = clean_string(resp["full_text"])
        
        date_time = datetime.strptime(resp["created_at"], "%a %b %d %H:%M:%S +0000 %Y")
        em = discord.Embed(colour=discord.Colour(0x00aced), description=final_text, timestamp=date_time)
        if image_url:
            em.set_image(url=image_url)
        em.set_author(name=resp["user"]['screen_name'], url='https://twitter.com/{}/status/{}'.format(resp["user"]["screen_name"], resp["id"]), icon_url=resp["user"]["profile_image_url_https"])
        return em
            
    async def check_twitch_streams(self):
        await self.wait_until_really_ready()
        def is_me(m):
            return m.author == self.user
        try:
            await self.get_channel(CHANS['twitch']).purge(limit=100, check=is_me)
        except:
            async for entry in self.get_channel(CHANS['twitch']).history(limit=10000):
                if entry.author == self.user:
                    await self.safe_delete_message(entry)
                    await asyncio.sleep(0.21)
        while True:
            for streamer in self.twitch_watch_list:
                try:
                    async with aiohttp.ClientSession() as session:
                        await asyncio.sleep(5)
                        resp = None
                        async with session.get('https://api.twitch.tv/kraken/streams/{}?client_id={}'.format(streamer, self.twitch_client_id)) as r:
                            try:
                                resp = await r.json()
                            except json.decoder.JSONDecodeError:
                                pass
                        if resp and "stream" in resp and resp["stream"] and (resp["stream"]["game"] == 'Anthem' or streamer in ['anthemgame']):
                            # if streamer in ['rainbow6']:
                                # target_channel = 414812315729526784
                            # else:
                            target_channel = CHANS['twitch']
                            if streamer not in self.twitch_is_live:
                                if self.twitch_debug: print('Creating new embed for user %s' % streamer)
                                self.twitch_is_live[streamer] = {'detected_start': datetime.utcnow(),
                                                                 'view_count_updated': datetime.utcnow(),
                                                                 'offline_cooldown': False,
                                                                 'embedded_object': await self.generate_streaming_embed(resp, streamer),
                                                                 'message': None}
                                self.twitch_is_live[streamer]['message'] = await self.safe_send_message(self.get_channel(target_channel), embed=self.twitch_is_live[streamer]['embedded_object'], file=discord.File("/home/bots/anthembot/img.png", filename="img.png"))
                            else:
                                if datetime.utcnow() - timedelta(minutes=60) > self.twitch_is_live[streamer]['detected_start']:
                                    if self.twitch_debug: print('Recreating new embed for user %s' % streamer)
                                    if self.twitch_is_live[streamer]['message']:
                                        await self.safe_delete_message(self.twitch_is_live[streamer]['message'])
                                    self.twitch_is_live[streamer] = {'detected_start': datetime.utcnow(),
                                                                     'view_count_updated': datetime.utcnow(),
                                                                     'offline_cooldown': False,
                                                                     'embedded_object': await self.generate_streaming_embed(resp, streamer),
                                                                     'message': None}
                                    self.twitch_is_live[streamer]['message'] = await self.safe_send_message(self.get_channel(target_channel), embed=self.twitch_is_live[streamer]['embedded_object'], file=discord.File("/home/bots/anthembot/img.png", filename="img.png"))
                                elif datetime.utcnow() - timedelta(minutes=15) > self.twitch_is_live[streamer]['view_count_updated'] and self.twitch_is_live[streamer]['message']:
                                    if self.twitch_debug: print('Updating embeds view count for user %s' % streamer)
                                    self.twitch_is_live[streamer]['embedded_object'] = await self.generate_streaming_embed(resp, streamer)
                                    self.twitch_is_live[streamer]['view_count_updated'] = datetime.utcnow()
                                    await self.safe_edit_message(self.twitch_is_live[streamer]['message'], embed=self.twitch_is_live[streamer]['embedded_object'])
                                    
                        elif streamer in self.twitch_is_live and not self.twitch_is_live[streamer]['offline_cooldown']:
                            if self.twitch_debug: print('User %s detected offline, marking as such' % streamer)
                            await self.safe_delete_message(self.twitch_is_live[streamer]['message'])
                            self.twitch_is_live[streamer]['message'] = None
                            self.twitch_is_live[streamer]['offline_cooldown'] = True
                            
                except RuntimeError:
                    return
                except:
                    traceback.print_exc()
                    print('error within twitch loop, handled to prevent breaking')

    def load_channel_logs(self):
        channel_logs = {}
        for root, dirs, files in os.walk('channel_logs', topdown=False):
            for file in files:
                fileroute = os.path.join(root, file)
                try:
                    channel_logs[int(file[:-5])] = {int(key): value for key, value in load_json(fileroute).items()}
                except:
                    pass
        final_dict = {}
        for chan_id, value in channel_logs.items():
            for message_id, fields in value.items():
                if datetime.utcnow() - timedelta(days=7) < snowflake_time(message_id):
                    final_dict[chan_id] = {message_id: fields}
        return final_dict
        
    async def do_search(self, guild_id, **kwargs):
        search_args = {}
        search_args['author_id'] = kwargs.pop('author_id', None)
        search_args['mentions']  = kwargs.pop('mentions', None)
        search_args['has']  = kwargs.pop('has', None)
        search_args['max_id']  = kwargs.pop('max_id', None)
        search_args['min_id']  = kwargs.pop('min_id', None)
        search_args['channel_id']  = kwargs.pop('channel_id', None)
        search_args['content']  = kwargs.pop('content', None)
        string_query = ''
        for param, value in search_args.items():
            if value:
                string_query = string_query + f'&{param}={value}' if string_query else f'?{param}={value}'
        return await self.user_http.request(Route('GET', f'/guilds/{guild_id}/messages/search{string_query}'))
        
        
    async def get_profile(self, user_id):
        state = self._connection
        data = await self.user_http.get_user_profile(user_id)

        def transform(d):
            return state._get_guild(int(d['id']))

        since = data.get('premium_since')
        mutual_guilds = list(filter(None, map(transform, data.get('mutual_guilds', []))))
        user = data['user']
        return discord.Profile(flags=user.get('flags', 0),
                               premium_since=discord.utils.parse_time(since),
                               mutual_guilds=mutual_guilds,
                               user=discord.User(data=user, state=state),
                               connected_accounts=data['connected_accounts'])
                       
    async def on_ready(self):
        await asyncio.sleep(10)
        self.ready_check = True
        print('Connected!\n')
        print('Populating New Ban Roles....')
        new_roles = [role for role in discord.utils.get(self.guilds, id=SERVERS['main']).roles if role.name.startswith('Ban') and role.id not in self.channel_bans]
        if new_roles:
            print('Found %s new roles!' % len(new_roles))
            for role in new_roles:
                self.channel_bans[role.id] = {member.id: None for member in discord.utils.get(self.guilds, id=SERVERS['main']).members if role.id in [role.id for role in member.roles]}
                write_json('channel_banned.json', self.channel_bans)     
        print('Done!\n\nFinalizing User Login...')
        await self.user_http.static_login(self.user_token, bot=False)
        # print('Done!\n\nPutting Together VC Tracker Data...')
        # self.vc_categories = {'na': self.get_channel(VC_CATS['na']),
                              # 'na2': self.get_channel(VC_CATS['na2']),
                              # 'na3': self.get_channel(VC_CATS['na3']),
                              # 'na_empty': self.get_channel(VC_CATS['na_empty']),
                              # 'eu': self.get_channel(VC_CATS['eu']),
                              # 'eu2': self.get_channel(VC_CATS['eu2']),
                              # 'eu_empty': self.get_channel(VC_CATS['eu_empty']),
                              # 'oce': self.get_channel(VC_CATS['oce']),
                              # 'sea': self.get_channel(VC_CATS['sea']),
                              # 'latam': self.get_channel(VC_CATS['latam'])}
            
        # for category in self.vc_categories.values():
            # self.vc_tracker[category.id] = {}
            # for channel in [channel for channel in category.channels if isinstance(channel, discord.VoiceChannel)]:
                # self.vc_tracker[category.id][channel.id] = {"mem_len": len(channel.members), "last_event": datetime.utcnow(), "pending_future": None}
            
        print('Done!\n\nDeserializing Channel Bans...')
        temp_dict = dict(self.channel_bans)
        target_server = discord.utils.get(self.guilds, id=SERVERS['main'])
        for role_id, user_blob in temp_dict.items():
            cban_role = discord.utils.get(target_server.roles, id=role_id)
            if not user_blob: continue
            for user_id, timestamp in user_blob.items():
                user = discord.utils.get(target_server.members, id=user_id)
                if timestamp:
                    datetime_timestamp = datetime.fromtimestamp(timestamp)
                    if datetime.utcnow() < datetime_timestamp:
                        asyncio.ensure_future(self.queue_timed_ban_role((datetime_timestamp-datetime.utcnow()).total_seconds(), user, cban_role, role_id, user_id))
                        print('Queueing serialized mute for {} for {} seconds'.format(user.name if user != None else user_id, (datetime_timestamp - datetime.utcnow()).total_seconds()))
                    else:
                        asyncio.ensure_future(self.queue_timed_ban_role(0, user, cban_role, role_id, user_id))
                        print('Serialized mute period has passed for {}'.format(user.name if user != None else user_id))
                        continue
                else:
                    print('Queueing serialized nontimed mute for {}'.format(user.name if user != None else user_id, ))
                if user:
                    try:
                        if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await user.edit(roles = list(set(([role for role in user.roles] + [cban_role]))))
                    except discord.Forbidden:
                        print('cannot add role to %s, permission error' % user.name)
                
        self.vc_ready = True
        print('Done!\n\nPopulating Message Logs...')
        self.messages_log  = self.load_channel_logs()
        print('Done!')        
        print('\n~')

    async def _wait_delete_msg(self, message, after):
        await asyncio.sleep(after)
        await self.safe_delete_message(message)

    async def safe_send_message(self, dest, *, content=None, tts=False, embed=None, file=None, files=None, expire_in=None, nonce=None, quiet=None):
        msg = None
        try:
            time_before = timer()
            msg = await dest.send(content=content, tts=tts, embed=embed, file=file, files=files)
            time_after = timer()
            # if embed:
                # print(f'Embed send time: "{time_after - time_before}"')
            if msg and expire_in:
                asyncio.ensure_future(self._wait_delete_msg(msg, expire_in))

        except discord.Forbidden:
            if not quiet:
                print("Error: Cannot send message to %s, no permission" % dest.name)
        except discord.NotFound:
            if not quiet:
                print("Warning: Cannot send message to %s, invalid channel?" % dest.name)
        finally:
            if msg: return msg

    async def safe_delete_message(self, message, *, quiet=False):
        try:
            return await message.delete()

        except discord.Forbidden:
            if not quiet:
                print("Error: Cannot delete message \"%s\", no permission" % message.clean_content)
        except discord.NotFound:
            if not quiet:
                print("Warning: Cannot delete message \"%s\", message not found" % message.clean_content)

    async def safe_edit_message(self, message, *, content=None, expire_in=0, send_if_fail=False, quiet=False, embed=None):
        msg = None
        try:
            if not embed:
                await message.edit(content=content)
                msg = message
            else:
                await message.edit(content=content, embed=embed)
                msg = message

            if msg and expire_in:
                asyncio.ensure_future(self._wait_delete_msg(msg, expire_in))

        except discord.NotFound:
            if not quiet:
                print("Warning: Cannot edit message \"%s\", message not found" % message.clean_content)
            if send_if_fail:
                if not quiet:
                    print("Sending instead")
                msg = await self.safe_send_message(message.channel, content=new)
        finally:
            if msg: return msg
            
    def prefix_only(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            prefix = _get_variable('prefix')
            if self.prefix == prefix:
                # noinspection PyCallingNonCallable
                return await func(self, *args, **kwargs)
            else:
                return

        wrapper.mod_cmd = True
        return wrapper
            
    def double_prefix(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            prefix = _get_variable('prefix')
            if f"{self.prefix}{self.prefix}" == prefix:
                # noinspection PyCallingNonCallable
                return await func(self, *args, **kwargs)
            else:
                return

        wrapper.mod_cmd = True
        return wrapper
            
    def mods_only(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            is_tag = _get_variable('tag_name')
            orig_msg = _get_variable('message')

            if [role for role in orig_msg.author.roles if role.id  in [ROLES['staff']]] or (is_tag and self.tags[is_tag][0] == 'unrestricted_eval'):
                # noinspection PyCallingNonCallable
                return await func(self, *args, **kwargs)
            else:
                return

        wrapper.mod_cmd = True
        return wrapper
        
    @mods_only
    async def cmd_alias(self, guild, raw_leftover_args):
        """
        Usage: {command_prefix}alias [channel ban role alias] [cban role id]
        Creates an alias for use within the `!cban` command. if ran with no args, outputs a list of all known aliases
        """
        if not raw_leftover_args or len(raw_leftover_args) < 2:
            newline = '\n'
            return Response(f'I know the following aliases:{chr(10)}{chr(10)}{newline.join([f"- {alias} for <@&{role_id}>" for alias, role_id in self.cban_role_aliases.items()])}')
        alias = raw_leftover_args.pop(0)
        role_id = raw_leftover_args.pop(0)
        
        role = discord.utils.get(guild.roles, id=int(role_id))
        if not role:
            return CommandError(f"No role with role id \"{role_id}\"")
        self.cban_role_aliases[alias] = role.id
        write_json('cbanrolealiases.json', self.cban_role_aliases)
        return Response(':thumbsup:', reply=True)
        
    async def cmd_shrink(self, message, channel, author):
        """
        Usage: {command_prefix}shrink
        If the user is in a voice channel in a LFG category, it will shrink that voice channel to the number of members currently in it
        If the user who shrinks the voice channel leaves, the channel auto rescales back to 4.
        """
        if author.voice and author.voice.channel and (author.voice.channel.category.id in self.vc_tracker):
            if author.id not in self.vc_num_locks:
                if author.voice.channel.id not in list(self.vc_num_locks.values()) and len(author.voice.channel.members) > 1:
                    await author.voice.channel.edit(user_limit=len(author.voice.channel.members))
                    self.vc_num_locks[author.id] = author.voice.channel.id
                    await self.safe_delete_message(message)
                    return Response(':thumbsup:', reply=True, delete_after=3)
            else:
                await author.voice.channel.edit(user_limit=3)
                self.vc_num_locks.pop(author.id, None)
                await self.safe_delete_message(message)
                return Response(':thumbsup:', reply=True, delete_after=3)
        return
        
    @prefix_only
    async def cmd_lfg(self, message, channel, author, raw_leftover_args):
        """
        Usage: {command_prefix}lfg <text here>
        If the user is in a voice channel in a LFG category, it will generate an embed allowing people to easily come and join their channel
        """
        if message.channel.category.id not in TEXT_CATS.values():
            return Response('This command can only be used in the LFG text channels!', reply=True, delete_after=5)
        if author.voice and author.voice.channel and (author.voice.channel.category.id in self.vc_tracker) and len(author.voice.channel.members) < 3:
            if author.voice.channel.id not in list(self.vc_num_locks.values()):
                invite = await author.voice.channel.create_invite(max_uses=5, max_age=3600)
                await self.safe_delete_message(message)
                if raw_leftover_args:
                    await self.safe_send_message(channel, content=f"Join {' + '.join([user.mention for user in author.voice.channel.members])} in {author.voice.channel.name} via {invite}\n```\n{' '.join((message.clean_content.strip().split())[1:])}\n```")
                else:
                    await self.safe_send_message(channel, content=f"Join {author.mention} in {author.voice.channel.name} via {invite}")
        else:
            return Response('You must be in a LFG Voice Channel to use this command!', reply=True, delete_after=10)
        
    async def cmd_inv(self, message, channel, author):
        """
        Usage: {command_prefix}inv
        If the user is in a voice channel in a LFG category, it will DM them an invite to that vc channel to aid the finding of a group
        """
        if author.voice and author.voice.channel and (author.voice.channel.category.id in self.vc_tracker):
            if author.voice.channel.id not in list(self.vc_num_locks.values()):
                invite = await author.voice.channel.create_invite(max_uses=5, max_age=3600)
                await self.safe_send_message(author, content=invite)
                await self.safe_delete_message(message)
        else:
            return Response('You must be in a LFG Voice Channel to use this command!', reply=True, delete_after=10)
            
        
    @mods_only
    async def cmd_restart(self, channel, author):
        """
        Usage: {command_prefix}restart
        Forces a restart
        """
        await self.safe_send_message(channel, content="Restarting....")
        await self.logout()

        
    @mods_only
    async def cmd_testnewtweet(self, channel, twitter_id):
        """
        THIS IS A DEBUG FUNCTION; PLEASE DONT USE IT
        """
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        
        loop = asyncio.get_event_loop()
        
        def get_twitter_data(twitterid):
            return self.twitAPI.request(f"statuses/show/:{twitterid}", {'tweet_mode': "extended"})
                
        future = loop.run_in_executor(executor, get_twitter_data, twitter_id)
                
        r = await future
        for item in r.get_iterator():
            if "full_text" in item:
                embed = await self.generate_new_tweet_embed(item)
                await self.safe_send_message(channel, embed=embed)
                
    @mods_only
    async def cmd_gettweetdata(self, twitter_id):
        """
        THIS IS A DEBUG FUNCTION; PLEASE DONT USE IT
        """
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        
        loop = asyncio.get_event_loop()
        
        def get_twitter_data(twitterid):
            return self.twitAPI.request(f"statuses/show/:{twitterid}", {'tweet_mode': "extended"})
                
        future = loop.run_in_executor(executor, get_twitter_data, twitter_id)
                
        r = await future
        for item in r.get_iterator():
            if "full_text" in item:
                print(item)
                
    @mods_only
    async def cmd_posttweet(self, twitter_id):
        """
        Usage: {command_prefix}posttweet [status ID]
        Posts a tweet using a status ID to the twitter channel.
        To find this, go to the URL and grab the numbers at the end.
        EX: twitter.com/SexualRhino_/status/[642969316820914176] <-- THAT STUFF THERE
        """
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        
        loop = asyncio.get_event_loop()
        
        def get_twitter_data(twitterid):
            return self.twitAPI.request(f"statuses/show/:{twitterid}", {'tweet_mode': "extended"})
                
        future = loop.run_in_executor(executor, get_twitter_data, twitter_id)
                
        r = await future
        for item in r.get_iterator():
            if "full_text" in item:
                embed = await self.generate_new_tweet_embed(item)
                await self.safe_send_message(self.get_channel(CHANS['tweets']), embed=embed)

    @mods_only
    async def cmd_changeavi(self, author, string_avi):
        """
        Usage: {command_prefix}changeavi img_url.com
        Changes the bot's profile picture to the image listed
        """
        async with aiohttp.get(string_avi) as r:
            data = await r.read()
            await self.user.edit(avatar=data)
        return Response(':thumbsup:', reply=True)
    
    @mods_only
    async def cmd_eval(self, author, guild, message, channel, mentions, eval_content, is_origin_tag=False):
        """
        Usage: {command_prefix}eval "evaluation string"
        runs a command thru the eval param for testing
        """
        env = {
            'self': self,
            'channel': channel,
            'author': author,
            'guild': guild,
            'message': message,
            'mentions': mentions,
            '_': self._last_result
        }

        env.update(globals())
        
        code = cleanup_code(eval_content)
        stdout = StringIO()

        to_compile = f'async def func():\n{textwrap.indent(code, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return Response(f'```py\n{e.__class__.__name__}: {e}\n```')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            await self.safe_send_message(channel, content=f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                if not is_origin_tag:
                    await message.add_reaction('\u2705')
            except:
                pass

            if ret is None:
                if value:
                    await self.safe_send_message(channel, content=f'```py\n{value}\n```')
            else:
                self._last_result = ret
                await self.safe_send_message(channel, content=f'```py\n{value}{ret}\n```')
                
    @mods_only
    async def cmd_changegame(self, author, string_game):
        """
        Usage: {command_prefix}changegame ["new game name"]
        Changes the "Now Playing..." game on Discord!
        """
        await self.change_presence(game=discord.Game(name=string_game))
        return Response(':thumbsup:', reply=True)

    @mods_only
    async def cmd_testoldsort(self, category_sh):
        """
        THIS IS A DEBUG FUNCTION; PLEASE DONT USE IT
        """
        cat = self.get_channel(VC_CATS[category_sh])
        vcs = {float(channel.name.split()[-1]) if len(channel.members) > 0 else float(int(channel.name.split()[-1])/100): channel for channel in cat.channels if isinstance(channel, discord.VoiceChannel)}
        od = collections.OrderedDict(sorted(vcs.items(), reverse=True))
        od_keys = list(reversed(list(od.keys())))
        base_keys = list(vcs.keys())
        if od_keys == base_keys:
            return Response('They should be already ordered! :thumbsup:')
        for channel_name, channel in od.items():
            await channel.edit(position=1)
            
        return Response('They should be ordered! :thumbsup:')

    @mods_only
    async def cmd_testnewsort(self, category_sh):
        """
        THIS IS A DEBUG FUNCTION; PLEASE DONT USE IT
        """
        cat = self.get_channel(VC_CATS[category_sh])
        if not cat:
            raise CommandError('bad cat')
        offset = [channel for channel in cat.channels if isinstance(channel, discord.VoiceChannel)][0].position
        vcs = [[float(channel.name.split()[-1]) if len(channel.members) > 0 else float(int(channel.name.split()[-1])/100), channel] for channel in cat.channels if isinstance(channel, discord.VoiceChannel)]
            
        #Sorting code intended to minimize number of API calls. it hurts tbh
        # Start with a big gap, then reduce the gap 
        n = len(vcs) 
        gap = n/2

        # Do a gapped insertion sort for this gap size. 
        # The first gap elements a[0..gap-1] are already in gapped  
        # order keep adding one more element until the entire array 
        # is gap sorted 
        while gap > 0: 

            for i in range(gap,n): 

                # add a[i] to the elements that have been gap sorted 
                # save a[i] in temp and make a hole at position i 
                temp = vcs[i]

                # shift earlier gap-sorted elements up until the correct 
                # location for a[i] is found 
                j = i 
                while  j >= gap and vcs[j-gap][0] >temp[0]: 
                    vcs[j] = vcs[j-gap] 
                    j -= gap 

                # put temp (the original a[i]) in its correct location 
                vcs[j] = temp 
            gap /= 2
            
        return Response(f'They should be ordered! cycles: {cycles} :thumbsup:')
        
    @double_prefix
    async def cmd_tag(self, message, guild, author, channel, mentions, leftover_args, eval_content):
        """
        Usage {command_prefix}tag tag name
        Gets a tag from the database of tags and returns it in chat for all to see.
        
        Usage {command_prefix}tag list
        Sends you a PM listing all tags in the tag database
        
        Usage {command_prefix}tag [+, add, -, remove,  blacklist]
        Mod only commands, ask rhino if you dont know the full syntax
        """
        if int(author.id) in self.tagblacklist:
            return
        if not leftover_args:
            raise CommandError('Please specify a tag!')
        switch = leftover_args.pop(0).lower()
        if switch in ['+', 'add', '-', 'remove', 'list', 'blacklist']:
            if switch in ['+', 'add']:
                if [role for role in author.roles if role.id  in [ROLES['staff']]]:
                    if len(leftover_args) == 2:
                        if len(leftover_args[0]) > 200 or len(leftover_args[1]) > 1750:
                            raise CommandError('Tag length too long')
                        self.tags[leftover_args[0].lower()] = [False, leftover_args[1]]
                        write_json('tags.json', self.tags)
                        return Response('Tag \"%s\" created' % clean_bad_pings(leftover_args[0]), delete_after=15)
                    elif len(leftover_args) == 3 and 'restrict' in leftover_args[0]:
                        if len(leftover_args[1]) > 200 or len(leftover_args[2]) > 1750:
                            raise CommandError('Tag length too long')
                        self.tags[leftover_args[1].lower()] = [True, leftover_args[2]]
                        write_json('tags.json', self.tags)
                        return Response('Tag \"%s\" created' % clean_bad_pings(leftover_args[1]), delete_after=15)
                    elif 'eval' in leftover_args[0]:
                        if 'open' in leftover_args[1]:
                            if len(leftover_args[2]) > 200:
                                raise CommandError('Tag name too long')
                            self.tags[leftover_args[2].lower()] = ['unrestricted_eval', cleanup_code(eval_content)]
                            write_json('tags.json', self.tags)
                            return Response('Tag \"%s\" created' % clean_bad_pings(leftover_args[2]), delete_after=15)
                        else:
                            if len(leftover_args[1]) > 200:
                                raise CommandError('Tag name too long')
                            self.tags[leftover_args[1].lower()] = ['eval', cleanup_code(eval_content)]
                            write_json('tags.json', self.tags)
                            return Response('Tag \"%s\" created' % clean_bad_pings(leftover_args[1]), delete_after=15)
                        
                    else:
                        print(leftover_args)
                        raise CommandError('Bad input')
            elif switch == 'list':
                try:
                    this = sorted(list(self.tags.keys()), key=str.lower)
                    new_this = [this[0]]
                    for elem in this[1:]:
                        if len(new_this[-1]) + len(elem) < 70:
                            new_this[-1] = new_this[-1] + ', ' + elem
                        else:
                            new_this.append(elem)
                    final = clean_bad_pings('%s' % '\n'.join(new_this))
                    if len(final) > 1800:
                        final_this = [new_this[0]]
                        for elem in new_this[1:]:
                            if len(final_this[-1]) + len(elem) < 1800:
                                final_this[-1] = final_this[-1] + '\n' + elem
                            else:
                                final_this.append(elem)
                        for x in final_this:
                            await self.safe_send_message(author, content=x)
                    else:
                        await self.safe_send_message(author, content=final)
                except Exception as e:
                    print(e)
            elif switch == 'blacklist':
                if [role for role in author.roles if role.id  in [ROLES['staff']]]:
                    for user in mentions:
                        self.tagblacklist.append(int(user.id))
                        return Response('User `{}` was blacklisted'.format(clean_bad_pings(user.name)), delete_after=20)
            else:
                if [role for role in author.roles if role.id  in [ROLES['staff']]]:
                    try:
                        del self.tags[' '.join(leftover_args)]
                        write_json('tags.json', self.tags)
                        return Response('Tag \"%s\" removed' % clean_bad_pings(' '.join(leftover_args)), delete_after=10)
                    except:
                        raise CommandError('Tag doesn\'t exist to be removed')
        else:
            msg = False
            if leftover_args:
                tag_name = '{} {}'.format(switch, ' '.join(leftover_args))
            else:
                tag_name = switch
            for tag in self.tags:
                if tag_name.lower() == tag.lower():
                    if self.tags[tag][0]:
                        if self.tags[tag][0] == 'unrestricted_eval':
                            await self.cmd_eval(message.author, message.guild, message, message.channel, message.mentions, self.tags[tag][1], is_origin_tag=True)
                            return
                        elif not [role for role in author.roles if role.id  in [ROLES['staff']]]:
                            return Response('Tag cannot be used by nonstaff members')
                        elif self.tags[tag][0] == 'eval':
                            await self.cmd_eval(message.author, message.guild, message, message.channel, message.mentions, self.tags[tag][1], is_origin_tag=True)
                            return
                    return Response(clean_bad_pings(self.tags[tag][1]))
            raise CommandError('Tag doesn\'t exist')
    
    # async def cmd_staff(self, message, channel, author, guild):
        # """
        # Usage: {command_prefix}staff
        # Prompts the user to ensure that the staff ping is really what they wanna do
        # implemented to cut down on unnecessary staff pings
        # """
        # check_msg = await self.safe_send_message(channel, content='Please remember to *only* tag staff for things that **absolutely** require **immediate** attention and can only be addressed by server administration.\n\nFor non-immediate topics, *please* send a private message to <@!278980093102260225> to send mod-mail to the administration.\n\nPlease react if you still wish to ping the staff')
        # await check_msg.add_reaction('✅')
        # def check(reaction, user):
            # return user.id == author.id and reaction.message.id == check_msg.id and str(reaction.emoji) == '✅'
        # try:
            # reac, user = await self.wait_for('reaction_add', check=check, timeout=300.0)
        # except asyncio.TimeoutError:
            # return
        
        # if str(reac.emoji) == '✅':
            # role = discord.utils.get(guild.roles, id=ROLES['staff'])
            # await role.edit(mentionable=True)
            # mention_msg = await self.safe_send_message(channel, content='<@&{}>'.format(ROLES['staff']))
            # await asyncio.sleep(1)
            # await mention_msg.add_reaction('☑')
            # await role.edit(mentionable=False)
        # else:
            # return
            
    @double_prefix
    async def cmd_ping(self, message, author, guild):
        """
        Usage: {command_prefix}ping
        Replies with "PONG!"; Use to test bot's responsiveness
        """
        return Response('PONG!', reply=True)
    
    async def cmd_cmdinfo(self, author, command=None):
        """
        Usage {command_prefix}cmdinfo
        Fetches the help info for the bot's commands
        """
        if [role for role in author.roles if role.id  in [ROLES['staff']]]:
            if command:
                cmd = getattr(self, 'cmd_' + command, None)
                if cmd:
                    return Response(
                        "```\n{}```".format(
                            textwrap.dedent(cmd.__doc__)
                        ).format(command_prefix=self.prefix)
                    )
                else:
                    return Response("No such command", delete_after=10)

            else:
                helpmsg = "**Available commands**\n```"
                commands = []

                for att in dir(self):
                    if att.startswith('cmd_') and att != 'cmd_help':
                        command_name = att.replace('cmd_', '').lower()
                        commands.append("{}{}".format(self.prefix, command_name))

                helpmsg += ", ".join(commands)
                helpmsg += "```\n"
                helpmsg += "You can also use `{}help x` for more info about each command.".format(self.prefix)

                return Response(helpmsg, reply=True)
        else:
            if command:
                cmd = getattr(self, 'cmd_' + command, None)
                if cmd and not hasattr(cmd, 'mod_cmd'):
                    return Response(
                        "```\n{}```".format(
                            textwrap.dedent(cmd.__doc__)
                        ).format(command_prefix=self.prefix)
                    )
                else:
                    return Response("No such command", delete_after=10)

            else:
                helpmsg = "**Available commands**\n```"
                commands = []

                for att in dir(self):
                    if att.startswith('cmd_') and att != 'cmd_help' and not hasattr(getattr(self, att), 'mod_cmd'):
                        command_name = att.replace('cmd_', '').lower()
                        commands.append("{}{}".format(self.prefix, command_name))

                helpmsg += ", ".join(commands)
                helpmsg += "```\n"
                helpmsg += "You can also use `{}help x` for more info about each command.".format(self.prefix)

                return Response(helpmsg, reply=True)
                
    @mods_only
    async def cmd_removestream(self, author, channel_name):
        """
        Usage {command_prefix}removestream [twitch channel name]
        Removes the stream from checked streams
        """
        if channel_name in self.twitch_watch_list:
            self.twitch_watch_list.remove(channel_name)
            write_json('twitchwatchlist.json', self.twitch_watch_list)
            return Response(':thumbsup:')
        else:
            raise CommandError('ERROR: Channel not in watch list')

    @mods_only
    async def cmd_addstream(self, author, channel_name):
        """
        Usage {command_prefix}addstream [twitch channel name]
        Adds the stream to the checks for online streams
        """
        self.twitch_watch_list.append(channel_name)
        write_json('twitchwatchlist.json', self.twitch_watch_list)
        return Response(':thumbsup:')

    @mods_only
    async def cmd_unfollowtwitter(self, author, username):
        """
        Usage {command_prefix}unfollowtwitter [twitter name]
        Removes username from twitter channel's watch list
        """
        if username in self.twitter_watch_list:
            self.twitter_watch_list.remove(username)
            write_json('twitterwatchlist.json', self.twitter_watch_list)
            return Response(':thumbsup:')
        else:
            raise CommandError('ERROR: Channel not in watch list')

    @mods_only
    async def cmd_followtwitter(self, author, username):
        """
        Usage {command_prefix}followtwitter [twitter name]
        Adds username to the twitter channel's watch list
        """
        self.twitter_watch_list.append(username)
        write_json('twitterwatchlist.json', self.twitter_watch_list)
        return Response(':thumbsup:')

    @mods_only
    async def cmd_echo(self, author, message, guild, channel, leftover_args):
        """
        Usage {command_prefix}echo #channel "ENTER MESSAGE HERE"
        Sends "ENTER MESSAGE HERE" to #channel as if the bot said it
        """
        chan_mention = message.channel_mentions[0]
        leftover_args = leftover_args[1:]
        await self.safe_send_message(chan_mention, content=' '.join(leftover_args))
        return Response(':thumbsup:')        
        
    @mods_only
    async def cmd_cban(self, message, guild, author, mentions, raw_leftover_args):
        """
        Usage {command_prefix}cban [@mention OR User ID] [role_id or alias] <time>
        Applies channel ban roles for a timed period
        If you'd like to create an alias, find the role id by running `{command_prefix}role ids` and then find the cmdinfo of `{command_prefix}alias`
        """
        if not raw_leftover_args:
            return Response(doc_string(inspect.getdoc(getattr(self, inspect.getframeinfo(inspect.currentframe()).function)), self.prefix))
        
        converter = UserConverter()
        users = []
        seconds_to_mute = None
        
        
        if mentions:
            for user in mentions:
                users.append(user)
                try:
                    raw_leftover_args.remove(user.mention)
                except:
                    raw_leftover_args.remove(f"<@!{user.id}>")
                    
        else:
            temp = list(raw_leftover_args)
            for item in temp:
                try:
                    user_to_append = await converter.convert(message, self, item, discrim_required=True)
                    users.append(user_to_append)
                    raw_leftover_args.remove(item)
                except:
                    traceback.print_exc()
                    pass
                    
        role = raw_leftover_args.pop(0)
        
        if role in [role.name for role in guild.roles]:
            role = discord.utils.get(guild.roles, name=role)
        elif role in [role.id for role in guild.roles]:
            role = discord.utils.get(guild.roles, id=role)
        elif role in self.cban_role_aliases:
            role = discord.utils.get(guild.roles, id=self.cban_role_aliases[role])
        else:
            raise CommandError(f'No role {role} found')
            
        seconds_to_mute = timestamp_to_seconds(''.join(raw_leftover_args))
            
        for user in users:
            try:
                user = guild.get_member(user.id)
                if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await user.edit(roles = list(set(([role for role in user.roles] + [role]))))
                await user.edit(mute=True)
            except discord.Forbidden:
                raise CommandError('Not enough permissions to channel ban user : {}'.format(user.name))
            except:
                traceback.print_exc()
                raise CommandError('Unable to channel ban user defined:\n{}\n'.format(user.name))
        response = ':thumbsup:'
        
        for user in users:
            if seconds_to_mute:
                muted_datetime = datetime.utcnow() + timedelta(seconds = seconds_to_mute)
                self.channel_bans[role.id][user.id] = muted_datetime.timestamp()
                print('user {} now timed channel banned'.format(user.name))
                await self.safe_send_message(self.get_channel(CHANS['staff_bot']), content=f"!addcase CHANNEL_BAN {user.id} --mod={author.id} Applied {role.name} for {''.join(raw_leftover_args)}")
                await self.safe_send_message(self.get_channel(CHANS['muted']), content=MSGS['timed_cban_message'].format(user_mention=user.mention, cban_role=role.name[4:], time=''.join(raw_leftover_args)))
                asyncio.ensure_future(self.queue_timed_ban_role(seconds_to_mute, user, role, role.id, user.id))
                response += ' channel banned for %s seconds' % seconds_to_mute
            else:
                self.channel_bans[role.id][user.id] = None
                await self.safe_send_message(self.get_channel(CHANS['staff_bot']), content=f"!addcase CHANNEL_BAN {user.id} --mod={author.id} Applied {role.name}")
                await self.safe_send_message(self.get_channel(CHANS['muted']), content=MSGS['cban_message'].format(user_mention=user.mention, cban_role=role.name[4:]))
                
        write_json('channel_banned.json', self.channel_bans)
        return Response(response) 
        
    @double_prefix
    @mods_only
    async def cmd_slowmode(self, message, author, guild, channel_mentions, raw_leftover_args):
        """
        Usage: {command_prefix}slowmode [#channel(s)] <time between messages>
        Puts the channel or channels mentioned into a slowmode where users can only send messages every x seconds.
        To turn slow mode off, set the time between messages to "0"
        """
        channels = []
        
        if not raw_leftover_args:
            channels = [channel for channel in guild.channels if isinstance(channel, discord.TextChannel) and channel.slowmode_delay > 0]
            if channels:
                newline = '\n'
                return Response(f'The following channels have slowmode enabled:{chr(10)}{chr(10)}{newline.join([f"- {channel.mention} at {channel.slowmode_delay}s" for channel in channels])}')
            return Response(f'No channels currently have slow mode enabled')
            
        seconds_to_slow = None
        
        
        if channel_mentions:
            for channel in channel_mentions:
                channels.append(channel)
                try:
                    raw_leftover_args.remove(channel.mention)
                except:
                    raw_leftover_args.remove(f"<#{channel.id}>")
                    
        else:
            raise CommandError('ERROR: No channel\'s provided ') 
        
        raw_leftover_args = ''.join(raw_leftover_args)
        seconds_to_slow = timestamp_to_seconds(raw_leftover_args)
        for channel in channels:
            if not seconds_to_slow and raw_leftover_args.startswith("0"):
                await channel.edit(slowmode_delay=0)
                await self.safe_send_message(channel, content='This channel is no longer in slow mode!')
            elif seconds_to_slow and 0 < seconds_to_slow < 120:
                await channel.edit(slowmode_delay=seconds_to_slow)
                await self.safe_send_message(channel, content='The delay between allowed messages is now **%s seconds**!' % seconds_to_slow)
            else:
                raise CommandError('ERROR: Time provided is invalid (not between the range of 0 to 120 seconds).')
        return Response(':thumbsup:')
        
    @mods_only
    async def cmd_purge(self, message, author, guild, channel, mentions):
        """
        Run this command without any args for the help string!
        """
        
        # Shamelessly ripped and modified from R.Danny by Danny#0007.
        # He did this the best so why reinvent the wheel
        
        parser = Arguments(add_help=False, allow_abbrev=False)
        parser.add_argument('--user', '--users', '--u', nargs='+', help='Mentions, IDs, or Names of Target Users.^*')
        parser.add_argument('--contains', '--has', '--c', nargs='+', help='Contents of Msg.^*')
        parser.add_argument('--starts', '--begins', '--startswith', nargs='+', help='Check what Msg ends with.^*')
        parser.add_argument('--ends','--endswith', nargs='+', help='Check what Msg starts with.^*')
        parser.add_argument('--or', action='store_true', dest='_or', help='Flag; Use Logical OR for all checks.^*')
        parser.add_argument('--not', action='store_true', dest='_not', help='Flag; Use Logical NOT for all checks.^*')
        parser.add_argument('--emoji', '--emotes', '--emojis', '--emote', action='store_true', help='Flag; Checks for Custom Emoji.^*')
        parser.add_argument('--bot', '--bots',  '--robots', action='store_const', const=lambda m: m.author.bot, help='Flag; Checks for Bots.^*')
        parser.add_argument('--embeds', action='store_const', const=lambda m: len(m.embeds), help='Flag; Checks for Embeds.^*')
        parser.add_argument('--files', action='store_const', const=lambda m: len(m.attachments), help='Flag; Checks for Files.^*')
        parser.add_argument('--reactions', '--reacts', action='store_const', const=lambda m: len(m.reactions), help='Flag; Checks for Reactions.^*')
        parser.add_argument('--search', '--limit', '--n', type=int, default=100, help='Number of Msgs to Search.^*')
        parser.add_argument('--after', type=int, help='MSG ID to search after.^*')
        parser.add_argument('--before', type=int, help='MSG ID to search before```.^*')

        try:
            _, *msg_args = shlex.split(message.content)
            args = parser.parse_args(msg_args)
        except Exception as e:
            await self.safe_send_message(channel, content=str(e))
            return
        predicates = []
        
        if not msg_args:
            return Response('Usage: !purge{}'.format(parser.format_help()[13:].replace("optional arguments:", "optional arguments:```").replace("],", "],\n ").replace(", --", ",\n  --").replace(".^*", "\n")))
        
        if args.bot:
            predicates.append(args.bot)

        if args.embeds:
            predicates.append(args.embeds)

        if args.files:
            predicates.append(args.files)

        if args.reactions:
            predicates.append(args.reactions)

        if args.emoji:
            custom_emoji = re.compile(r'<:(\w+):(\d+)>')
            predicates.append(lambda m: custom_emoji.search(m.content))

        if args.user:
            users = []
            converter = MemberConverter()
            for u in args.user:
                try:
                    user = await converter.convert(guild, u)
                    users.append(user)
                except Exception as e:
                    await self.safe_send_message(channel, content=str(e))
                    return

            predicates.append(lambda m: m.author in users)

        if args.contains:
            predicates.append(lambda m: any(sub in m.content for sub in args.contains))

        if args.starts:
            predicates.append(lambda m: any(m.content.startswith(s) for s in args.starts))

        if args.ends:
            predicates.append(lambda m: any(m.content.endswith(s) for s in args.ends))

        op = all if not args._or else any
        def predicate(m):
            r = op(p(m) for p in predicates)
            if args._not:
                return not r
            return r

        args.search = max(0, min(2000, args.search)) # clamp from 0-2000
        
        before = discord.Object(id=before) if args.before else message

        after = discord.Object(id=after) if args.after else None

        try:
            deleted = await channel.purge(limit=args.search, before=before, after=after, check=predicate)
        except discord.Forbidden as e:
            raise CommandError('I do not have permissions to delete messages.')
        except discord.HTTPException as e:
            raise CommandError(f'Error: {e} (try a smaller search?)')

        spammers = collections.Counter(m.author.display_name for m in deleted)
        deleted = len(deleted)
        messages = [f'{deleted} message{" was" if deleted == 1 else "s were"} removed.']
        if deleted:
            messages.append('')
            spammers = sorted(spammers.items(), key=lambda t: t[1], reverse=True)
            messages.extend(f'**{name}**: {count}' for name, count in spammers)

        to_send = '\n'.join(messages)

        if len(to_send) > 2000:
            return Response(f'Successfully removed {deleted} messages.', delete_after=10) 
        else:
            return Response(to_send, delete_after=10) 

        
    @mods_only
    async def cmd_userinfo(self, message, guild, channel, author, mentions, leftover_args):
        """
        Usage {command_prefix}userinfo [@mention OR User ID]
        Gathers info on a user and posts it in one easily consumable embed
        """
        if not leftover_args:
            user = author
        else:
            try:
                user = await UserConverter().convert(message, self, ' '.join(leftover_args))
            except:
                user = await self.get_user_info(int(leftover_args.pop(0)))
                
        if not user:
            raise CommandError('No user found by that ID!')
        member = discord.utils.get(guild.members, id=user.id)
        try:
            vc_activity = await self.do_search(guild_id=guild.id, channel_id=CHANS['vclog'], content=user.id)
        except discord.HTTPException:
            raise CommandError('ERROR: Bot still booting, please give me a moment to finish :)')
        vc_string = ''
        if vc_activity["total_results"] < 20:
            vc_string = 'Nothing'
        elif vc_activity["total_results"] < 60:
            vc_string = 'Very Low'
        elif vc_activity["total_results"] < 180:
            vc_string = 'Low'
        elif vc_activity["total_results"] < 540:
            vc_string = 'Medium'
        elif vc_activity["total_results"] < 1000:
            vc_string = 'High'
        elif vc_activity["total_results"] < 1620:
            vc_string = 'Very High'
        else:
            vc_string = 'Very Fucking High, Like Holy Shit'

        if member:
            em = discord.Embed(colour=member.color)
            em.add_field(name='Full Name:', value=f'{user.name}#{user.discriminator}', inline=False)
            em.add_field(name='ID:', value=f'{user.id}', inline=False)
            em.add_field(name='Joined On:', value='{} ({} ago)'.format(member.joined_at.strftime('%c'), strfdelta(datetime.utcnow() - member.joined_at)), inline=False)
            em.add_field(name='Created On:', value='{} ({} ago)'.format(user.created_at.strftime('%c'), strfdelta(datetime.utcnow() - user.created_at)), inline=False)
            member_search = await self.do_search(guild_id=guild.id, author_id=user.id)
            em.add_field(name='Messages in Server:', value='{}'.format(member_search["total_results"]), inline=False)
            em.add_field(name='Voice Channel Activity:', value=f'{vc_string}', inline=False)
            em.add_field(name='Roles:', value='{}'.format(', '.join([f'<@&{role.id}>' for role in member.roles])), inline=False)
            member_profile = await self.get_profile(member.id)
            em.add_field(name='Nitro Since:', value='{} ({} ago)'.format(member_profile.premium_since, strfdelta(datetime.utcnow() - member_profile.premium_since)) if member_profile.premium else '-Not Subscribed-', inline=False)
            if member_profile.hypesquad: 
                em.add_field(name='User In HypeSquad', value='<:r6hype:543089542870073345> ', inline=True)
            if member_profile.partner: 
                em.add_field(name='User Is a Partner', value='<:r6partner:543089545923788800>', inline=True)
            if member_profile.staff: 
                em.add_field(name='User Is Staff', value='<:r6staff:543089549992263680>', inline=True)
            connection_txt = '\n'.join(['{}{}: {}'.format('{}'.format(con['type']).rjust(9), '\u2705' if con['verified'] else '\U0001F6AB', con["name"]) for con in member_profile.connected_accounts])
            if not connection_txt:
                connection_txt = 'None'
            em.add_field(name='Connections:', value='```{}```'.format(connection_txt), inline=False)
            
            em.set_author(name='%s AKA %s' % (member.nick, user.name), icon_url='https://i.imgur.com/FSGlsOR.png')
        else:
            em = discord.Embed(colour=discord.Colour(0xFFFF00))
            em.add_field(name='Full Name:', value=f'{user.name}', inline=False)
            em.add_field(name='ID:', value=f'{user.id}', inline=False)
            em.add_field(name='Created On:', value='{} ({} ago)'.format(user.created_at.strftime('%c'), strfdelta(datetime.utcnow() - user.created_at)), inline=False)
            em.set_author(name=user.name, icon_url='https://i.imgur.com/FSGlsOR.png')
            member_search = await self.do_search(guild_id=guild.id, author_id=user.id)
            em.add_field(name='Messages in Server:', value='{}'.format(member_search["total_results"]), inline=False)
            em.add_field(name='Voice Channel Activity:', value=f'{vc_string}', inline=False)
            try:
                bans = await guild.get_ban(user)
                reason = bans.reason
                em.add_field(name='User Banned from Server:', value=f'Reason: {reason}', inline=False)
            except discord.NotFound:
                pass
                
        em.set_thumbnail(url=user.avatar_url)
        await self.safe_send_message(channel, embed=em)
        
    async def on_reaction_add(self, reaction, member):
        if not self.use_reactions: return
        if member.id == self.user.id:
            return
        if reaction.message.channel.id in [CHANS['drama']]:
            user = discord.utils.get(reaction.message.guild.members, id=self.watched_messages[reaction.message.id]['author_id'])
            if ROLES['staff'] in [role.id for role in user.roles]: 
                await self.safe_delete_message(reaction.message)
                return
            matched_content = self.watched_messages[reaction.message.id]['matched_content']
            channel = self.get_channel(self.watched_messages[reaction.message.id]['channel_id'])
            if reaction.emoji.id == REACTS['delete']:
                await self.safe_delete_message(await self.get_channel(self.watched_messages[reaction.message.id]['channel_id']).get_message(self.watched_messages[reaction.message.id]['message_id']))
            if reaction.emoji.id == REACTS['mute']:
                if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await self.safe_send_message(self.get_channel(CHANS['staff_bot']), content=f'!mute {user.id} --mod={member.id} User said `{matched_content}` in {channel.mention}')
            if reaction.emoji.id == REACTS['24mute']:
                if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await self.safe_send_message(self.get_channel(CHANS['staff_bot']), content=f'!mute {user.id} --mod={member.id} User said `{matched_content}` in {channel.mention}')
            if reaction.emoji.id == REACTS['48mute']:
                if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await self.safe_send_message(self.get_channel(CHANS['staff_bot']), content=f'!mute {user.id} --mod={member.id} User said `{matched_content}` in {channel.mention}')
            if reaction.emoji.id == REACTS['ban']:
                if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await self.safe_send_message(self.get_channel(CHANS['staff_bot']), content=f'!ban {user.id} --mod={member.id} User said `{matched_content}` in {channel.mention}')
            if reaction.emoji.id == REACTS['check']:
                await self.safe_delete_message(reaction.message)

                            
    async def on_member_join(self, member):
        if member.guild.id == SERVERS['ban']: return
        updated_member_roles = []
        for role_id in self.channel_bans:
            if member.id in self.channel_bans[role_id]:
                if self.channel_bans[role_id][member.id]:
                    asyncio.ensure_future(self.queue_timed_ban_role(self.channel_bans[role_id][member.id], user, None, role_id, user.id))
                updated_member_roles = updated_member_roles + [discord.utils.get(member.guild.roles, id=role_id)]
                
        if updated_member_roles:
            if not ROLES['staff'] in [role.id for role in member.roles]:
                await member.edit(roles = updated_member_roles)
                        
    async def on_member_update(self, before, after):
        if before.guild.id == SERVERS['ban']: return
        
        new_roles = [role for role in discord.utils.get(self.guilds, id=SERVERS['main']).roles if role.name.startswith('Ban') and role.id not in self.channel_bans]
        if new_roles:
            print('Found %s new roles!' % len(new_roles))
            for role in new_roles:
                self.channel_bans[role.id] = {member.id: None for member in discord.utils.get(self.guilds, id=SERVERS['main']).members if role in member.roles}
                write_json('channel_banned.json', self.channel_bans)
        if before.roles != after.roles:
            try:
                for role_id in self.channel_bans:
                    if not [role for role in before.roles if role.id == role_id] and [role for role in after.roles if role.id == role_id]:
                        self.channel_bans[role_id][before.id] = None
                        print('user {} now channel banned'.format(before.name))
                        write_json('channel_banned.json', self.channel_bans)
                    if [role for role in before.roles if role.id == role_id] and not [role for role in after.roles if role.id == role_id]:
                        self.channel_bans[role_id].pop(before.id, None)
                        print('user {} no longer channel banned'.format(before.name))
                        write_json('channel_banned.json', self.channel_bans)
            except:
                traceback.print_exc()
                pass

    async def on_message_edit(self, before, after):
        if before.author == self.user:
            return
        if before.guild.id == SERVERS['ban']: return
        await self.on_message(after, edit=True)
        
    async def on_guild_channel_delete(self, channel):
        if channel.guild.id == SERVERS['ban']: return
        if channel.category and self.vc_tracker[channel.category.id] and self.vc_tracker[channel.category.id][channel.id]:
            self.vc_tracker[channel.category.id].pop(channel.id, None)
            
    async def on_voice_state_update(self, member, before, after):
        if before != after:
            if not self.vc_ready: return
            if before and after and (before.channel == after.channel):
                return
            # LFG VC Tracking
            if (before and before.channel):
                if self.lfg_vc_debug: print(f"EVENT: tracking change in {before.channel.name}")
                if member.id in self.vc_num_locks:
                    await before.channel.edit(user_limit=3)
                    self.vc_num_locks.pop(member.id, None)
                        
                if before.channel.category in self.vc_categories.values():
                    if self.lfg_vc_debug: print(f"EVENT: found {before.channel.name} in tracked cat")
                    dt_now = datetime.utcnow()
                    if before.channel.id in self.vc_tracker[before.channel.category.id]:
                        self.vc_tracker[before.channel.category.id][before.channel.id]["last_event"] = dt_now
                        asyncio.ensure_future(self.vc_member_num_buffer(before.channel, dt_now, len(before.channel.members)))
                # else:
                    # if self.lfg_vc_debug: print(f"EVENT: {before.channel.name} not in tracked cat")
            if (after and after.channel):
                if self.lfg_vc_debug: print(f"EVENT: tracking change in {after.channel.name}")
                    
                if after.channel.category in self.vc_categories.values():
                    if self.lfg_vc_debug: print(f"EVENT: found {after.channel.name} in tracked cat")
                    dt_now = datetime.utcnow()
                    if after.channel.id in self.vc_tracker[after.channel.category.id]:
                        self.vc_tracker[after.channel.category.id][after.channel.id]["last_event"] = dt_now
                        asyncio.ensure_future(self.vc_member_num_buffer(after.channel, dt_now, len(after.channel.members)))
                # else:
                    # if self.lfg_vc_debug: print(f"EVENT: {after.channel.name} not in tracked cat")
            

    async def on_message(self, message, edit=False):
        if message.author == self.user or message.webhook_id:
            return
                

        if isinstance(message.channel, discord.abc.PrivateChannel):
            print('pm')
            return
        else:
            if message.guild.id == SERVERS['ban']: return
            if message.channel.id not in self.messages_log:
                self.messages_log[message.channel.id] = {message.id: {'content': message.content, 'author': message.author.id}}
            else:
                self.messages_log[message.channel.id][message.id] = {'content': message.content, 'author': message.author.id}
        try:
            this = [role for role in message.author.roles if role.id  in [ROLES['staff']]]
        except:
            try:
                message.author.roles = [role for role in message.author.roles if role is not None]
            except AttributeError as e:
                print(message.author.id)
                print(message.author.name)
                    
 
        if not message.author.bot and not [role for role in message.author.roles if role.id  in [ROLES['staff'], ROLES['submods'], ROLES['Respawn'], ROLES['modmail'], ROLES['zepp']]]:
            if message.channel.id == 542118959072280586:
                drama_matches = re.search(REGEX['drama2'], message.content, re.IGNORECASE)
            else:
                drama_matches = re.search(REGEX['drama'], message.content, re.IGNORECASE)
            dox_matches = re.search(REGEX['dox'], message.content, re.IGNORECASE)
            matched_content = None
            sent_msg = None
            if message.id in [self.watched_messages[msg]['message_id'] for msg in self.watched_messages]:
                if not drama_matches and not dox_matches:
                    await self.safe_send_message(self.get_channel(CHANS['drama']), content='{}#{} has edited away the past potentially drama inducing item'.format(message.author.name, message.author.discriminator))
                else:
                    for msg_id, msg_dict in self.watched_messages.items():
                        if msg_dict['message_id'] == message.id:
                            await self.safe_delete_message(await (self.get_channel(460798145236959232)).get_message(msg_id))
            if drama_matches:
                em = discord.Embed(description=f"**Potential Drama found in {message.channel.mention}** - [Click Here]({message.jump_url}) to jump", colour=discord.Colour(0xffff00), timestamp=datetime.utcnow())
                em.set_author(name="𝅳𝅳𝅳", icon_url="https://i.imgur.com/TVlATNp.png")
                async for msg in message.channel.history(limit=4, before=message, reverse=True):
                    em.add_field(name="~~                    ~~", value='**%s**:\n%s' % (msg.author.mention, msg.content), inline=False)
                msg_value = message.content[:drama_matches.start()] + '**__' + message.content[drama_matches.start():drama_matches.end()] + '__**' + message.content[drama_matches.end():]
                em.add_field(name="~~                    ~~", value='**%s**:\n%s' % (message.author.mention, msg_value), inline=False)
                matched_content = message.content[drama_matches.start():drama_matches.end()]
                sent_msg = await self.safe_send_message(self.get_channel(CHANS['drama']), embed=em)
            if dox_matches:
                em = discord.Embed(ddescription=f"**Potential DOXXING found in {message.channel.mention}** - [Click Here]({message.jump_url}) to jump", colour=discord.Colour(0xff0000), timestamp=datetime.utcnow())
                em.set_author(name="𝅳𝅳𝅳", icon_url="https://i.imgur.com/ozWtGXL.png")
                async for msg in message.channel.history(limit=4, before=message, reverse=True):
                    em.add_field(name="~~                    ~~", value='**%s**:\n%s' % (msg.author.mention, msg.content), inline=False)
                msg_value = message.content[:dox_matches.start()] + '**__' + message.content[dox_matches.start():dox_matches.end()] + '__**' + message.content[dox_matches.end():]
                em.add_field(name="~~                    ~~", value='**%s**:\n%s' % (message.author.mention, msg_value), inline=False)
                matched_content = message.content[dox_matches.start():dox_matches.end()]
                sent_msg = await self.safe_send_message(self.get_channel(CHANS['drama']), embed=em)
            if sent_msg:
                self.watched_messages[sent_msg.id] = {'author_id': message.author.id, 'message_id': message.id, 'channel_id': message.channel.id, 'matched_content': matched_content}
                reactions = [emote for emote in self.emojis if emote.id in [REACTS['delete'], REACTS['mute'],REACTS['24mute'], REACTS['48mute'], REACTS['ban'], REACTS['check']]]
                for reaction in reactions:
                    await asyncio.sleep(1)
                    await sent_msg.add_reaction(reaction)
            
        message_content = message.content.strip()
        
        if [role for role in message.author.roles if role.id == ROLES['muted']]:
            return
        
        if not [prefix for prefix in self.prefix_aliases if message_content.startswith(prefix)] or edit:
            return
        try:
            command, *args = shlex.split(message.content.strip())
            command, *raw_args = message.content.strip().split()
        except:
            command, *args = message.content.strip().split()
            command, *raw_args = message.content.strip().split()
            
        prefix = max([prefix for prefix in self.prefix_aliases if message_content.startswith(prefix)], key=len)
        command = command[len(prefix):].lower().strip()
        
        
        handler = getattr(self, 'cmd_%s' % command, None)
        if not handler:
            if prefix == self.prefix:
                tag_name = message.content.strip()[len(prefix):].lower()
                if tag_name in self.tags:
                    if self.tags[tag_name][0]:
                        if self.tags[tag_name][0] == 'unrestricted_eval':
                            resp = await self.cmd_eval(message.author, message.guild, message, message.channel, message.mentions, self.tags[tag_name][1], is_origin_tag=True)
                            if resp:
                                await self.safe_send_message(message.channel, content=clean_bad_pings(resp))
                        elif not [role for role in message.author.roles if role.id  in [ROLES['staff']]]:
                            await self.safe_send_message(message.channel, content='Tag cannot be used by nonstaff members')
                            print("[Command] {0.id}/{0.name} ({1})".format(message.author, message_content))
                            return
                        elif self.tags[tag_name][0] == 'eval':
                            resp = await self.cmd_eval(message.author, message.guild, message, message.channel, message.mentions, self.tags[tag_name][1], is_origin_tag=True)
                            if resp:
                                await self.safe_send_message(message.channel, content=clean_bad_pings(resp))
                    else:
                        await self.safe_send_message(message.channel, content=clean_bad_pings(self.tags[tag_name][1]))
                            
                    print("[Command] {0.id}/{0.name} ({1})".format(message.author, message_content))
            return

        print("[Command] {0.id}/{0.name} ({1})".format(message.author, message_content))

        argspec = inspect.signature(handler)
        params = argspec.parameters.copy()

        # noinspection PyBroadException
        try:
            handler_kwargs = {}
            if params.pop('message', None):
                handler_kwargs['message'] = message

            if params.pop('channel', None):
                handler_kwargs['channel'] = message.channel

            if params.pop('author', None):
                handler_kwargs['author'] = message.author

            if params.pop('guild', None):
                handler_kwargs['guild'] = message.guild

            if params.pop('mentions', None):
                handler_kwargs['mentions'] = message.mentions

            if params.pop('channel_mentions', None):
                handler_kwargs['channel_mentions'] = message.channel_mentions

            if params.pop('leftover_args', None):
                            handler_kwargs['leftover_args'] = args

            if params.pop('raw_leftover_args', None):
                            handler_kwargs['raw_leftover_args'] = raw_args

            if params.pop('eval_content', None):
                            handler_kwargs['eval_content'] = message.content
                            
            args_expected = []
            for key, param in list(params.items()):
                doc_key = '[%s=%s]' % (key, param.default) if param.default is not inspect.Parameter.empty else key
                args_expected.append(doc_key)

                if not args and param.default is not inspect.Parameter.empty:
                    params.pop(key)
                    continue

                if args:
                    arg_value = args.pop(0)
                    if arg_value.startswith('<@') or arg_value.startswith('<#'):
                        pass
                    else:
                        handler_kwargs[key] = arg_value
                        params.pop(key)

            if params:
                docs = getattr(handler, '__doc__', None)
                if not docs:
                    docs = 'Usage: {}{} {}'.format(
                        self.prefix,
                        command,
                        ' '.join(args_expected)
                    )

                docs = '\n'.join(l.strip() for l in docs.split('\n'))
                await self.safe_send_message(
                    message.channel,
                    content= '```\n%s\n```' % docs.format(command_prefix=self.prefix),
                             expire_in=15
                )
                return

            response = await handler(**handler_kwargs)
            if response and isinstance(response, Response):
                content = response.content
                if response.reply:
                    content = '%s, %s' % (message.author.mention, content)
                    
                if response.delete_after > 0:
                    await self.safe_delete_message(message)
                    sentmsg = await self.safe_send_message(message.channel, content=content, expire_in=response.delete_after)
                else:
                    sentmsg = await self.safe_send_message(message.channel, content=content)
                    
        except CommandError as e:
            await self.safe_send_message(message.channel, content='```\n%s\n```' % e.message, expire_in=15)

        except:
            await self.safe_send_message(message.channel, content='```\n%s\n```' % traceback.format_exc(), expire_in=60)
            traceback.print_exc()

if __name__ == '__main__':
    bot = ApexBot()
    bot.run()
