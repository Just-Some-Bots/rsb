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
from io import BytesIO, StringIO
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from timeit import default_timer as timer
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .constants import *
from .exceptions import CommandError
from discord.http import HTTPClient, Route
from .creds import BOT_TOKEN, TWITCH_CREDS, USER_TOKEN
from .utils import doc_string, cleanup_code, cleanup_blocks, clean_string, write_json, load_json, clean_bad_pings, datetime_to_utc_ts, timestamp_to_seconds, strfdelta, _get_variable, snowflake_time, MemberConverter, UserConverter

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



class Response(object):
    def __init__(self, content, reply=False, delete_after=0, delete_invoking=False):
        self.content = content
        self.reply = reply
        self.delete_after = delete_after
        self.delete_invoking = delete_invoking

class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeError(message)

class R6Bot(discord.Client):
    def __init__(self):
        super().__init__(max_messages=50000, fetch_offline_members=True)
        # Auth Related 
        self.prefix = '!'
        self.token = BOT_TOKEN
        self.user_token = USER_TOKEN
        self.twitch_client_id = TWITCH_CREDS
        
        # Local JSON Storage
        self.messages_log = {}
        self.tags = load_json('tags.json')
        self.tagblacklist = load_json('tagbl.json')
        self.serious_d_blacklist = load_json('sd_bl.json')
        self.extra_drama_kwords = load_json('dramakwords.json')
        self.guild_whitelist = load_json('server_whitelist.json')
        self.twitch_watch_list = load_json('twitchwatchlist.json')
        self.muted_dict = {int(key): value for key, value in load_json('muted.json').items()}
        self.mod_mail_db = {int(key): value for key, value in load_json('modmaildb.json').items()}
        self.channel_bans = {int(key): {int(k): v for k, v in value.items()} if value else value for key, value in load_json('channel_banned.json').items()}
        self.cban_role_aliases = {key: int(value) for key, value in load_json('cbanrolealiases.json').items()}
        
        # Instance Storage (nothing saved between bot reboots)
        self.ban_list = {}
        self.voice_changes = {}
        self.twitch_is_live = {}
        self.slow_mode_dict = {}
        self.last_actions = {}
        self.vc_num_locks = {}
        self.watched_messages = {}
        self.anti_stupid_modmail_list = []
        self.anti_spam_modmail_list = {}
        self.mention_spam_watch = {}
        REGEX['drama'] = REGEX['drama_base'].format('|'.join(self.extra_drama_kwords))
        self.server_status = {'PC': 'online', 'XBOXONE': 'online', 'PS4': 'online', 'timestamp': None}
        
        # Variables used as storage of information between commands
        self._last_result = None
        self.divider_content = ''
        self.last_modmail_msg = None
        self.last_modmail_poster = None
        self.role_ping_toggle = {'server': None,
                                 'game': None}
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        # Used to make RESTful calls using the User Token.
        self.user_http = HTTPClient(None, proxy=None, proxy_auth=None, loop=asyncio.get_event_loop())
        
        # Debug Garbage / work arounds for bugs I saw.
        self.twitch_debug = True
        self.slow_mode_debug = False
        self.ready_check = False
        self.use_reactions = True
        self.use_new_modmail = False
        self.debug_status_check = False
        
        # I separated these out from Constants because I wanted to ensure they could be easily found and changed.
        self.intro_msg = "Welcome to the official Rainbow6 Discord server, make sure to read <#{rules}>! You will need a role in order to chat and join voice channels. To obtain a role *(take note of the exclamation mark prefix)*:```!pc\n!xbox\n!ps4``` If you happen to run a Youtube or Twitch  channel w/ over 15k followers or work at Ubisoft, dm me (the bot) about it and the admins will get you set up with a fancy role!".format(rules=CHANS['rules'])
        self.dm_msg = "Hello and welcome to the official Rainbow6 Discord!\nPlease take a moment to review the rules in <#{rules}> and don't forget to assign yourself a role in <#{roleswap}> as you cannot use the text / voice channels until you do, if you have any further questions, simply message this bot back to send a mod mail to the server staff!".format(rules=CHANS['rules'], roleswap=CHANS['roleswap'])
        
        #scheduler garbage
        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(self.backup_messages_log, 'cron', id='backup_msgs',  minute='*/10')
        self.scheduler.add_job(self.get_siege_server_status, 'cron', id='get_siege_server_status',  second ='*/10')
        self.scheduler.add_job(self.do_server_summary_month, 'cron', id='month_summary', day='1', hour='15')
        self.scheduler.add_job(self.remind_for_roles, 'cron', id='remind_for_roles', day='1-30/3', hour='19')
        self.scheduler.add_job(self.do_server_summary_week, 'cron', id='week_summary', day_of_week='0', hour='15')
        self.scheduler.start()
        print('past init')

    # noinspection PyMethodOverriding
    def run(self):
        loop = asyncio.get_event_loop()
        try:
            loop.create_task(self.mod_mail_reminders())
            loop.create_task(self.check_twitch_streams())
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
        self.channel_bans[role_id].pop(user_id, None)
        write_json('channel_banned.json', self.channel_bans)
        try:
            if not user or isinstance(user, discord.User):
                user = discord.utils.get(self.guilds, id=SERVERS['main']).get_member(user_id)
                if not user:
                    return
                
            if not timed_role:
                timed_role = discord.utils.get(discord.utils.get(self.guilds, id=SERVERS['main']).roles, id=role_id)
            if timed_role in user.roles:
                if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await user.remove_roles(timed_role, atomic = True)
        except:
            traceback.print_exc()
            
    async def queue_timed_mute(self, sec_time, user, timed_role, user_id):
        await asyncio.sleep(sec_time)
        if self.muted_dict[user_id]:
            datetime_timestamp = datetime.fromtimestamp(self.muted_dict[user_id])
            if datetime.utcnow() < datetime_timestamp:
                return
                print('Mute extended for {} for {} more seconds'.format(user.name if user != None else user_id, (datetime_timestamp - datetime.utcnow()).total_seconds()))
        else:
            return
            
        self.muted_dict.pop(user_id, None)
        write_json('muted.json', self.muted_dict)
        try:
            if not user or isinstance(user, discord.User):
                user = discord.utils.get(self.guilds, id=SERVERS['main']).get_member(user_id)
                if not user:
                    return
                    
            if timed_role in user.roles:
                if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await user.remove_roles(timed_role, atomic = True)
                em = discord.Embed(colour=discord.Colour(0xFFD800), description=MUTED_MESSAGES['timed_over'].format(roles=CHANS['roleswap'], rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(user, embed=em)
                await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=user.mention, id=user.id, reason='as they were unmuted'))
                try:
                    await user.edit(mute=False)
                except:
                    pass
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
        file = discord.File("/home/bots/r6botrw/img.png", filename="img.png")
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
        
    async def remind_for_roles(self):
        target_channel = self.get_channel(CHANS['rolereminder'])
        async for message in target_channel.history(limit=5):
            await self.safe_delete_message(message)
        await self.safe_send_message(target_channel, content=f"@everyone\nHello and welcome to the official Rainbow6 Discord!\nPlease take a moment to review the rules in <#{CHANS['rules']}> and don't forget to assign yourself a role by pressing any of the platform (PC, Xbox or PS4) emojis in <#{CHANS['roleswap']}>!\nDo bear in mind that role assignment will not function until the 10 minute join timer has expired.\nIf you have any further questions, simply DM me(<@!{self.user.id}>). to get in contact with staff!")
        
    async def do_server_summary_month(self):
        await self.user_http.send_message(CHANS['servermetrics'], '%serversummary month')
            
        
    async def do_server_summary_week(self):
        await self.user_http.send_message(CHANS['servermetrics'], '%serversummary week')
            
    async def wait_until_really_ready(self):
        while not self.ready_check:
            await asyncio.sleep(1)
            
    async def mod_mail_reminders(self):
        while True:
            ticker = 0
            while ticker != 1800:
                await asyncio.sleep(1)
                if not [member_id for member_id in self.mod_mail_db if not self.mod_mail_db[member_id]['answered']]:
                    ticker = 0
                else:
                    ticker+=1
            try:
                async for lmsg in self.get_channel(CHANS['staff']).history(limit=1):
                        if self.last_modmail_msg and lmsg.id == self.last_modmail_msg.id:
                            await self.safe_edit_message(lmsg, content='There are **{}** unread items in the mod mail queue that\'re over a half hour old! Either run `!mmqueue` to see them and reply or mark them read using `!markread`!'.format(len([member_id for member_id in self.mod_mail_db if not self.mod_mail_db[member_id]['answered']])))
                        else:
                            if self.last_modmail_msg:
                                await self.safe_delete_message(self.last_modmail_msg)
                            self.last_modmail_msg = await self.safe_send_message(self.get_channel(CHANS['staff']), content='There are **{}** unread items in the mod mail queue that\'re over a half hour old! Either run `!mmqueue` to see them and reply or mark them read using `!markread`!'.format(len([member_id for member_id in self.mod_mail_db if not self.mod_mail_db[member_id]['answered']])))
            except:
                print('something broke in mod mail, just gonna print this I guess')
            
    async def get_siege_server_status(self):
        async with aiohttp.ClientSession() as sess:
            async with sess.get(R6_STATUS_URL) as r:
                data = await r.json()
                self.server_status['timestamp'] = datetime.utcnow()
                for platform_data in data:
                    platform = platform_data['Platform']
                    status = platform_data['Status'].lower()
                    maintenance = platform_data['Maintenance']
                    if self.debug_status_check: print(f"[{platform}] {status} / {maintenance}")
                    if maintenance:
                        self.server_status[platform] = 'maintenance'
                    else:
                        if status == 'online':
                            self.server_status[platform] = 'online'
                        elif status == 'interrupted':
                            self.server_status[platform] = 'interrupted'
                        elif status == 'degraded':
                            self.server_status[platform] = 'degraded'
                    
            
            
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
                        if resp and "stream" in resp and resp["stream"] and resp["stream"]["game"] == 'Tom Clancy\'s Rainbow Six: Siege':
                            if streamer in ['rainbow6']:
                                target_channel = 414812315729526784
                            else:
                                target_channel = CHANS['twitch']
                            if streamer not in self.twitch_is_live:
                                if self.twitch_debug: print('Creating new embed for user %s' % streamer)
                                self.twitch_is_live[streamer] = {'detected_start': datetime.utcnow(),
                                                                 'view_count_updated': datetime.utcnow(),
                                                                 'offline_cooldown': False,
                                                                 'embedded_object': await self.generate_streaming_embed(resp, streamer),
                                                                 'message': None}
                                self.twitch_is_live[streamer]['message'] = await self.safe_send_message(self.get_channel(target_channel), embed=self.twitch_is_live[streamer]['embedded_object'], file=discord.File("/home/bots/r6botrw/img.png", filename="img.png"))
                            else:
                                if datetime.utcnow() - timedelta(minutes=15) > self.twitch_is_live[streamer]['detected_start']:
                                    if self.twitch_debug: print('Recreating new embed for user %s' % streamer)
                                    await self.safe_delete_message(self.twitch_is_live[streamer]['message'])
                                    self.twitch_is_live[streamer] = {'detected_start': datetime.utcnow(),
                                                                     'view_count_updated': datetime.utcnow(),
                                                                     'offline_cooldown': False,
                                                                     'embedded_object': await self.generate_streaming_embed(resp, streamer),
                                                                     'message': None}
                                    self.twitch_is_live[streamer]['message'] = await self.safe_send_message(self.get_channel(target_channel), embed=self.twitch_is_live[streamer]['embedded_object'], file=discord.File("/home/bots/r6botrw/img.png", filename="img.png"))
                                elif datetime.utcnow() - timedelta(minutes=5) > self.twitch_is_live[streamer]['view_count_updated']:
                                    if self.twitch_debug: print('Updating embeds view count for user %s' % streamer)
                                    self.twitch_is_live[streamer]['embedded_object'] = await self.generate_streaming_embed(resp, streamer)
                                    self.twitch_is_live[streamer]['view_count_updated'] = datetime.utcnow()
                                    await self.safe_edit_message(self.twitch_is_live[streamer]['message'], embed=self.twitch_is_live[streamer]['embedded_object'])
                                    
                        elif streamer in self.twitch_is_live and not self.twitch_is_live[streamer]['offline_cooldown']:
                            if self.twitch_debug: print('User %s detected offline, marking as such' % streamer)
                            self.twitch_is_live[streamer]['embedded_object'].color = discord.Colour(0x979c9f)
                            self.twitch_is_live[streamer]['embedded_object'].set_field_at(0, name="Status", value="OFFLINE", inline=True)
                            self.twitch_is_live[streamer]['offline_cooldown'] = True
                            await self.safe_edit_message(self.twitch_is_live[streamer]['message'], embed=self.twitch_is_live[streamer]['embedded_object'])
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
        print('Done!\n\nClearing Bans from Muted Dict...')
        target_server = discord.utils.get(self.guilds, id=SERVERS['main'])
        ban_list = await target_server.bans()
        temp_dict = [user_id for user_id in self.muted_dict.keys() if discord.utils.find(lambda u: u.user.id == user_id, ban_list)]
        for user_id in temp_dict:
            del self.muted_dict[user_id]
        write_json('muted.json', self.muted_dict)

        print('Done!\n\nDeserializing Mutes...')
        mutedrole = discord.utils.get(target_server.roles, id=ROLES['muted'])
        temp_dict = dict({user_id: timestamp for user_id, timestamp in self.muted_dict.items() if timestamp or target_server.get_member(user_id)})
        for user_id, timestamp in temp_dict.items():
            user = target_server.get_member(user_id)
            if timestamp:
                datetime_timestamp = datetime.fromtimestamp(timestamp)
                if datetime.utcnow() < datetime_timestamp:
                    asyncio.ensure_future(self.queue_timed_mute((datetime_timestamp-datetime.utcnow()).total_seconds(), user, mutedrole, user_id))
                    print('Queueing serialized mute for {} for {} seconds'.format(user.name if user != None else user_id, (datetime_timestamp - datetime.utcnow()).total_seconds()))
                else:
                    asyncio.ensure_future(self.queue_timed_mute(0, user, mutedrole, user_id))
                    print('Serialized mute period has passed for {}'.format(user.name if user != None else user_id))
                    continue
            else:
                print('Queueing serialized nontimed mute for {}'.format(user.name if user != None else user_id, ))
            if user:
                try:
                    if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: 
                        roles = set(([role for role in user.roles if role.id not in UNPROTECTED_ROLES] + [mutedrole]))
                        if set(user.roles) != roles:
                            await user.edit(roles = list(roles))                    
                    try:
                        await user.edit(mute=True)
                    except:
                        pass
                except discord.Forbidden:
                    print('cannot add role to %s, permission error' % user.name)
                    
        # print('Done!\n\nClearing Bans from Channel Ban Dict...')
        # for role_id, user_blob in temp_dict.items():
            # temp_dict = [user_id for user_id in user_blob.keys() if discord.utils.find(lambda u: u.user.id == user_id, ban_list)]
            # for user_id in temp_dict:
                # del self.muted_dict[user_id]
        # write_json('muted.json', self.muted_dict)

        print('Done!\n\nDeserializing Channel Bans...')
        temp_dict = dict(self.channel_bans)
        temp_dict = dict({role_id: {user_id: timestamp for user_id, timestamp in user_blob.items() if timestamp or target_server.get_member(user_id)} for role_id, user_blob in self.channel_bans.items() if user_blob})
        for role_id, user_blob in temp_dict.items():
            cban_role = discord.utils.get(target_server.roles, id=role_id)
            if not user_blob: continue
            for user_id, timestamp in user_blob.items():
                user = target_server.get_member(user_id)
                if timestamp:
                    datetime_timestamp = datetime.fromtimestamp(timestamp)
                    if datetime.utcnow() < datetime_timestamp:
                        asyncio.ensure_future(self.queue_timed_ban_role((datetime_timestamp-datetime.utcnow()).total_seconds(), user, cban_role, role_id, user_id))
                        print('Queueing serialized cban for {} for {} seconds'.format(user.name if user != None else user_id, (datetime_timestamp - datetime.utcnow()).total_seconds()))
                    else:
                        asyncio.ensure_future(self.queue_timed_ban_role(0, user, cban_role, role_id, user_id))
                        print('Serialized cban period has passed for {}'.format(user.name if user != None else user_id))
                        continue
                else:
                    print('Queueing serialized nontimed cban for {}'.format(user.name if user != None else user_id, ))
                if user:
                    try:
                        if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: 
                            if cban_role not in user.roles:
                                await user.add_roles(cban_role)
                    except discord.Forbidden:
                        print('cannot add role to %s, permission error' % user.name)
                    # try:
                        # if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await user.edit(roles = list())
                    # except discord.Forbidden:
                        # print('cannot add role to %s, permission error' % user.name)

        
        print('Done!\n\nPopulating Message Logs...')
        self.messages_log  = self.load_channel_logs()
        # print('Done!\n\nCacheing Avatars...')
        # for member in discord.utils.get(self.guilds, id=SERVERS['main']).members:
            # if '{}.gif'.format(member.id) not in [files for root, dirs, files in os.walk('avatars', topdown=False)]:
                # async with aiohttp.ClientSession() as sess:
                    # avatar_url = member.avatar_url
                    # if '.webp' in avatar_url:
                        # ffmpeg.input(avatar_url).output("avatars/{}.gif".format(member.id)).overwrite_output().run(cmd='ffmpeg', loglevel ='-8')
                    # else:
                        # async with sess.get(avatar_url) as r:
                            # data = await r.read()
                            # with open("avatars/{}.gif".format(member.id), "wb") as f:
                                # f.write(data)
        print('Done!\n\nAppending Missed Mutes...')
        muted_coffee_filter = [member for member in discord.utils.get(self.guilds, id=SERVERS['main']).members if mutedrole in member.roles and member.id not in self.muted_dict]
        for member in muted_coffee_filter:
            self.muted_dict[member.id] = None
        write_json('muted.json', self.muted_dict)
        print('Done!')
        
        await self.change_presence(activity=discord.Game(name='DM to contact staff!'))
        await self.safe_send_message(self.get_channel(CHANS['staff']), content='I have just been rebooted!')
        
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
                msg = await self.safe_send_message(message.channel, content=content)
        finally:
            if msg: return msg
            
    def mods_only(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            is_tag = _get_variable('tag_name')
            orig_msg = _get_variable('message')

            if [role for role in orig_msg.author.roles if role.id  in [ROLES['staff']]] or (is_tag and (self.tags[is_tag][0] == 'unrestricted_eval' or [role for role in orig_msg.author.roles if role.id  in [ROLES['tagmaster'], ROLES['staff']]])):
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
        if author.voice and author.voice.channel and author.voice.channel.name.lower().startswith(("[na", "[eu", "[latam", "[apac")):
            if author.id not in self.vc_num_locks:
                if author.voice.channel.id not in list(self.vc_num_locks.values()) and len(author.voice.channel.members) > 1:
                    await author.voice.channel.edit(user_limit=len(author.voice.channel.members))
                    self.vc_num_locks[author.id] = author.voice.channel.id
                    await self.safe_delete_message(message)
                    return Response(':thumbsup:', reply=True, delete_after=3, delete_invoking=True)
            else:
                await author.voice.channel.edit(user_limit=5)
                self.vc_num_locks.pop(author.id, None)
                await self.safe_delete_message(message)
                return Response(':thumbsup:', reply=True, delete_after=3, delete_invoking=True)
        return
 
    @mods_only
    async def cmd_whitelistserver(self, author, server_id):
        """
        Usage: {command_prefix}whitelistserver server_id
        Adds a server's id to the whitelist!
        """
        if server_id not in self.guild_whitelist:
            self.guild_whitelist.append(int(server_id))
            write_json('server_whitelist.json', self.guild_whitelist)
            return Response(':thumbsup:', reply=True)
        
    @mods_only
    async def cmd_restart(self, channel, author):
        """
        Usage: {command_prefix}restart
        Forces a restart
        """
        await self.safe_send_message(channel, content="Restarting....")
        await self.logout()

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

    async def cmd_clear(self, message, author, channel):
        """
        Usage {command_prefix}clear
        Removes all removable roles from a user.
        """
        author_roles = author.roles
        mod_check = [role for role in author_roles if role.id not in UNPROTECTED_ROLES]
        
        if mod_check:
            for roles in author.roles:
                if roles.id in UNPROTECTED_ROLES and not roles.is_everyone:
                    author_roles.remove(roles)
        else:
            author_roles = []
        if not ROLES['staff'] in [role.id for role in author.roles]: await author.edit(roles = author_roles)
        return Response('I\'ve removed all platform roles from you!', reply=True, delete_after=15, delete_invoking=True)
    
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
            traceback.print_exc()
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
                if is_origin_tag == False:
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
                    else:
                        flags = leftover_args[0].split()
                        final_args = []
                        eval_override = False
                        for flag in flags:
                            if flag.isdigit() and guild.get_channel(int(flag)):
                                final_args.append(flag)
                            elif flag == 'restrict':
                                final_args.append(flag)
                            elif flag == 'image':
                                eval_content = f"```\nem = discord.Embed(colour=discord.Colour(0x36393F))\nem.set_image(url=\"{leftover_args[2]}\")\nawait self.safe_send_message(channel, embed=em)\n\n```"
                                if 'open' in flags:
                                    final_args.append('unrestricted_eval')
                                else:
                                    final_args.append('eval')
                                eval_override = True
                            elif flag == 'eval':
                                if 'open' in flags:
                                    final_args.append('unrestricted_eval')
                                else:
                                    final_args.append('eval')
                                eval_override = True
                        
                        if not final_args:
                            raise CommandError('Bad input')
                            
                        final_str = ' '.join(final_args)
                        if len(leftover_args[1]) > 200:
                            raise CommandError('Tag length too long')
                        self.tags[leftover_args[1].lower()] = [final_str, leftover_args[2] if not eval_override else cleanup_code(eval_content)]
                        write_json('tags.json', self.tags)
                        return Response('Tag \"%s\" created' % clean_bad_pings(leftover_args[1]), delete_after=15)
                        
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
                        return Response('User `{}` was blacklisted'.format(clean_bad_pings(user.name)), delete_after=20, delete_invoking=True)
            else:
                if [role for role in author.roles if role.id  in [ROLES['staff']]]:
                    try:
                        del self.tags[' '.join(leftover_args)]
                        write_json('tags.json', self.tags)
                        return Response('Tag \"%s\" removed' % clean_bad_pings(' '.join(leftover_args)), delete_after=10, delete_invoking=True)
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
                        tag_flags = self.tags[tag][0].split()
                        # Channel Restriction Parsing
                        acceptable_chans = []
                        for item in tag_flags:
                            if item.isdigit() and guild.get_channel(int(item)):
                                chan = guild.get_channel(int(item))
                                if isinstance(chan, discord.CategoryChannel):
                                    acceptable_chans = acceptable_chans + [cat_chan.id for cat_chan in chan.text_channels]
                                else:
                                    acceptable_chans.append((guild.get_channel(int(item))).id)
                        if channel.id not in acceptable_chans and len(acceptable_chans) > 0:
                            return Response(f'Tag cannot be used outside of {", ".join([f"<#{chan}>" for chan in acceptable_chans])}', delete_after=20)
                            
                        # Eval Checking
                        if "unrestricted_eval" in tag_flags:
                            resp = await self.cmd_eval(author, guild, message, channel, mentions, self.tags[tag][1], is_origin_tag=True)
                            if resp:
                                await self.safe_send_message(channel, content=clean_bad_pings(resp))
                            return
                        elif "restrict" in tag_flags and not [role for role in author.roles if role.id  in [ROLES['staff'], ROLES['tagmaster']]]:
                            return
                        elif "eval" in tag_flags:
                            resp = await self.cmd_eval(author, guild, message, channel, mentions, self.tags[tag][1], is_origin_tag=True)
                            if resp:
                                await self.safe_send_message(channel, content=clean_bad_pings(resp))
                            return
                    return Response(clean_bad_pings(self.tags[tag][1]))
            raise CommandError('Tag doesn\'t exist')
    
    async def cmd_id(self, message, author, guild):
        """
        Usage: {command_prefix}id
        Replies with the user who issued the command's ID
        """
        if message.channel.id != CHANS['genbotspam']:
            return
        return Response('Your ID is `{}`!'.format(author.id), reply=True)
    
    async def cmd_staff(self, message, channel, author, guild):
        """
        Usage: {command_prefix}staff
        Prompts the user to ensure that the staff ping is really what they wanna do
        implemented to cut down on unnecessary staff pings
        """
        check_msg = await self.safe_send_message(channel, content='Please remember to *only* tag staff for things that **absolutely** require **immediate** attention and can only be addressed by server administration.\n\nFor non-immediate topics, *please* send a private message to <@!278980093102260225> to send mod-mail to the administration.\n\nPlease react if you still wish to ping the staff')
        await check_msg.add_reaction('✅')
        def check(reaction, user):
            return user.id == author.id and reaction.message.id == check_msg.id and str(reaction.emoji) == '✅'
        try:
            reac, user = await self.wait_for('reaction_add', check=check, timeout=300.0)
        except asyncio.TimeoutError:
            return
        
        if str(reac.emoji) == '✅':
            role = discord.utils.get(guild.roles, id=ROLES['staff'])
            await role.edit(mentionable=True)
            mention_msg = await self.safe_send_message(channel, content='<@&{}>'.format(ROLES['staff']))
            await asyncio.sleep(1)
            await mention_msg.add_reaction('☑')
            await role.edit(mentionable=False)
        else:
            return
                
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
                        ).format(command_prefix=self.prefix),
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
    async def cmd_check(self, message, mentions, author, guild, leftover_args):
        """
        Usage: {command_prefix}check
        Checks if the user is in Serious Discussion Blacklist or not
        """
        user = None
        option = None
        if leftover_args:
            option = ' '.join(leftover_args)
        if mentions:
            user = mentions[0]
        else:
            if discord.utils.get(guild.members, name=option):
                user = discord.utils.get(guild.members, name=option)
            elif discord.utils.get(guild.members, id=option):
                user = discord.utils.get(guild.members, id=option)
            elif discord.utils.get(guild.members, nick=option):
                user = discord.utils.get(guild.members, nick=option)
            else:
                raise CommandError('Could not find user specified')
        if user.id in self.serious_d_blacklist:
            return Response('%s is Serious Discussion blacklisted!' % clean_bad_pings(user.name))
        else:
            return Response('%s is not Serious Discussion blacklisted!' % clean_bad_pings(user.name))

    @mods_only
    async def cmd_unwatch(self, author, leftover_args):
        """
        Usage {command_prefix}unwatch [regex word(s)]
        Removes the regex word from drama watcher
        """
        word = ' '.join(leftover_args)
        if word in self.extra_drama_kwords:
            self.extra_drama_kwords.remove(word)
            REGEX['drama'] = REGEX['drama_base'].format('|'.join(self.extra_drama_kwords))
            write_json('dramakwords.json', self.extra_drama_kwords)
            return Response(':thumbsup:')
        else:
            raise CommandError('ERROR: Word not in drama watcher')

    @mods_only
    async def cmd_watch(self, author, leftover_args):
        """
        Usage {command_prefix}watch [regex word(s)]
        Removes the regex word from drama watcher
        """
        word = ' '.join(leftover_args)
        self.extra_drama_kwords.append(word)
        REGEX['drama'] = REGEX['drama_base'].format('|'.join(self.extra_drama_kwords))
        write_json('dramakwords.json', self.extra_drama_kwords)
        return Response(':thumbsup:')

    @mods_only
    async def cmd_removestream(self, author, channel_name):
        """
        Usage {command_prefix}removestream [twitch channel name]
        Removes the stream from the checks for online streams
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
    async def cmd_markread(self, author, guild,  auth_id):
        """
        Usage {command_prefix}markread user_id
        Marks the modmail thread as read if no reply is necessary 
        """
        auth_id = int(auth_id)
        if auth_id in self.mod_mail_db:
            self.mod_mail_db[auth_id]['answered'] = True
            write_json('modmaildb.json', self.mod_mail_db)
            return Response(':thumbsup:')
        else:
            raise CommandError('ERROR: User ID not found in Mod Mail DB')
        
    @mods_only
    async def cmd_mmlogs(self, author, channel, guild, auth_id):
        """
        Usage {command_prefix}mmlogs user_id
        Generates paginated logs for the specified user
        """
        auth_id = int(auth_id)
        if auth_id not in self.mod_mail_db:
            raise CommandError('ERROR: User ID not found in Mod Mail DB')
        
        current_index = 0
        step = 20
        current_msg = None
        message_dict = collections.OrderedDict(sorted(self.mod_mail_db[auth_id]['messages'].items(), reverse=True))
        while True:
            
            quick_switch_dict = {}
            quick_switch_dict = {'embed': discord.Embed(), 'member_obj': await self.fetch_user(auth_id)}
            quick_switch_dict['embed'].set_author(name='{}({})'.format(quick_switch_dict['member_obj'].name, quick_switch_dict['member_obj'].id), icon_url=quick_switch_dict['member_obj'].avatar_url)
            od = collections.OrderedDict(islice(message_dict.items(),current_index, current_index+step))
            od = collections.OrderedDict(reversed(list(od.items())))
            total_length = sum([len(msg_dict['content']) for timestamp, msg_dict in od.items()])
            sub_per_msg = None if total_length < 6000 else ((total_length - 6000) / 20)
            for timestamp, msg_dict in od.items():
                user = None
                if msg_dict['modreply'] is not None:
                    try:
                        user = discord.utils.get(guild.members, id=msg_dict['modreply']).name
                    except:
                        user = await self.fetch_user(msg_dict['modreply'])
                        user = user.name
                else:
                    user = quick_switch_dict['member_obj'].name
                if sub_per_msg:
                    msg_dict['content'] = msg_dict['content'][:(2000 - sub_per_msg)] + '...'
                # if len(msg_dict['content']) > 1020:
                    # msg_dict['content'] = msg_dict['content'][:1020] + '...'
                quick_switch_dict['embed'].add_field(name='{} | *{}*'.format(user, datetime.utcfromtimestamp(float(timestamp)).strftime('%H:%M %d.%m.%y' )), value=msg_dict['content'], inline=False)
            if not current_msg:
                current_msg = await self.safe_send_message(channel, embed=quick_switch_dict['embed'])
            else:
                current_msg = await self.safe_edit_message(current_msg, embed=quick_switch_dict['embed'])
            
            if current_index != 0:
                await current_msg.add_reaction('⬅')
            await current_msg.add_reaction('ℹ')
            if (current_index+step) < len(message_dict):
                await current_msg.add_reaction('➡')
                
            def check(reaction, user):
                e = str(reaction.emoji)
                if user != self.user and reaction.message.id == current_msg.id:
                    return e.startswith(('⬅', '➡', 'ℹ'))
                else:
                    return False
            try:
                reac, user = await self.wait_for('reaction_add', check=check, timeout=300)
            except:
                return
            if str(reac.emoji) == 'ℹ':
                await self.safe_send_message(current_msg.channel, content=quick_switch_dict['member_obj'].id)
            elif str(reac.emoji) == '➡' and current_index != len(message_dict):
                current_index+=step
                await current_msg.remove_reaction(reac.emoji, user)
            elif str(reac.emoji) == '⬅' and current_index != 0:
                current_index-=step
                await current_msg.remove_reaction(reac.emoji, user)
            else:
                return
            await current_msg.clear_reactions()
        
    @mods_only
    async def cmd_mmqueue(self, author, channel, guild):
        """
        Usage {command_prefix}mmqueue
        Fetches the open mod mail threads with paginated emotes
        """
        unanswered_threads = [member_id for member_id in self.mod_mail_db if not self.mod_mail_db[member_id]['answered']]
        if not unanswered_threads:
            return Response('Everything is answered!')
        quick_switch_dict = {}
        for member_id in unanswered_threads:
            quick_switch_dict[member_id] = {'embed': discord.Embed(), 'member_obj': await self.fetch_user(member_id)}
            quick_switch_dict[member_id]['embed'].set_author(name='{}({})'.format(quick_switch_dict[member_id]['member_obj'].name, quick_switch_dict[member_id]['member_obj'].id), icon_url=quick_switch_dict[member_id]['member_obj'].avatar_url)
            od = collections.OrderedDict(sorted(self.mod_mail_db[member_id]['messages'].items(), reverse=True))
            od = collections.OrderedDict(islice(od.items(), 10))
            od = collections.OrderedDict(reversed(list(od.items())))
            for timestamp, msg_dict in od.items():
                user = None
                if msg_dict['modreply'] is not None:
                    user = (await self.fetch_user(msg_dict['modreply'])).name
                else:
                    user = quick_switch_dict[member_id]['member_obj'].name
                if len(str(msg_dict['content'])) > 1020:
                    msg_dict['content'] = str(msg_dict['content'])[:1020] + '...'
                if not msg_dict['content']:
                    msg_dict['content'] = "-Message has no content-"
                quick_switch_dict[member_id]['embed'].add_field(name='{} | *{}*'.format(user, datetime.utcfromtimestamp(float(timestamp)).strftime('%H:%M %d.%m.%y' )), value=msg_dict['content'], inline=False)
                
        current_index = 0
        current_msg = None
        loop_dict = list(collections.OrderedDict(quick_switch_dict.items()).values())
        while True:
            if current_index >= len(loop_dict):
                current_index = len(loop_dict)-1

            embed_object = loop_dict[current_index]['embed']
            embed_object.set_footer(text='{} / {}'.format(current_index+1, len(loop_dict)))
            
            if not current_msg: 
                current_msg = await self.safe_send_message(channel, embed=embed_object)
            else:
                current_msg = await self.safe_edit_message(current_msg, embed=embed_object)
            
            if current_index != 0:
                await current_msg.add_reaction('⬅')
            await current_msg.add_reaction('☑')
            await current_msg.add_reaction('ℹ')
            if (current_index+1) != len(loop_dict):
                await current_msg.add_reaction('➡')
                
            def check(reaction, user):
                e = str(reaction.emoji)
                if user != self.user and reaction.message.id == current_msg.id:
                    return e.startswith(('⬅', '➡',  'ℹ', '☑'))
                else:
                    return False
            try:
                reac, user = await self.wait_for('reaction_add', check=check, timeout=300)
            except:
                return
            if str(reac.emoji) == '☑':
                if not self.mod_mail_db[loop_dict[current_index]['member_obj'].id]['answered']:
                    self.mod_mail_db[loop_dict[current_index]['member_obj'].id]['answered'] = True
                    if current_index == len(loop_dict):
                        current_index-=1
                        del loop_dict[current_index+1]
                    else:
                        del loop_dict[current_index]
                    if len(loop_dict) == 0:
                        await self.safe_delete_message(current_msg)
                        await self.safe_send_message(current_msg.channel, content='Everything is answered!')
                        return
                    else:
                        await current_msg.remove_reaction(reac.emoji, user)
                else:
                    await self.safe_delete_message(current_msg)
                    await self.safe_send_message(current_msg.channel, content='Everything is answered!')
                    return
            elif str(reac.emoji) == 'ℹ':
                await self.safe_send_message(current_msg.channel, content=loop_dict[current_index]['member_obj'].id)
            elif str(reac.emoji) == '⬅' and current_index != 0:
                current_index-=1
                await current_msg.remove_reaction(reac.emoji, user)
            elif str(reac.emoji) == '➡' and current_index != len(loop_dict):
                current_index+=1
                await current_msg.remove_reaction(reac.emoji, user)
            else:
                return
            await current_msg.clear_reactions()
        
    @mods_only
    async def cmd_modmail(self, author, guild, raw_leftover_args):
        """
        Usage {command_prefix}modmail user_id "Message Content"
        Sends a DM to a user (whos ID is user_id)
        If this is a reply, it marks it as read
        If "anon" is the first word in "Message Content", it sends it without a staff username attached
        """
        if not raw_leftover_args:
            return Response(doc_string(inspect.getdoc(getattr(self, inspect.getframeinfo(inspect.currentframe()).function)), self.prefix))
        try:
            auth_id = int(raw_leftover_args.pop(0))
        except:
            raise CommandError('Not a valid ID, must be all numbers')
        member = discord.utils.get(guild.members, id=auth_id)
        if not member:
            member = discord.utils.get(discord.utils.get(self.guilds, id=SERVERS['ban']).members, id=auth_id)
        if member:
            if raw_leftover_args[0] == 'anon':
                msg_to_send = ' '.join(raw_leftover_args[1:])
                await self.safe_send_message(member, content='**Admins:** {}'.format(msg_to_send))
                if member.id in self.mod_mail_db:
                    self.mod_mail_db[member.id]['messages']['{}'.format(datetime_to_utc_ts(datetime.now()))] = {'content': '(ANON){}'.format(msg_to_send), 'modreply': author.id}
                    self.mod_mail_db[member.id]['answered'] = True
                else:
                    self.mod_mail_db[member.id] = {'answered': True, 'messages': {'{}'.format(datetime_to_utc_ts(datetime.now())): {'modreply': author.id,'content': '(ANON){}'.format(msg_to_send)}}}

            else:
                msg_to_send = ' '.join(raw_leftover_args)
                await self.safe_send_message(member, content='**{}:** {}'.format(author.name, msg_to_send))
                if member.id in self.mod_mail_db:
                    self.mod_mail_db[member.id]['messages']['{}'.format(datetime_to_utc_ts(datetime.now()))] = {'content': '{}'.format(msg_to_send), 'modreply': author.id}
                    self.mod_mail_db[member.id]['answered'] = True
                else:
                    self.mod_mail_db[member.id] = {'answered': True, 'messages': {'{}'.format(datetime_to_utc_ts(datetime.now())): {'modreply': author.id,'content': '{}'.format(msg_to_send)}}}
            write_json('modmaildb.json', self.mod_mail_db)
            return Response(':thumbsup: Send this to {}:```{}```'.format(member.name, msg_to_send))
        else:
            raise CommandError('ERROR: User not found')

    async def cmd_timeleft(self, author):
        """
        Usage {command_prefix}timeleft
        Tells muted people how long they have left in their mute
        """
        if ROLES['muted'] in [role.id for role in author.roles] and self.muted_dict[author.id]:
            return Response('You will be unmuted in %s' % strfdelta(datetime.fromtimestamp(self.muted_dict[author.id])- datetime.utcnow()))
        return
        
    @mods_only
    async def cmd_unmute(self, message, guild, author, mentions, raw_leftover_args):
        """
        Usage {command_prefix}unmute [@mention OR User ID] <time>
        Unmutes ppl
        """
        if not raw_leftover_args:
            return Response(doc_string(inspect.getdoc(getattr(self, inspect.getframeinfo(inspect.currentframe()).function)), self.prefix))
        converter = UserConverter()
        users = []
        
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
        
        for user in users:
            try:
                user = guild.get_member(user.id)
                if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await user.edit(roles = [role for role in user.roles if role.id not in UNPROTECTED_ROLES])
                try:
                    await user.edit(mute=False)
                except:
                    pass
                del self.muted_dict[user.id]
                write_json('muted.json', self.muted_dict)
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Unmuted user', reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                self.last_actions[author.id] = action_msg
                em = discord.Embed(colour=discord.Colour(0xFFD800), description=MUTED_MESSAGES['timed_over'].format(roles=CHANS['roleswap'], rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(user, embed=em)
                await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=user.mention, id=user.id, reason='as they were unmuted'))
            except discord.Forbidden:
                raise CommandError('Not enough permissions to mute user : {}'.format(user.name))
            except:
                traceback.print_exc()
                raise CommandError('Unable to mute user defined:\n{}\n'.format(user.name))
        return Response(':thumbsup:')

    @mods_only
    async def cmd_reason(self, message, guild, author, mentions, message_id, leftover_args):
        """
        Usage {command_prefix}reason [message_id] <reason text>
        Allows you to specify a reason for any action in the action log based on the message ID that was sent
        """
        msg_ids = message_id.strip().split()
        action_log = discord.utils.get(guild.channels, id=CHANS['actions'])
        no_id = False
        for msg_id in msg_ids:
            try:
                msg = await action_log.fetch_message(msg_id)
            except:
                if author.id in self.last_actions:
                    msg = self.last_actions[author.id]
                    leftover_args.insert(0, message_id)
                    no_id = True
                else:
                    traceback.print_exc()
                    raise CommandError(f"No Message ID found by ID {msg_id}")
            if msg.author.id != self.user.id:
                return Response(f"I cannot edit other people's messages. Please speak to {msg.author.mention} if you'd like to change their reason")
            reason = ' '.join(leftover_args)
            edited_content = cleanup_blocks(msg.content).strip().split('\n')[:2]
            match = re.search("\(Taken by (.*?)\)", edited_content[0])
            if match:
                edited_content[0] = edited_content[0][:(match.start(0)-1)]
            edited_content[0] = f"{edited_content[0]} (Taken by {author.name}#{author.discriminator})"
            edited_content = '\n'.join(edited_content)
            bonus_content = '' if not message.attachments else ', '.join([attch.url for attch in message.attachments])
            edited_content = f"```{edited_content}\nReason: {reason}\n```{bonus_content}"
            await self.safe_edit_message(msg, content=edited_content)
            if no_id:
                return Response(':thumbsup:')
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

                try:
                    await user.edit(mute=True)
                except:
                    pass
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
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Applied {} channel ban for {}'.format(role.name[4:], ' '.join(raw_leftover_args)), reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                self.last_actions[author.id] = action_msg
                em = discord.Embed(colour=discord.Colour(0xFF0000), description=CBAN_MESSAGES['timed'].format(cban_name=role.name[4:], time=' '.join(raw_leftover_args), rules=CHANS['rules']))
                await self.safe_send_message(user, embed=em)
                asyncio.ensure_future(self.queue_timed_ban_role(seconds_to_mute, user, role, role.id, user.id))
                response += ' channel banned for %s seconds' % seconds_to_mute
            else:
                self.channel_bans[role.id][user.id] = None
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Applied {} channel ban forever'.format(role.name[4:]), reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                self.last_actions[author.id] = action_msg
                em = discord.Embed(colour=discord.Colour(0xFF0000), description=CBAN_MESSAGES['plain'].format(cban_name=role.name[4:], rules=CHANS['rules']))
                await self.safe_send_message(user, embed=em)
            await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=user.mention, id=user.id, reason=f'as they were assigned {role.name}'))
        
        write_json('channel_banned.json', self.channel_bans)
        return Response(response) 
        

    @mods_only
    async def cmd_history(self, channel, message, guild, author, mentions, raw_leftover_args):
        """
        Usage {command_prefix}history [@mention OR User ID]
        Fetches the history for a user. As of right now, only queries the action-log
        """
        if not raw_leftover_args:
            return Response(doc_string(inspect.getdoc(getattr(self, inspect.getframeinfo(inspect.currentframe()).function)), self.prefix))
            
        converter = UserConverter()
        user = None
        if mentions:
            user = mentions[0]
                    
        else:
            try:
                user = await converter.convert(message, self, ' '.join(raw_leftover_args))
            except:
                traceback.print_exc()
        if not user:
            raise CommandError("Error: No user found")
        
        history_items = {}
        
        
        
        search_in_actions = (await self.do_search(guild_id=guild.id, channel_id=CHANS['actions'], content=user.id))['messages']
        for message_block in search_in_actions:
            for msg in message_block:
                if str(user.id) in msg["content"] and msg["id"] not in history_items:
                    history_items[msg["id"]] = {"content": cleanup_blocks(msg["content"]), "actor": discord.utils.get(guild.members, id=int(msg["author"]["id"]))}
        current_index = 0
        step = 10
        current_msg = None
        message_dict = collections.OrderedDict(sorted(history_items.items(), reverse=True))
        while True:
            
            quick_switch_dict = {'embed': discord.Embed(), 'member_obj': user}
            quick_switch_dict['embed'].set_author(name=f'{quick_switch_dict["member_obj"].name}({quick_switch_dict["member_obj"].id}) - {len(history_items)} {"result" if len(history_items)==1 else "results"}', icon_url=quick_switch_dict['member_obj'].avatar_url)
            quick_switch_dict['embed'].set_footer(text=f"{current_index} - {(current_index+step) if (current_index+step) < len(message_dict) else len(message_dict)}")

            od = collections.OrderedDict(islice(message_dict.items(),current_index, current_index+step))
            for ts_id, msg_block in od.items():
                fmt_msg = msg_block["content"].strip().split('\n')
                actor = msg_block["actor"]
                if not actor:
                    return CommandError("something is broke, poke rhino about it: actor not found in request via user bot")
                match = None
                if actor.bot:
                    match = re.search("\(Taken by (.*?)\)", fmt_msg[0])
                    if match:
                        actor = discord.utils.get(guild.members, name=match.group(1)[:-5], discriminator=match.group(1)[-4:])
                        if not actor:
                            actor = msg_block["actor"]
                acting_user_message = f"by {actor.mention}" if not actor.bot else f"by {actor.mention}(automated action or reason not specified)"
                quick_switch_dict['embed'].add_field(name=f'*{snowflake_time(ts_id).strftime("%H:%M %d.%m.%y")}*', value=f'"{fmt_msg[0][7:] if not match else fmt_msg[0][7:match.start(0)]}" {acting_user_message}', inline=False)
            if not current_msg:
                current_msg = await self.safe_send_message(channel, embed=quick_switch_dict['embed'])
            else:
                current_msg = await self.safe_edit_message(current_msg, embed=quick_switch_dict['embed'])
            
            if current_index != 0:
                await current_msg.add_reaction('⬅')
            await current_msg.add_reaction('ℹ')
            if (current_index+step) < len(message_dict):
                await current_msg.add_reaction('➡')
                
            def check(reaction, usr):
                e = str(reaction.emoji)
                if usr != self.user and reaction.message.id == current_msg.id:
                    return e.startswith(('⬅', '➡', 'ℹ'))
                else:
                    return False
            try:
                reac, usr = await self.wait_for('reaction_add', check=check, timeout=300)
            except:
                return
            if str(reac.emoji) == 'ℹ':
                await self.safe_send_message(current_msg.channel, content=quick_switch_dict['member_obj'].id)
            elif str(reac.emoji) == '➡' and current_index != len(message_dict):
                current_index+=step
                await current_msg.remove_reaction(reac.emoji, usr)
            elif str(reac.emoji) == '⬅' and current_index != 0:
                current_index-=step
                await current_msg.remove_reaction(reac.emoji, usr)
            else:
                return
            await current_msg.clear_reactions()
        

    @mods_only
    async def cmd_warn(self, message, guild, author, mentions, raw_leftover_args):
        """
        Usage {command_prefix}warn [@mention OR User ID] <reason for warning>
        Creates a warning for a user which is put into the action-log and shows up in `{command_prefix}history
        """
        if not raw_leftover_args:
            return Response(doc_string(inspect.getdoc(getattr(self, inspect.getframeinfo(inspect.currentframe()).function)), self.prefix))
        
        converter = UserConverter()
        users = []
        warning_str = None
        
        
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
                    break
                
        warning_str = ' '.join(raw_leftover_args)
        for user in users:
            if warning_str:
                print(f'user {user.name} warned for {warning_str}')
                em = discord.Embed(colour=discord.Colour(0xFF0000), description=MSGS['warn'].format(server=guild.name, reason=(": " + warning_str)))
                await self.safe_send_message(user, embed=em)
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Warned user for {}'.format(warning_str), reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                self.last_actions[author.id] = action_msg
            else:
                print(f'user {user.name} warned for {warning_str}')
                em = discord.Embed(colour=discord.Colour(0xFF0000), description=MSGS['warn'].format(server=guild.name, reason=""))
                await self.safe_send_message(user, embed=em)
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Warned user for -REASON NOT GIVEN-', reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                self.last_actions[author.id] = action_msg
            await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=user.mention, id=user.id, reason='as they were warned'))
        
        return Response(':thumbsup:') 

    @mods_only
    async def cmd_mute(self, message, guild, author, mentions, raw_leftover_args):
        """
        Usage {command_prefix}mute [@mention OR User ID] <time>
        Mutes ppl
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
                
        seconds_to_mute = timestamp_to_seconds(''.join(raw_leftover_args))
        
        mutedrole = discord.utils.get(guild.roles, id=ROLES['muted'])
        if not mutedrole:
            raise CommandError('No Muted role found')
            
        for user in users:
            try:
                user = guild.get_member(user.id)
                if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await user.edit(roles = list(set(([role for role in user.roles if role.id not in UNPROTECTED_ROLES] + [mutedrole]))))

                try:
                    await user.edit(mute=True)
                except:
                    pass
            except discord.Forbidden:
                raise CommandError('Not enough permissions to mute user : {}'.format(user.name))
            except:
                traceback.print_exc()
                raise CommandError('Unable to mute user defined:\n{}\n'.format(user.name))
        response = ':thumbsup:'
        
        for user in users:
            if seconds_to_mute:
                muted_datetime = datetime.utcnow() + timedelta(seconds = seconds_to_mute)
                self.muted_dict[user.id] = muted_datetime.timestamp()
                print('user {} now timed muted'.format(user.name))
                em = discord.Embed(colour=discord.Colour(0xFF0000), description=MUTED_MESSAGES['timed'].format(time=' '.join(raw_leftover_args), rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(user, embed=em)
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Muted user for {}'.format(' '.join(raw_leftover_args)), reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                self.last_actions[author.id] = action_msg
                asyncio.ensure_future(self.queue_timed_mute(seconds_to_mute, user, mutedrole, user.id))
                response += ' muted for %s seconds' % seconds_to_mute
            else:
                self.muted_dict[user.id] = None
                em = discord.Embed(colour=discord.Colour(0xFF0000), description=MUTED_MESSAGES['plain'].format(rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(user, embed=em)
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Muted user forever', reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                self.last_actions[author.id] = action_msg
            await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=user.mention, id=user.id, reason='as they were muted'))
        
        write_json('muted.json', self.muted_dict)
        return Response(response) 
        
    @mods_only
    async def cmd_addsgd(self, message, guild, author, mentions, raw_leftover_args):
        """
        Usage {command_prefix}addsgd [@mention OR User ID] 
        Adds the "Serious Game Discussion" role to people
        """
        if not raw_leftover_args:
            return Response(doc_string(inspect.getdoc(getattr(self, inspect.getframeinfo(inspect.currentframe()).function)), self.prefix))
        
        converter = UserConverter()
        users = []
        
        
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
                
        
        sgdrole = discord.utils.get(guild.roles, id=ROLES['seriousd'])
        if not sgdrole:
            raise CommandError('No SGD role found')
            
        for user in users:
            try:
                user = guild.get_member(user.id)
                await user.edit(roles = list(set(([role for role in user.roles] + [sgdrole]))))
            except discord.Forbidden:
                raise CommandError('Not enough permissions to mute user : {}'.format(user.name))
            except:
                traceback.print_exc()
                raise CommandError('Unable to mute user defined:\n{}\n'.format(user.name))
        return Response(f'Added SGD role to {user.mention}') 
        
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
            elif seconds_to_slow and 0 < seconds_to_slow <= 120:
                await channel.edit(slowmode_delay=seconds_to_slow)
                await self.safe_send_message(channel, content='The delay between allowed messages is now **%s seconds**!' % seconds_to_slow)
            else:
                raise CommandError('ERROR: Time provided is invalid (not between the range of 0 to 120 seconds).')
            action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=(MSGS['action'][:21] + MSGS['action'][57:]).format(optional_content='', action='Channel {} put in slow mode of {}'.format(channel.name, channel.slowmode_delay), reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
            self.last_actions[author.id] = action_msg
        return Response(':thumbsup:')


    @mods_only
    async def cmd_botslow(self, message, author, guild, channel_mentions, leftover_args):
        """
        Usage: {command_prefix}botslow #channel <time between messages>
        Puts the channel mentioned into a slowmode where users can only send messages every x seconds.
        To turn slow mode off, set the time between messages to "0"
        """
        seconds_to_slow = timestamp_to_seconds(''.join(leftover_args[1:]))
        if not seconds_to_slow:
            seconds_to_slow = 0
        channel_mentions = channel_mentions[0]
        try:
            if channel_mentions.id in self.slow_mode_dict.keys():
                if seconds_to_slow == 0 :
                    await self.slow_mode_dict[channel_mentions.id]['channel_muted_role'].delete()
                    del self.slow_mode_dict[channel_mentions.id]
                    await self.safe_send_message(self.get_channel(channel_mentions.id), content='This channel is no longer in slow mode!')
                else:
                    self.slow_mode_dict[channel_mentions.id]['time_between'] = seconds_to_slow
                    await self.safe_send_message(self.get_channel(channel_mentions.id), content='The delay between allowed messages is now **%s seconds**!' % seconds_to_slow)
            else:
                if seconds_to_slow == 0:
                    await self.safe_send_message(self.get_channel(message.channel.id), content='No time detected, please use a valid time!')
                    return
                slowed_channel = discord.utils.get(guild.channels, id=channel_mentions.id)
                channel_muted_role = await guild.create_role(name=slowed_channel.name + 'SLOWROLE',
                                                            permissions=discord.Permissions(permissions=66560))
                overwrite = discord.PermissionOverwrite()
                overwrite.send_messages = False
                await slowed_channel.set_permissions(channel_muted_role, overwrite=overwrite)
                await self.safe_send_message(self.get_channel(channel_mentions.id), content='This channel is now in slow mode with a delay of **%s seconds**!' % seconds_to_slow)
                self.slow_mode_dict[channel_mentions.id] = {'time_between': seconds_to_slow,
                                                   'channel_muted_role': channel_muted_role}
            action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=(MSGS['action'][:21] + MSGS['action'][57:]).format(optional_content='', action='Channel {} put in slow mode of {}'.format(channel_mentions.name, ' '.join(leftover_args[1:])), reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
            self.last_actions[author.id] = action_msg
            return Response(':thumbsup:')
        except:
            traceback.print_exc()
            raise CommandError('ERROR: Please make sure the syntax is correct and resubmit the command!')

    @mods_only
    async def cmd_purge(self, message, author, guild, channel, mentions):
        """
        Usage: {command_prefix}purge <number of messages to purge> @UserName ["reason"]
        Removes all messages from chat unless a user is specified;
        then remove all messages by the user.
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
        await self.log_action(user=author, message=deleted, action='bulk_message_delete')
        deleted = len(deleted)
        messages = [f'{deleted} message{" was" if deleted == 1 else "s were"} removed.']
        if deleted:
            messages.append('')
            spammers = sorted(spammers.items(), key=lambda t: t[1], reverse=True)
            messages.extend(f'**{name}**: {count}' for name, count in spammers)

        to_send = '\n'.join(messages)

        if len(to_send) > 2000:
            return Response(f'Successfully removed {clean_string(deleted)} messages.', delete_after=10, delete_invoking=True) 
        else:
            return Response(clean_string(to_send), delete_after=10, delete_invoking=True) 

        
    @mods_only
    async def cmd_userinfo(self, guild, channel, message, author, mentions, raw_leftover_args):
        """
        Usage {command_prefix}userinfo [@mention OR User ID]
        Gathers info on a user and posts it in one easily consumable embed
        """
        converter = UserConverter()
        user = None
        
        
        if mentions:
            user = mentions[0]
            try:
                raw_leftover_args.remove(mentions[0].mention)
            except:
                raw_leftover_args.remove(f"<@!{mentions[0].id}>")
                    
        else:
            temp = " " if len(list(raw_leftover_args)) > 1 else ""
            temp = temp.join(list(raw_leftover_args)).strip()
            print(f"'{temp}'")
            try:
                user = await converter.convert(message, self, temp)
            except:
                traceback.print_exc()
                pass
                
        if not user:
            user = author
            
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
            if not member.joined_at:
                em.add_field(name='Joined On:', value='ERROR: Cannot fetch', inline=False)
            else:
                em.add_field(name='Joined On:', value='{} ({} ago)'.format(member.joined_at.strftime('%c'), strfdelta(datetime.utcnow() - member.joined_at)), inline=False)
            em.add_field(name='Created On:', value='{} ({} ago)'.format(user.created_at.strftime('%c'), strfdelta(datetime.utcnow() - user.created_at)), inline=False)
            member_search = await self.do_search(guild_id=guild.id, author_id=user.id)
            em.add_field(name='Messages in Server:', value='{}'.format(member_search["total_results"]), inline=False)
            em.add_field(name='Voice Channel Activity:', value=f'{vc_string}', inline=False)
            em.add_field(name='Roles:', value='{}'.format(', '.join([f'<@&{role.id}>' for role in member.roles])), inline=False)
            member_profile = await self.get_profile(member.id)
            em.add_field(name='Nitro Since:', value='{} ({} ago)'.format(member_profile.premium_since, strfdelta(datetime.utcnow() - member_profile.premium_since)) if member_profile.premium else '-Not Subscribed-', inline=False)
            if member_profile.hypesquad: 
                em.add_field(name='User In HypeSquad', value='<:r6hype:420535089898848266> ', inline=True)
            if member_profile.partner: 
                em.add_field(name='User Is a Partner', value='<:r6partner:420535152117284865>', inline=True)
            if member_profile.staff: 
                em.add_field(name='User Is Staff', value='<:r6staff:420535209398763520>', inline=True)
            connection_txt = '\n'.join(['{}{}: {}'.format('{}'.format(con['type']).rjust(9), '\u2705' if con['verified'] else '\U0001F6AB', con["name"]) for con in member_profile.connected_accounts])
            if not connection_txt:
                connection_txt = 'None'
            em.add_field(name='Connections:', value='```{}```'.format(connection_txt), inline=False)
            
            em.set_author(name=f"{'%s AKA %s' % (member.nick, user.name) if member.nick else user.name}", icon_url='https://i.imgur.com/FSGlsOR.png')
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
                if not reason:
                    history_items = []
                    
                    search_in_actions = (await self.do_search(guild_id=guild.id, channel_id=CHANS['actions'], content=user.id))['messages']
                    for message_block in search_in_actions:
                        for msg in message_block:
                            if str(user.id) in msg["content"] and "Banned user" in msg["content"] and msg["content"] not in history_items:
                                history_items.append(msg["content"])
                    reason = (cleanup_blocks(history_items[-1]).strip().split("\n"))[2][7:]

                em.add_field(name='User Banned from Server:', value=f'Reason: {reason}', inline=False)
            except discord.NotFound:
                pass
                
        em.set_thumbnail(url=user.avatar_url)
        await self.safe_send_message(channel, embed=em)

    async def cmd_status(self, author, message, guild, channel):
        """
        Usage {command_prefix}status
        Fetches the server status from ubisoft's API
        """
        if int(author.id) in self.tagblacklist:
            return
            
        color = None
        status_colorizer = [value for value in self.server_status.values() if not isinstance(value, datetime)]
        if 'degraded' in status_colorizer:
            color = R6_STATUS_COLORS['degraded']
        elif 'interrupted' in status_colorizer:
            color = R6_STATUS_COLORS['interrupted']
        elif 'maintenance' in status_colorizer:
            color = R6_STATUS_COLORS['maintenance']
        elif 'online' in status_colorizer:
            color = R6_STATUS_COLORS['online']
        pc_string = f"{str(self.get_emoji(R6_STATUS_EMOTES[self.server_status['PC']]))} __PC__: **{self.server_status['PC'].capitalize()}**"
        xbox_string = f"{str(self.get_emoji(R6_STATUS_EMOTES[self.server_status['PS4']]))} __PS4__: **{self.server_status['PS4'].capitalize()}**"
        ps4_string = f"{str(self.get_emoji(R6_STATUS_EMOTES[self.server_status['XBOXONE']]))} __Xbox__: **{self.server_status['XBOXONE'].capitalize()}**"
        em = discord.Embed(description=f"{pc_string}\n{xbox_string}\n{ps4_string}",
                           colour=discord.Colour(color),
                           timestamp=self.server_status['timestamp'])
        em.set_author(name="Siege Server Status")
        if [role for role in message.author.roles if role.id  in [ROLES['staff'], ROLES['tagmaster']]] or channel.id == CHANS["genbotspam"]:
            await self.safe_send_message(channel, embed=em)
        

    @mods_only
    async def cmd_genembeds(self, author, message, guild, channel):
        """
        Usage {command_prefix}genembeds
        Generates and then reposts the embeds found in the react role assignment channel
        """
        try:
            await self.get_channel(CHANS['roleswap']).purge(limit=100, check=is_me)
        except:
            async for entry in self.get_channel(CHANS['roleswap']).history(limit=10000):
                if entry.author == self.user:
                    await self.safe_delete_message(entry)
                    await asyncio.sleep(0.21)
        em = discord.Embed(description='React with each of the platforms you play on by clicking on the corresponding platform icon below.', colour=discord.Colour(0x9d9bf4))
        em.set_author(name="Platform Role Assignment")
        msg = await self.safe_send_message(self.get_channel(CHANS['roleswap']), embed=em)
        await msg.add_reaction(self.get_emoji(REACTS['pc']))
        await msg.add_reaction(self.get_emoji(REACTS['ps4']))
        await msg.add_reaction(self.get_emoji(REACTS['xbox']))
        
        em = discord.Embed(description='React below if you\'d like to be pinged when any news regarding Rainbow 6 is posted!.', colour=discord.Colour(0x9d9bf4))
        em.set_author(name="Rainbow 6 News Toggle")
        msg = await self.safe_send_message(self.get_channel(CHANS['roleswap']), embed=em)
        await msg.add_reaction(self.get_emoji(REACTS['r6ping']))
        
        em = discord.Embed(description='React below if you\'d like to be pinged when any news regarding this discord server is posted!', colour=discord.Colour(0x9d9bf4))
        em.set_author(name="Server News Toggle")
        msg = await self.safe_send_message(self.get_channel(CHANS['roleswap']), embed=em)
        await msg.add_reaction(self.get_emoji(REACTS['serverping']))
        
        await self.safe_send_message(self.get_channel(CHANS['roleswap']), content='__                                                                                                          __\n:clock3: You will need to wait for the 10-minute timer to finish before selecting a role.\n:warning: Please refresh Discord using Ctrl+R if the reactions are not visible.')
        
        return Response(':thumbsup:')

        
    @mods_only
    async def cmd_ban(self, message, guild, author, mentions, raw_leftover_args):
        """
        Usage {command_prefix}ban [@mention OR User ID] <time>
        Bans ppl. Time accepts 0 - 7 as an argument
        Time is optional, if included, purges messages in days dating back to that point
        """
        if not raw_leftover_args:
            return Response(doc_string(inspect.getdoc(getattr(self, inspect.getframeinfo(inspect.currentframe()).function)), self.prefix))
            
        converter = UserConverter()
        users = []
        ban_time = 0
        
        if raw_leftover_args and re.fullmatch(r'[0-7]', raw_leftover_args[-1]):
            ban_time = raw_leftover_args.pop()
        if mentions:
            for user in mentions:
                users.append(user)
        else:
            for item in raw_leftover_args:
                users.append(await converter.convert(message, self, item, discrim_required=True))
                
        for user in users:
            try:
                if  ROLES['staff'] in [role.id for role in discord.utils.get(guild.members, id=user.id).roles]: return Response('Error: User is Staff!')
                em = discord.Embed(colour=discord.Colour(0xFF0000), description=MSGS['banmsg'])
                await self.safe_send_message(user, embed=em)
            except:
                pass
            try:
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Banned user', reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                self.last_actions[author.id] = action_msg
                await self.http.ban(user.id, guild.id, ban_time)
                if user.id in self.muted_dict:
                    del self.muted_dict[user.id]
            except discord.Forbidden:
                raise CommandError('Not enough permissions to ban user : {}'.format(user.name))
            except:
                traceback.print_exc()
                raise CommandError('Unable to ban user defined:\n{}\n'.format(user.name))
        return Response(':thumbsup:')


    @mods_only
    async def cmd_softban(self, message, guild, author, mentions, raw_leftover_args):
        """
        Usage {command_prefix}softban [@mention OR User ID] <time>
        Bans and then unbans ppl to bulk delete their messages. Should be used as a "kick but also delete messages"
        Time accepts 0 - 7 as an argument
        Time is optional, if included, purges messages in days dating back to that point
        """
        if not raw_leftover_args:
            return Response(doc_string(inspect.getdoc(getattr(self, inspect.getframeinfo(inspect.currentframe()).function)), self.prefix))
            
        converter = UserConverter()
        users = []
        ban_time = 7
        
        if raw_leftover_args and re.fullmatch(r'[0-7]', raw_leftover_args[-1]):
            ban_time = raw_leftover_args.pop()
        if mentions:
            for user in mentions:
                users.append(user)
        else:
            for item in raw_leftover_args:
                users.append(await converter.convert(message, self, item, discrim_required=True))
                
        for user in users:
            # Not sure if I actually wanna send ppl who were softbanned a msg since we don't do it for kicks.
            # Its implemented anyway if we decide otherwise
            # try:
                # await self.safe_send_message(user, content=MSGS['softbanmsg'])
            # except:
                # pass
            try:
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Softbanned user', reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                self.last_actions[author.id] = action_msg
                await self.http.ban(user.id, guild.id, ban_time)
                await guild.unban(user)
            except discord.Forbidden:
                raise CommandError('Not enough permissions to ban user : {}'.format(user.name))
            except:
                traceback.print_exc()
                raise CommandError('Unable to ban user defined:\n{}\n'.format(user.name))
                
        return Response(':thumbsup:')        
        
    async def log_action(self, user, action, *, message=None, after = None):
        file = None
        if action == 'server_join':
            em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user), title='Account **{} old.**'.format(strfdelta(datetime.utcnow() - user.created_at)),colour=discord.Colour(0x32CD32), timestamp=datetime.utcnow())
            em.set_author(name="𝅳𝅳𝅳User Joined Server", icon_url="https://i.imgur.com/cjJm2Yb.png")
            em.set_thumbnail(url=user.avatar_url)
            if datetime.utcnow() - timedelta(hours=24) < user.created_at:
                em.set_footer(text="WARNING: User account is < 24 hours old (FRESH)", icon_url="https://i.imgur.com/RsOSopy.png")
        elif action == 'server_leave':
            if not user.joined_at:
                em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user), title='Left Server', colour=discord.Colour(0xCD5C5C), timestamp=datetime.utcnow())
            else:
                em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user), title='Left after **{}**.'.format(strfdelta(datetime.utcnow() - user.joined_at)),colour=discord.Colour(0xCD5C5C), timestamp=datetime.utcnow())
            
            em.set_author(name="𝅳𝅳𝅳User Left Server", icon_url="https://i.imgur.com/gturKf2.png")
            em.set_thumbnail(url=user.avatar_url)
        elif action == 'server_ban':
            em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user),colour=discord.Colour(0xFF0000), timestamp=datetime.utcnow())
            em.set_author(name="𝅳𝅳𝅳User Banned from Server", icon_url="https://i.imgur.com/gqseDvC.png")
            em.set_thumbnail(url=user.avatar_url)
        elif action == 'server_unban':
            em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user),colour=discord.Colour(0xFFFF99), timestamp=datetime.utcnow())
            em.set_author(name="𝅳𝅳𝅳User Unbanned from Server", icon_url="https://i.imgur.com/hPTzmRa.png")
            em.set_thumbnail(url=user.avatar_url)
        elif action == 'message_edit':
            if message.channel.id in UNLOGGED_CHANNELS: return
            em = discord.Embed(description='**𝅳𝅳𝅳User Edited Message by ID {2} in {1}**\n{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user, message.channel.mention, message.id), colour=discord.Colour(0xFFFF00), timestamp=datetime.utcnow())
            em.set_author(name="𝅳𝅳𝅳", icon_url="https://i.imgur.com/NLpSnr2.png")
            em.set_thumbnail(url=user.avatar_url)
            
            if len(message.content) > 1020:
             message.content = f'{message.content[:1020]}...'
             
            em.add_field(name='BEFORE: ', value=message.content, inline=False)
            
            if message.attachments:
                em.add_field(name='ATTACHMENTS: ', value=', '.join([attachment.url for attachment in message.attachments]), inline=False)

            if len(after.content) > 1020:
             after.content = f'{after.content[:1020]}...'
             
            em.add_field(name='\nAFTER: ', value=after.content, inline=False)
        elif action == 'message_delete':
            if message['channel'] in UNLOGGED_CHANNELS: return
            em = discord.Embed(description='**User\'s Message By ID {2} Deleted in <#{1}>**\n{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user, message['channel'], message['message_id']),colour=discord.Colour(0x305ebf), timestamp=datetime.utcnow())
            em.set_author(name="", icon_url="https://i.imgur.com/MrrRQTo.png")
            em.set_thumbnail(url=user.avatar_url)
            if not message['content']:
                message['content'] = 'None!'
            if len(message['content']) > 1020:
                message['content'] = f'{message["content"][:1020]}...'
            em.add_field(name='Content: ', value=message['content'], inline=False)
            if after:
                em.add_field(name='ATTACHMENTS: ', value=', '.join([attachment.url for attachment in after]), inline=False)
                
        elif action == 'bulk_message_delete':
            if message[0].channel.id in UNLOGGED_CHANNELS: return
            actor = user
            em = []
            author_dict = {msg.author: [] for msg in message}
            for msg in message:
                if msg.author in author_dict:
                    author_dict[msg.author].append(msg)
                else:
                    print('dumb fucking error in bulk delete action logging')
            for user, messages in author_dict.items():
                try:
                    msgs_content = [f' - `{msg.content if len(msg.content) < 1020 else msg.content[:1020]+"..."}`{"ATTACHMENTS: ```" if msg.attachments else ""}{", ".join([attachment.url for attachment in msg]) if msg.attachments else ""}{"```" if msg.attachments else ""}\n' for msg in messages]
                    emb = discord.Embed(description=f'**𝅳𝅳𝅳User\'s Messages Bulk Deleted in {message[0].channel.mention} by {actor.mention}**\n\n\n→{user.mention} - `{user.name}#{user.discriminator} ({user.id})`',colour=discord.Colour(0x305ebf), timestamp=datetime.utcnow())
                    emb.set_author(name=" ", icon_url="https://i.imgur.com/RsOSopy.png")
                    emb.set_thumbnail(url=user.avatar_url)
                    count = 1
                    for msg_to_send in msgs_content:
                        if count < 21:
                            emb.add_field(name=f'Message {count}', value=msg_to_send, inline=False)
                        count+=1
                    if count > 20 :
                        emb.set_footer(icon_url='https://cdn.discordapp.com/emojis/414648560110403595.gif', text=f'along with {count-20} more messages.')
                    em.append(emb)
                except TypeError:
                    print(messages)
                    traceback.print_exc()
                
        # elif action == 'avatar_change':
            # em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user),colour=discord.Colour(0xA330BF), timestamp=datetime.utcnow())
            # em.set_author(name="𝅳𝅳𝅳User Changed Avatar", icon_url="https://i.imgur.com/C21wipj.png")
            # ffmpeg_success = True
            
            # def do_ffmpeg_things():
                # ffmpeg.filter_((avatar_before.filter_('scale', w=-1, h=70), avatar_after.filter_('scale', w=-1, h=70)), 'hstack').output('output.gif').overwrite_output().run(cmd='ffmpeg', loglevel ='0')
            # after.avatar_url.replace('size=1024&_=.gif', '')
            # try:            
                # avatar_before = ffmpeg.input("avatars/{}.gif".format(user.id))
                # avatar_after = ffmpeg.input(after.avatar_url)
                
                # do_ffmpeg_things()
            # except subprocess.CalledProcessError as e:
                # print(e.output)
                # try:
                    # avatar_before = ffmpeg.input('backup.gif')
                    # avatar_after = ffmpeg.input(after.avatar_url)
                    
                    # do_ffmpeg_things()
                # except subprocess.CalledProcessError as e:
                    # print(e.output)
                    # em.set_image(url=after.avatar_url)
                    # ffmpeg_success = False
                    
            # if ffmpeg_success:
                # for member in discord.utils.get(self.guilds, id=SERVERS['main']).members:
                    # async with aiohttp.ClientSession() as sess:
                        # avatar_url = member.avatar_url
                        # if '.png' in avatar_url:
                            # ffmpeg.input(avatar_url).output("avatars/{}.gif".format(member.id)).overwrite_output().run(cmd='ffmpeg', loglevel ='-8')
                        # else:
                            # async with sess.get(avatar_url) as r:
                                # data = await r.read()
                                # with open("avatars/{}.gif".format(member.id), "wb") as f:
                                    # f.write(data)

                # file = discord.File("/home/bots/r6botrw/output.gif", filename="output.gif")
                # em.set_image(url="attachment://output.gif")
        elif action == 'avatar_change':
            em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user),colour=discord.Colour(0xA330BF), timestamp=datetime.utcnow())
            em.set_author(name="𝅳𝅳𝅳User Changed Avatar", icon_url="https://i.imgur.com/C21wipj.png")
            em.set_image(url=after.avatar_url_as(size=128))
        elif action == 'name_change':
            em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user),colour=discord.Colour(0xA330BF), timestamp=datetime.utcnow())
            em.set_author(name="𝅳𝅳𝅳User Changed Name", icon_url="https://i.imgur.com/C21wipj.png")
            em.set_thumbnail(url=user.avatar_url)
            em.add_field(name='BEFORE: ', value=user.name, inline=False)
            em.add_field(name='\nAFTER: ', value=after.name, inline=False)
        elif action == 'nickname_change':
            em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user),colour=discord.Colour(0x6130BF), timestamp=datetime.utcnow())
            em.set_author(name="𝅳𝅳𝅳User Changed Nickname", icon_url="https://i.imgur.com/C21wipj.png")
            em.set_thumbnail(url=user.avatar_url)
            em.add_field(name='BEFORE: ', value=user.nick, inline=False)
            em.add_field(name='\nAFTER: ', value=after.nick, inline=False)
        elif action == 'important_role_change':
            em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user),colour=discord.Colour(0xC69FBA), timestamp=datetime.utcnow())
            em.set_author(name="𝅳𝅳𝅳User Changed Important Roles", icon_url="https://i.imgur.com/Ubp44ao.png")
            em.set_thumbnail(url=user.avatar_url)
            
            before_values = [x.name for x in user.roles[1:]]
            after_values = [x.name for x in after.roles[1:]]
            
            em.add_field(name='BEFORE: ', value='`, `'.join(before_values) if before_values else 'None', inline=False)
            em.add_field(name='\nAFTER: ', value='`, `'.join(after_values) if after_values else 'None', inline=False)
        else:
            print('how does one break the server log?')
            return
        if isinstance(em, list):
            for emb in em:
                sent_msg = await self.safe_send_message(self.get_channel(CHANS['serverlog']), embed=emb, file=file)
        else:
            sent_msg = await self.safe_send_message(self.get_channel(CHANS['serverlog']), embed=em, file=file)
        
    async def on_raw_reaction_remove(self, payload):
        if not self.use_reactions: return
        
        emoji = payload.emoji
        message_id = payload.message_id
        channel_id = payload.channel_id
        user_id = payload.user_id
        
        if channel_id == CHANS['roleswap']:
            member = self.get_guild(SERVERS['main']).get_member(user_id)
            if member and [role for role in member.roles if role.id == ROLES['muted']]:
                return
            if emoji.id == REACTS['pc']:
                await self.http.remove_role(SERVERS['main'], user_id, ROLES['pc'], reason=None)
            if emoji.id  ==  REACTS['xbox']:
                await self.http.remove_role(SERVERS['main'], user_id, ROLES['xbox'], reason=None)
            if emoji.id  ==  REACTS['ps4']:
                await self.http.remove_role(SERVERS['main'], user_id, ROLES['ps4'], reason=None)
            if emoji.id  ==  REACTS['r6ping']:
                await self.http.remove_role(SERVERS['main'], user_id, ROLES['r6news'], reason=None)
            if emoji.id  ==  REACTS['invitationals']:
                await self.http.remove_role(SERVERS['main'], user_id, ROLES['invitationals'], reason=None)
            if emoji.id  ==  REACTS['serverping']:
                await self.http.remove_role(SERVERS['main'], user_id, ROLES['servernews'], reason=None)

    async def on_typing(self, channel, user, when):
        if channel.id in [CHANS['gamenews'], CHANS['servernews']]:
            if channel.id == CHANS['gamenews']:
                role = discord.utils.get(channel.guild.roles, id=ROLES['r6news'])
                self.role_ping_toggle['game'] = role
            if channel.id == CHANS['servernews']:
                role = discord.utils.get(channel.guild.roles, id=ROLES['servernews'])
                self.role_ping_toggle['server'] = role
            await role.edit(mentionable=True)
            await asyncio.sleep(30)
            await role.edit(mentionable=False)
    
    async def on_raw_message_delete(self, payload):
        channel_id = payload.channel_id
        message_id = payload.message_id
        if isinstance(self.get_channel(channel_id), discord.abc.PrivateChannel):
            return
        message = discord.utils.get(self._connection._messages, id=message_id)
        if message:
            hacky_code_dict = {'content': message.content, 'channel': message.channel.id, 'message_id': message.id}
            await self.log_action(message=hacky_code_dict, after=message.attachments, user=message.author, action='message_delete')
        else:
            if channel_id in self.messages_log and message_id in self.messages_log[channel_id]:
                cached_msg = self.messages_log[channel_id][message_id]
                author = await self.fetch_user(cached_msg['author'])
                hacky_code_dict = {'content': cached_msg['content'], 'channel': channel_id, 'message_id': message_id}
                await self.log_action(message=hacky_code_dict, user=author, action='message_delete')            
                    
    async def on_raw_reaction_add(self, payload):
        emoji = payload.emoji
        message_id = payload.message_id
        channel_id = payload.channel_id
        user_id = payload.user_id
        if not self.use_reactions: return
        if user_id == self.user.id:
            return
        if channel_id == CHANS['modmail']:
            modmail = self.get_channel(CHANS['modmail'])
            if emoji.name == 'ℹ':
                msg = await modmail.fetch_message(message_id)
                match = re.search(r'Reply ID: `([0-9]+)`$', msg.content)
                if match:
                    await self.safe_send_message(modmail, content=match.group(1))
            elif emoji.name == '✅':
                msg = await modmail.fetch_message(message_id)
                match = re.search(r'Reply ID: `([0-9]+)`$', msg.content)
                if match:
                    auth_id = int(match.group(1))
                    if auth_id in self.mod_mail_db:
                        self.mod_mail_db[auth_id]['answered'] = True
                        write_json('modmaildb.json', self.mod_mail_db)
                        await self.safe_send_message(modmail, content=':thumbsup:')
                        
        if channel_id == CHANS['roleswap']:
            member = self.get_guild(SERVERS['main']).get_member(user_id)
            if member and [role for role in member.roles if role.id == ROLES['muted']]:
                return
            if emoji.id == REACTS['pc']:
                await self.http.add_role(SERVERS['main'], user_id, ROLES['pc'], reason=None)
            if emoji.id  ==  REACTS['xbox']:
                await self.http.add_role(SERVERS['main'], user_id, ROLES['xbox'], reason=None)
            if emoji.id  ==  REACTS['ps4']:
                await self.http.add_role(SERVERS['main'], user_id, ROLES['ps4'], reason=None)
            if emoji.id  ==  REACTS['r6ping']:
                await self.http.add_role(SERVERS['main'], user_id, ROLES['r6news'], reason=None)
            if emoji.id  ==  REACTS['invitationals']:
                await self.http.add_role(SERVERS['main'], user_id, ROLES['invitationals'], reason=None)
            if emoji.id  ==  REACTS['serverping']:
                await self.http.add_role(SERVERS['main'], user_id, ROLES['servernews'], reason=None)

    async def on_reaction_add(self, reaction, member):
        if not self.use_reactions: return
        if member.id == self.user.id:
            return
        if reaction.message.channel.id in [CHANS['drama']]:
            user = discord.utils.get(reaction.message.guild.members, id=self.watched_messages[reaction.message.id]['author_id'])
            if ROLES['staff'] in [role.id for role in user.roles]: 
                await self.safe_delete_message(reaction.message)
                return
            mutedrole = discord.utils.get(reaction.message.guild.roles, id=ROLES['muted'])
            if reaction.emoji.id == REACTS['delete']:
                await self.safe_delete_message(await self.get_channel(self.watched_messages[reaction.message.id]['channel_id']).fetch_message(self.watched_messages[reaction.message.id]['message_id']))
            if reaction.emoji.id == REACTS['mute']:
                try:
                    if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await user.edit(roles = list(set(([role for role in user.roles if role.id not in UNPROTECTED_ROLES] + [mutedrole]))))

                    try:
                        await user.edit(mute=True)
                    except:
                        pass
                except:
                    await self.safe_send_message(self.get_channel(CHANS['drama']), content='Cannot mute user {} ({}) for they\'re not on the server'.format(await self.fetch_user(self.watched_messages[reaction.message.id]['author_id']).name, self.watched_messages[reaction.message.id]['author_id']))
                    return
                self.muted_dict[user.id] = None
                em = discord.Embed(colour=discord.Colour(0xFF0000), description=MUTED_MESSAGES['plain'].format(rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(user, embed=em)
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Muted user', reason='Action taken by {}#{}'.format(member.name, member.discriminator)))
                self.last_actions[member.id] = action_msg
                await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=user.mention, id=user.id, reason='as they were muted'))
            if reaction.emoji.id == REACTS['24mute']:
                try:
                    if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await user.edit(roles = list(set(([role for role in user.roles if role.id not in UNPROTECTED_ROLES] + [mutedrole]))))
                    try:
                        await user.edit(mute=True)
                    except:
                        pass
                except:
                    await self.safe_send_message(self.get_channel(CHANS['drama']), content='Cannot mute user {} ({}) for they\'re not on the server'.format(await self.fetch_user(self.watched_messages[reaction.message.id]['author_id']).name, self.watched_messages[reaction.message.id]['author_id']))
                    return
                muted_datetime = datetime.utcnow() + timedelta(hours = 24)
                self.muted_dict[user.id] = muted_datetime.timestamp()
                print('user {} now timed muted'.format(user.name))
                em = discord.Embed(colour=discord.Colour(0xFF0000), description=MUTED_MESSAGES['timed'].format(time='24 hours', rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(user, embed=em)
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Muted user for 24 hrs', reason='Action taken by {}#{}'.format(member.name, member.discriminator)))
                self.last_actions[member.id] = action_msg
                await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=user.mention, id=user.id, reason='as they were muted for 24 hrs'))
                asyncio.ensure_future(self.queue_timed_mute(86400, user, mutedrole, user.id))
            if reaction.emoji.id == REACTS['48mute']:
                try:
                    if not ROLES['staff'] in [role.id for role in user.roles] and not user.bot: await user.edit(roles = list(set(([role for role in user.roles if role.id not in UNPROTECTED_ROLES] + [mutedrole]))))

                    try:
                        await user.edit(mute=True)
                    except:
                        pass
                except:
                    await self.safe_send_message(self.get_channel(CHANS['drama']), content='Cannot mute user {} ({}) for they\'re not on the server'.format(await self.fetch_user(self.watched_messages[reaction.message.id]['author_id']).name, self.watched_messages[reaction.message.id]['author_id']))
                    return
                muted_datetime = datetime.utcnow() + timedelta(hours = 48)
                self.muted_dict[user.id] = muted_datetime.timestamp()
                print('user {} now timed muted'.format(user.name))
                em = discord.Embed(colour=discord.Colour(0xFF0000), description=MUTED_MESSAGES['timed'].format(time='48 hours', rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(user, embed=em)
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Muted user for 48 hrs', reason='Action taken by {}#{}'.format(member.name, member.discriminator)))
                self.last_actions[member.id] = action_msg
                await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=user.mention, id=user.id, reason='as they were muted for 48 hrs'))
                asyncio.ensure_future(self.queue_timed_mute(172800, user, mutedrole, user.id))
            if reaction.emoji.id == REACTS['ban']:
                try:
                    em = discord.Embed(colour=discord.Colour(0xFF0000), description=MSGS['banmsg'])
                    await self.safe_send_message(user, embed=em)
                except:
                    if not user:
                        await self.safe_send_message(self.get_channel(CHANS['drama']), content=MSGS['dramaerror'].format('send ban message to ', self.watched_messages[reaction.message.id]['author_id'], 'Banning anyway...'))
                await self.http.ban(self.watched_messages[reaction.message.id]['author_id'], reaction.message.guild.id, 0)
                action_msg = await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Banned user', reason='Action taken by {}#{}'.format(member.name, member.discriminator)))
                self.last_actions[member.id] = action_msg
                if self.watched_messages[reaction.message.id]['author_id'] in self.muted_dict:
                    del self.muted_dict[self.watched_messages[reaction.message.id]['author_id']]
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
        if member.id in self.muted_dict:
            updated_member_roles = updated_member_roles + [discord.utils.get(member.guild.roles, id=ROLES['muted'])]
        else:   
            
            await asyncio.sleep(5)
            final_msg = '{}, {}'.format(member.mention, self.intro_msg)
            if self.use_reactions:
                await self.safe_send_message(member, content=self.dm_msg)
            else:
                await self.safe_send_message(self.get_channel(CHANS['registration']), content=final_msg)
                
        if updated_member_roles:
            if not ROLES['staff'] in [role.id for role in member.roles]:
                await member.edit(roles = updated_member_roles)
                
        await self.log_action(user=member, action='server_join')

    async def on_member_unban(self, guild, user):
        if user in self.ban_list and self.ban_list[user.id] == guild.id:
            del self.ban_list[user.id]
        await self.log_action(user=user, action='server_unban')
        
    async def on_member_ban(self, guild, user):
        self.ban_list[user.id] = guild.id
        await self.log_action(user=user, action='server_ban')
        
    async def on_member_remove(self, member):
        if member in self.ban_list and self.ban_list[member.id] == member.guild.id:
            return
        await self.log_action(user=member, action='server_leave')
        
    async def on_member_update(self, before, after):
        if before.guild.id == SERVERS['ban']: return
        
        new_roles = [role for role in discord.utils.get(self.guilds, id=SERVERS['main']).roles if role.name.startswith('Ban') and role.id not in self.channel_bans]
        if new_roles:
            print('Found %s new roles!' % len(new_roles))
            for role in new_roles:
                self.channel_bans[role.id] = {member.id: None for member in discord.utils.get(self.guilds, id=SERVERS['main']).members if role in member.roles}
                write_json('channel_banned.json', self.channel_bans)
        if before.nick != after.nick:
            await self.log_action(user=before, after=after, action='nickname_change')
        if before.name != after.name:
            await self.log_action(user=before, after=after, action='name_change')
        # if before.avatar_url != after.avatar_url:
            # await self.log_action(user=before, after=after, action='avatar_change')
        if before.roles != after.roles:
            merged_roles = list((set(before.roles) - set(after.roles))) + list((set(after.roles) - set(before.roles)))
            if [role.id for role in merged_roles if role.id not in UNPROTECTED_ROLES]:
                await self.log_action(user=before, after=after, action='important_role_change')
            try:
                self.serious_d_blacklist = list(set(self.serious_d_blacklist))
                
                if not [role for role in before.roles if role.id  in [ROLES['banteams']]] and [role for role in after.roles if role.id  in [ROLES['banteams']]]:
                    await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=before.name, discrim=before.discriminator ,id=before.id, optional_content='', action='Ban-Player-Team-LFM Applied', reason='Someone will post a screenshot soon (I hope)'))
                if not [role for role in before.roles if role.id  in [ROLES['muted']]] and [role for role in after.roles if role.id  in [ROLES['muted']]]:
                    await asyncio.sleep(5)
                    if before.id not in self.muted_dict:
                        self.muted_dict[before.id] = None
                        print('user {} now no time muted'.format(before.name))
                    write_json('muted.json', self.muted_dict)
                if [role for role in before.roles if role.id  in [ROLES['muted']]] and not [role for role in after.roles if role.id  in [ROLES['muted']]]:
                    await asyncio.sleep(5)
                    if before.id in self.muted_dict:
                        del self.muted_dict[before.id]
                        print('user {} unmuted'.format(before.name))
                    write_json('muted.json', self.muted_dict)
                if not [role for role in before.roles if role.id  in [ROLES['seriousd']]] and [role for role in after.roles if role.id  in [ROLES['seriousd']]]:
                    self.serious_d_blacklist.remove(before.id)
                    print('user {} removed from SD blacklist'.format(before.name))
                    write_json('sd_bl.json', self.serious_d_blacklist)
                if [role for role in before.roles if role.id  in [ROLES['seriousd']]] and not [role for role in after.roles if role.id  in [ROLES['seriousd']]]:
                    self.serious_d_blacklist.append(before.id)
                    print('user {} now in SD blacklist'.format(before.name))
                    write_json('sd_bl.json', self.serious_d_blacklist)
                    
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
        if before.guild and before.guild.id == SERVERS['ban']: return
        if not isinstance(before.channel, discord.abc.PrivateChannel):
            if before.content != after.content:
                await self.log_action(user=before.author, message=before, after=after,  action='message_edit')
        await self.on_message(after, edit=True)
        
    async def on_voice_state_update(self, member, before, after):
        if before != after:
            if not (before and before.channel) and after and after.mute and not ROLES['staff'] in [role.id for role in member.roles]:
                try:
                    await member.edit(mute=False)
                except:
                    pass
            if before and after and (before.channel == after.channel):
                return
            if member.id not in self.voice_changes:
                self.voice_changes[member.id] = {'last_change': datetime.utcnow(), 'changes': 1}
            else:
                if datetime.utcnow() - timedelta(minutes=10) < self.voice_changes[member.id]['last_change']:
                    self.voice_changes[member.id]['changes'] += 1
                else:
                    self.voice_changes[member.id] = {'last_change': datetime.utcnow(), 'changes': 1}
            optional_content = ''
            staff_role = False
            role = discord.utils.get(member.guild.roles, id=ROLES['staff'])
            vc_muted_role = discord.utils.get(member.guild.roles, id=ROLES['vcmuted'])
            if self.voice_changes[member.id]['changes'] < 10:
                optional_content = ':small_blue_diamond:'
            elif self.voice_changes[member.id]['changes'] < 20:
                optional_content = ':small_orange_diamond:'
            elif self.voice_changes[member.id]['changes'] < 30:
                optional_content = ':exclamation:'
            elif self.voice_changes[member.id]['changes'] == 30:
                staff_role = True
                await role.edit(mentionable=True)
                await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=member.name, optional_content='', discrim=member.discriminator ,id=member.id, action='Automatically Voice Muted', reason='Moved voice channels 30+ times', ))
                optional_content = ':radioactive::radioactive: `(VC Ban Applied)` '
                member_roles = [vc_muted_role] + member.roles
                try:
                    await member.edit(mute=True)
                except:
                    pass
                if not ROLES['staff'] in [role.id for role in member.roles]: await member.edit(roles = member_roles) 
            else:
                
                if vc_muted_role.id not in [role.id for role in member.roles]:
                    member_roles = [vc_muted_role] + member.roles
                    if not ROLES['staff'] in [role.id for role in member.roles]: await member.edit(roles = member_roles) 
                optional_content = ':radioactive::bangbang::radioactive:'
                
            if (before and before.channel) and (after and after.channel):
                await self.safe_send_message(self.get_channel(CHANS['vclog']), content='{} **{}** `{}` `VCLog` `{}` **{}#{}** `{}` → `{}`'.format(optional_content, self.voice_changes[member.id]['changes'], datetime.utcnow().strftime('%y.%m.%d %H:%M:%S'), member.mention, clean_string(member.name), member.discriminator, before.channel.name, after.channel.name))
            elif (before and before.channel):
                await self.safe_send_message(self.get_channel(CHANS['vclog']), content='{} **{}** `{}` `VCLog` `{}` **{}#{}** `{}` → `<Left Voice Chat>`'.format(optional_content, self.voice_changes[member.id]['changes'], datetime.utcnow().strftime('%y.%m.%d %H:%M:%S'), member.mention, clean_string(member.name), member.discriminator, before.channel.name))
            elif (after and after.channel):
                await self.safe_send_message(self.get_channel(CHANS['vclog']), content='{} **{}** `{}` `VCLog` `{}` **{}#{}** `<Joined Voice Chat>` → `{}`'.format(optional_content, self.voice_changes[member.id]['changes'], datetime.utcnow().strftime('%y.%m.%d %H:%M:%S'), member.mention, clean_string(member.name), member.discriminator, after.channel.name))
            if staff_role:
                await role.edit(mentionable=False)

            # LFG VC Tracking
            if (before and before.channel):
                # if self.lfg_vc_debug: print(f"EVENT: tracking change in {before.channel.name}")
                if member.id in self.vc_num_locks:
                    await before.channel.edit(user_limit=5)
                    self.vc_num_locks.pop(member.id, None)

    async def on_message(self, message, edit=False):
        if not self.use_new_modmail:
            if message.channel.id == CHANS['modmail']:
                self.last_modmail_poster = message.author.id
            
        if message.author == self.user:
            return
        if (self.role_ping_toggle['game'] or self.role_ping_toggle['server']) and message.role_mentions:
            if self.role_ping_toggle['game'] and self.role_ping_toggle['game'] in message.role_mentions:
                await self.role_ping_toggle['game'].edit(mentionable=False)
                self.role_ping_toggle['game'] = None
            elif self.role_ping_toggle['server'] and self.role_ping_toggle['server'] in message.role_mentions:
                await self.role_ping_toggle['server'].edit(mentionable=False)
                self.role_ping_toggle['server'] = None
        if not self.use_new_modmail:
            if self.last_modmail_poster == self.user.id: 
                self.divider_content = '__                                                                                                          __\n\n'
            else:
                self.divider_content = ''

        if isinstance(message.channel, discord.abc.PrivateChannel):
            print('pm')
            if message.author.id in self.anti_spam_modmail_list and self.anti_spam_modmail_list[message.author.id]["blocked"]:
                if datetime.utcnow() - timedelta(minutes=30) < self.anti_spam_modmail_list[message.author.id]["last_message"]:
                    self.anti_spam_modmail_list[message.author.id]["last_message"] = datetime.utcnow()
                    self.anti_spam_modmail_list[message.author.id]["count"] += 1
                    return
                    
                self.anti_spam_modmail_list[message.author.id]["last_message"] = datetime.utcnow()
                self.anti_spam_modmail_list[message.author.id]["count"] = 1
                self.anti_spam_modmail_list[message.author.id]["blocked"] = False
                
            if message.author.id in [member.id for member in discord.utils.get(self.guilds, id=SERVERS['main']).members] and len(discord.utils.get(discord.utils.get(self.guilds, id=SERVERS['main']).members, id=message.author.id).roles) < 2 and message.author.id not in self.anti_stupid_modmail_list:
                await self.safe_send_message(message.author, content=f"I noticed you\'re attempting to send the staff a mod mail but have no roles, if this is your issue __**PLEASE**__ make sure to review the message you recieved when you joined __along__ with reading over <#{CHANS['rules']}>! If this didn\'t help, please resend your original message!")
                if not self.use_new_modmail: await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+'→ I sent a message to {}({}) to remind them to read the welcome DM as they attempted to DM me without any roles'.format(message.author.mention, message.author.id))
                self.anti_stupid_modmail_list.append(message.author.id)
                return
                
            if message.author.id in self.anti_spam_modmail_list:
                if datetime.utcnow() - timedelta(seconds=2) < self.anti_spam_modmail_list[message.author.id]["last_message"]:
                    self.anti_spam_modmail_list[message.author.id]["last_message"] = datetime.utcnow()
                    self.anti_spam_modmail_list[message.author.id]["count"] += 1
                else:
                    self.anti_spam_modmail_list[message.author.id]["last_message"] = datetime.utcnow()
                    self.anti_spam_modmail_list[message.author.id]["count"] = 1
                if self.anti_spam_modmail_list[message.author.id]["count"] > 4:
                    self.anti_spam_modmail_list[message.author.id]["blocked"] = True
                    await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+'→ I\'ve blocked {}({}) from sending me any more mod mail as they spammed me.'.format(message.author.mention, message.author.id))
            else:
                self.anti_spam_modmail_list[message.author.id] = {"last_message": datetime.utcnow(), "count": 1, "blocked": False}
            if not edit:
                try:
                    await self.safe_send_message(message.author, content='Thank you for your message! Our mod team will reply to you as soon as possible.')
                except:
                    print('ERROR: Cannot send message to user {} ({}#{})'.format(message.author.mention, message.author.name, message.author.discriminator))
                    
            if not message.content: 
                msg_content = '-No content-'
            else:
                msg_content = message.clean_content
                
            if message.attachments:
                msg_attachments = '\n~Attachments: {}'.format(', '.join([attachment.url for attachment in message.attachments]))
            else:
                msg_attachments = ''
                
            if message.author.id in [member.id for member in discord.utils.get(self.guilds, id=SERVERS['ban']).members] and message.author.id not in [member.id for member in discord.utils.get(self.guilds, id=SERVERS['main']).members]:
                msg_alert = '\n**__WARNING: USER IN BANNED SERVER__**'
            elif message.author.id in self.serious_d_blacklist:
                msg_alert = '\n**__WARNING: USER IN SERIOUS DISCUSSION BLACKLIST__**'
            else:
                msg_alert = ''
                
            if edit:
                msg_edit = 'EDITED MSG '
            else:
                msg_edit = ''
                
            if message.author.id in self.mod_mail_db:
                self.mod_mail_db[message.author.id]['messages']['{}'.format(datetime_to_utc_ts(datetime.now()))] = {'content': '{}{}'.format(msg_content, msg_attachments), 'modreply': None}
                self.mod_mail_db[message.author.id]['answered'] = False
            else:
                self.mod_mail_db[message.author.id] = {'answered': False,'messages': {'{}'.format(datetime_to_utc_ts(datetime.now())): {'modreply': None,'content': '{}\n~ATTACHMENT:{}'.format(msg_content, ', '.join([attachment.url for attachment in message.attachments]))}}}
            if not self.use_new_modmail: await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+'**{edited_alert}From:** *{mention}*:\n```{message_content}```{attachment_info}{alert_info}\nReply ID: `{author_id}`'.format(edited_alert = msg_edit,
                                                                                                                                                                                                                                        mention = message.author.mention,
                                                                                                                                                                                                                                        message_content = msg_content,
                                                                                                                                                                                                                                        attachment_info = msg_attachments,
                                                                                                                                                                                                                                        alert_info =  msg_alert,
                                                                                                                                                                                                                                        author_id = message.author.id))
            write_json('modmaildb.json', self.mod_mail_db)
            return
        else:
            if message.channel.id not in self.messages_log:
                self.messages_log[message.channel.id] = {message.id: {'content': message.content, 'author': message.author.id}}
            else:
                self.messages_log[message.channel.id][message.id] = {'content': message.content, 'author': message.author.id}
                
        if isinstance(message.author, discord.User):
            return
            
        try:
            this = [role for role in message.author.roles if role.id  in [ROLES['staff'], ROLES['bots']]]
        except:
            message.author.roles = [role for role in message.author.roles if role is not None]
            
        if [role for role in message.author.roles if role.id  in [ROLES['staff'], ROLES['bots']]]:
            pass
        elif message.channel.id in TEAM_CHANS:
            if len(message.content) < 60 or [mention.id for mention in message.mentions if mention.id is not message.author.id]:
                    await self.safe_delete_message(message)
                    msg_to_send = MSGS['msg_content_error'].format(message.channel.mention)
                    if message.author.id in self.mod_mail_db:
                        self.mod_mail_db[message.author.id]['messages']['{}'.format(datetime_to_utc_ts(datetime.now()))] = {'content': msg_to_send, 'modreply': self.user.id}
                        self.mod_mail_db[message.author.id]['answered'] = True
                    else:
                        self.mod_mail_db[message.author.id] = {'answered': True, 'messages': {'{}'.format(datetime_to_utc_ts(datetime.now())): {'modreply': self.user.id,'content': msg_to_send}}}

                    await self.safe_send_message(message.author, content=msg_to_send)
                    if not self.use_new_modmail: await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='for sending some dumb shit in teams that was shorter than 60 chars or had a mention'))
                    await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=message.author.name, discrim=message.author.discriminator ,id=message.author.id, action='Deleted Message', reason='Sent some dumb shit in teams that was shorter than 60 chars or had a mention.', optional_content='Message sent in {}: `{}`\n'.format(message.channel.mention, message.clean_content)))
        
        elif message.channel.id in SCRIM_CHANS:
            if [mention.id for mention in message.mentions if mention.id is not message.author.id]:
                    await self.safe_delete_message(message)
                    msg_to_send = MSGS['msg_content_error'].format(message.channel.mention)
                    if message.author.id in self.mod_mail_db:
                        self.mod_mail_db[message.author.id]['messages']['{}'.format(datetime_to_utc_ts(datetime.now()))] = {'content': msg_to_send, 'modreply': self.user.id}
                        self.mod_mail_db[message.author.id]['answered'] = True
                    else:
                        self.mod_mail_db[message.author.id] = {'answered': True, 'messages': {'{}'.format(datetime_to_utc_ts(datetime.now())): {'modreply': self.user.id,'content': msg_to_send}}}

                    await self.safe_send_message(message.author, content=msg_to_send)
                    if not self.use_new_modmail: await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='for mentioning someone in lf scrims'))
                    await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=message.author.name, discrim=message.author.discriminator ,id=message.author.id, action='Deleted Message', reason='mentioned someone in lf scrims', optional_content='Message sent in {}: `{}`\n'.format(message.channel.mention, message.clean_content)))
        
        elif message.channel.id in LFG_CHANS:
            if len(message.content) > 200 :
                    await self.safe_delete_message(message)
                    msg_to_send = MSGS['msg_content_error'].format(message.channel.mention)
                    if message.author.id in self.mod_mail_db:
                        self.mod_mail_db[message.author.id]['messages']['{}'.format(datetime_to_utc_ts(datetime.now()))] = {'content': msg_to_send, 'modreply': self.user.id}
                        self.mod_mail_db[message.author.id]['answered'] = True
                    else:
                        self.mod_mail_db[message.author.id] = {'answered': True, 'messages': {'{}'.format(datetime_to_utc_ts(datetime.now())): {'modreply': self.user.id,'content': msg_to_send}}}

                    await self.safe_send_message(message.author, content=msg_to_send)
                    if not self.use_new_modmail: await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='for sending some dumb shit in lfg that was longer than 200 chars'))
                    await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=message.author.name, discrim=message.author.discriminator ,id=message.author.id, action='Deleted Message', reason='Sent some dumb shit in lfg that was longer than 200 chars', optional_content='Message sent in {}: `{}`\n'.format(message.channel.mention, message.clean_content)))
        
        # I don't feel like fixing all these IDs, they're all the staff channels just pretend I actually did the work pls.
        if not message.author.bot and message.channel.id not in [269519917693272074, 290274342904922112, 282076089927598081, 282076117651947520, 269566972977610753, 282076329829072897, 269567077805719552, 282076628153139200, 282076615784136705, 282076800698548224, 282076856201510914, 282076300838043648, 290428366312701962, 290428522080763904, 290428554968301569, 290428408465195008, 290428617773678592, 290428645883772928]:
            if re.search(REGEX['uplay'], message.content, re.IGNORECASE):
                em = discord.Embed(description='**Noteworthy mention found in %s:**' % message.channel.mention, colour=discord.Colour(0x9d9bf4), timestamp=datetime.utcnow())
                em.set_author(name="𝅳𝅳𝅳", icon_url="https://i.imgur.com/TVlATNp.png")
                history = reversed(await message.channel.history(limit=4, before=message).flatten())
                for msg in history:
                    em.add_field(name="~~                    ~~", value='**%s**:\n%s' % (msg.author.mention, msg.content), inline=False)
                em.add_field(name="~~                    ~~", value='**%s**:\n%s' % (message.author.mention, message.content), inline=False)
                await self.safe_send_message(self.get_channel(CHANS['ubireports']), embed=em)
                
        if not message.author.bot and not [role for role in message.author.roles if role.id  in [ROLES['staff'], ROLES['bots']]] and message.channel.id not in [CHANS['star']]:
            drama_matches = re.search(REGEX['drama'], message.content, re.IGNORECASE)
            dox_matches = re.search(REGEX['dox'], message.content, re.IGNORECASE)
            sent_msg = None
            if message.id in [self.watched_messages[msg]['message_id'] for msg in self.watched_messages]:
                if not drama_matches and not dox_matches:
                    await self.safe_send_message(self.get_channel(CHANS['drama']), content='{}#{} has edited away the past potentially drama inducing item'.format(message.author.name, message.author.discriminator))
                else:
                    for msg_id, msg_dict in self.watched_messages.items():
                        if msg_dict['message_id'] == message.id:
                            await self.safe_delete_message(await self.get_channel(466756995517775872).fetch_message(msg_id))
            if drama_matches:
                em = discord.Embed(description=f"**Potential Drama found in {message.channel.mention}** - [Click Here]({message.jump_url}) to jump", colour=discord.Colour(0xffff00), timestamp=datetime.utcnow())
                em.set_author(name="𝅳𝅳𝅳", icon_url="https://i.imgur.com/TVlATNp.png")
                history = reversed(await message.channel.history(limit=4, before=message).flatten())
                for msg in history:
                    em.add_field(name="~~                    ~~", value='**%s**:\n%s' % (msg.author.mention, msg.content), inline=False)
                msg_value = message.content[:drama_matches.start()] + '**__' + message.content[drama_matches.start():drama_matches.end()] + '__**' + message.content[drama_matches.end():]
                em.add_field(name="~~                    ~~", value='**%s**:\n%s' % (message.author.mention, msg_value), inline=False)
                sent_msg = await self.safe_send_message(self.get_channel(CHANS['drama']), embed=em)
            if dox_matches:
                em = discord.Embed(ddescription=f"**Potential DOXXING found in {message.channel.mention}** - [Click Here]({message.jump_url}) to jump", colour=discord.Colour(0xff0000), timestamp=datetime.utcnow())
                em.set_author(name="𝅳𝅳𝅳", icon_url="https://i.imgur.com/ozWtGXL.png")
                history = reversed(await message.channel.history(limit=4, before=message).flatten())
                for msg in history:
                    em.add_field(name="~~                    ~~", value='**%s**:\n%s' % (msg.author.mention, msg.content), inline=False)
                msg_value = message.content[:dox_matches.start()] + '**__' + message.content[dox_matches.start():dox_matches.end()] + '__**' + message.content[dox_matches.end():]
                em.add_field(name="~~                    ~~", value='**%s**:\n%s' % (message.author.mention, msg_value), inline=False)
                sent_msg = await self.safe_send_message(self.get_channel(CHANS['drama']),  embed=em)
            if sent_msg:
                self.watched_messages[sent_msg.id] = {'author_id': message.author.id, 'message_id': message.id, 'channel_id': message.channel.id}
                reactions = [emote for emote in self.emojis if emote.id in [REACTS['delete'], REACTS['mute'],REACTS['24mute'], REACTS['48mute'], REACTS['check'], REACTS['ban']]]
                for reaction in reactions:
                    await asyncio.sleep(1)
                    await sent_msg.add_reaction(reaction)

        if not message.author.bot and not [role for role in message.author.roles if role.id  in [ROLES['staff'], ROLES['bots']]]:
            mutedrole = discord.utils.get(message.guild.roles, id=ROLES['muted'])
            if len(message.mentions) > 9 and not [item for item in message.content.strip().split() if item not in [msg_author.mention for msg_author in message.mentions]]:
                print(f"9 mention spam broken by {message.author.name}, banning")
                try:
                    await self.safe_send_message(message.author, content=MSGS['banmsg'])
                except:
                    pass
                await self.http.ban(message.author.id, message.guild.id, 0)
                await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=message.author.name, optional_content='', discrim=message.author.discriminator ,id=message.author.id, action='Banned user', reason='Mention Spam in excess of 10 mentions per message'))
            elif len(message.mentions) > 4:
                print(f"4 mention spam broken by {message.author.name}, muting")
                try:
                    await message.author.edit(roles = list(set(([role for role in message.author.roles if role.id not in UNPROTECTED_ROLES] + [mutedrole]))))
                    try:
                        await message.author.edit(mute=True)
                    except:
                        pass
                except:
                    pass
                self.muted_dict[message.author.id] = None
                await self.safe_send_message(message.author, content=MUTED_MESSAGES['plain'].format(rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=message.author.name, optional_content='', discrim=message.author.discriminator ,id=message.author.id, action='Muted user', reason='Mention Spam in excess of 5 mentions per message'))
                await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='as they were muted'))
            elif len(message.mentions) > 2 and message.author.id in self.mention_spam_watch and not edit:
                if datetime.utcnow() - timedelta(minutes=30) < self.mention_spam_watch[message.author.id]:
                    print(f"2x Spam Watch broken by {message.author.name}, muting")
                    try:
                        await message.author.edit(roles = list(set(([role for role in message.author.roles if role.id not in UNPROTECTED_ROLES] + [mutedrole]))))
                        try:
                            await message.author.edit(mute=True)
                        except:
                            pass
                    except:
                        pass
                    self.muted_dict[message.author.id] = None
                    await self.safe_send_message(message.author, content=MUTED_MESSAGES['plain'].format(rules=CHANS['rules'], muted=CHANS['muted']))
                    await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=message.author.name, optional_content='', discrim=message.author.discriminator ,id=message.author.id, action='Muted user', reason='Mention Spam in excess of 3 mentions per message more than once'))
                    await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='as they were muted'))
                else:
                    self.mention_spam_watch[message.author.id] = datetime.utcnow()
            elif len(message.mentions) > 2:
                print(f"Spam watching {message.author.name}")
                self.mention_spam_watch[message.author.id] = datetime.utcnow()

            
        message_content = message.content.strip()
        
        for item in message.content.strip().split():
            try:
                if 'discord.gg' in item or 'discordapp.com/invite' in item:
                    invite = await self.fetch_invite(item)
                    print(f"invite ID - {invite.guild.id}")
                    if invite.guild.id not in self.guild_whitelist:
                        if not [role for role in message.author.roles if role.id  in [ROLES['staff'], ROLES['bots']]]:
                            await self.safe_delete_message(message)
                            print('detected illegal invite from {}:{}\t{}'.format(message.author.name, message.author.id, item))
                            msg_to_send = 'I\'ve deleted your message in {} since I detected an invite url in your message! Please remember not to advertise servers not approved by staff!'.format(message.channel.mention)
                            if message.author.id in self.mod_mail_db:
                                self.mod_mail_db[message.author.id]['messages']['{}'.format(datetime_to_utc_ts(datetime.now()))] = {'content': msg_to_send, 'modreply': self.user.id}
                                self.mod_mail_db[message.author.id]['answered'] = True
                            else:
                                self.mod_mail_db[message.author.id] = {'answered': True, 'messages': {'{}'.format(datetime_to_utc_ts(datetime.now())): {'modreply': self.user.id,'content': msg_to_send}}}

                            await self.safe_send_message(message.author, content=msg_to_send)
                            if not self.use_new_modmail: await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='for sending discord invites'))
                            await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=message.author.name, action='Deleted discord invite', discrim=message.author.discriminator ,id=message.author.id, reason='Sent a nonwhitelisted invite url ({} : {})'.format(item, invite.guild.id), optional_content='Message sent in {}: `{}`\n'.format(message.channel.mention, message.clean_content)))
                            return
            except:
                pass
        
        if [role for role in message.author.roles if role.id == ROLES['muted']]:
            if message.content != '!timeleft':
                return
        
        if not message_content.startswith(self.prefix) or edit:
            if message.channel.id in list(self.slow_mode_dict.keys()):
                time_out = self.slow_mode_dict[message.channel.id]['time_between']
                if self.slow_mode_debug: print(f"putting {message.author.name} in slow mode for {time_out} seconds in no command method")
                channel_muted_role = self.slow_mode_dict[message.channel.id]['channel_muted_role']
                if self.slow_mode_debug: print(f"adding role...")
                await message.author.add_roles(channel_muted_role)
                if self.slow_mode_debug: print(f"role added")
                await asyncio.sleep(time_out)
                if self.slow_mode_debug: print(f"removing role...")
                await message.author.remove_roles(channel_muted_role)
                if self.slow_mode_debug: print(f"role removed")
            return
        try:
            command, *args = shlex.split(message.content.strip())
            command, *raw_args = message.content.strip().split()
        except:
            command, *args = message.content.strip().split()
            command, *raw_args = message.content.strip().split()
        command = command[len(self.prefix):].lower().strip()
        
        
        handler = getattr(self, 'cmd_%s' % command, None)
        if not handler:
            class_name = message.content.strip()[1:]
            if class_name.startswith('['):
                class_name = class_name.replace('[', '').replace(']', '')
            if class_name.lower() in ROLE_ALIASES:
                role = discord.utils.get(message.guild.roles, id=ROLE_ALIASES[class_name.lower()])
            else:
                role = discord.utils.get(message.guild.roles, name=class_name.lower())
            if  role and message.channel.id  in [CHANS['genbotspam'], CHANS['registration']]:
                author_roles = message.author.roles
                mod_check = [role for role in author_roles if role.id not in UNPROTECTED_ROLES]
                author_roles.append(role)
                if not ROLES['staff'] in [role.id for role in message.author.roles]: await message.author.edit(roles = author_roles)
                await self.safe_send_message(message.channel, content='%s, you now are marked with the role `%s`!' % (message.author.mention, role.name), expire_in=15)
                print("[Command] {0.id}/{0.name} ({1})".format(message.author, message_content))
        
            if message.channel.id in list(self.slow_mode_dict.keys()):
                time_out = self.slow_mode_dict[message.channel.id]['time_between']
                channel_muted_role = self.slow_mode_dict[message.channel.id]['channel_muted_role']
                await message.author.add_roles(channel_muted_role)
                await asyncio.sleep(time_out)
                await message.author.remove_roles(channel_muted_role)
                return
                
            tag_name = class_name.lower()
            if tag_name in self.tags:
                if self.tags[tag_name][0]:
                    tag_flags = self.tags[tag_name][0].split()
                    # Channel Restriction Parsing
                    acceptable_chans = []
                    for item in tag_flags:
                        if item.isdigit() and message.guild.get_channel(int(item)):
                            chan = message.guild.get_channel(int(item))
                            if isinstance(chan, discord.CategoryChannel):
                                acceptable_chans = acceptable_chans + [cat_chan.id for cat_chan in chan.text_channels]
                            else:
                                acceptable_chans.append((message.guild.get_channel(int(item))).id)
                    if message.channel.id not in acceptable_chans and len(acceptable_chans) > 0:
                        await self.safe_send_message(message.channel, content=f'Tag cannot be used outside of {", ".join([f"<#{chan}>" for chan in acceptable_chans])}', expire_in=20)
                        return
                        
                    # Eval Checking
                    if "unrestricted_eval" in tag_flags:
                        resp = await self.cmd_eval(message.author, message.guild, message, message.channel, message.mentions, self.tags[tag_name][1], is_origin_tag=True)
                        if resp:
                            await self.safe_send_message(message.channel, content=clean_bad_pings(resp))
                        return
                    elif "restrict" in tag_flags and not [role for role in message.author.roles if role.id  in [ROLES['staff'], ROLES['tagmaster']]]:
                        return
                    elif "eval" in tag_flags:
                        resp = await self.cmd_eval(message.author, message.guild, message, message.channel, message.mentions, self.tags[tag_name][1], is_origin_tag=True)
                        if resp:
                            await self.safe_send_message(message.channel, content=clean_bad_pings(resp))
                        return
                        
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
                if message.channel.id in list(self.slow_mode_dict.keys()):
                    time_out = self.slow_mode_dict[message.channel.id]['time_between']
                    channel_muted_role = self.slow_mode_dict[message.channel.id]['channel_muted_role']
                    await message.author.add_roles(channel_muted_role)
                    await asyncio.sleep(time_out)
                    await message.author.remove_roles(channel_muted_role)
                return

            response = await handler(**handler_kwargs)
            if response and isinstance(response, Response):
                content = response.content
                if response.reply:
                    content = '%s, %s' % (message.author.mention, content)
                    
                if response.delete_invoking:
                    await self.safe_delete_message(message)
                    
                if response.delete_after > 0:
                    sentmsg = await self.safe_send_message(message.channel, content=content, expire_in=response.delete_after)
                else:
                    sentmsg = await self.safe_send_message(message.channel, content=content)
                    
        except CommandError as e:
            await self.safe_send_message(message.channel, content='```\n%s\n```' % e.message, expire_in=15)

        except:
            await self.safe_send_message(message.channel, content='```\n%s\n```' % traceback.format_exc(), expire_in=60)
            traceback.print_exc()
        
        if message.channel.id in list(self.slow_mode_dict.keys()):
            time_out = self.slow_mode_dict[message.channel.id]['time_between']
            channel_muted_role = self.slow_mode_dict[message.channel.id]['channel_muted_role']
            await message.author.add_roles(channel_muted_role)
            await asyncio.sleep(time_out)
            await message.author.remove_roles(channel_muted_role)

if __name__ == '__main__':
    bot = R6Bot()
    bot.run()
