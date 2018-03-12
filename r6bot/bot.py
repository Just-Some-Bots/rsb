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

from .constants import *
from .exceptions import CommandError
from discord.http import HTTPClient, Route
from .creds import BOT_TOKEN, TWITCH_CREDS, USER_TOKEN
from .utils import clean_string, write_json, load_json, clean_bad_pings, datetime_to_utc_ts, timestamp_to_seconds, strfdelta, _get_variable, snowflake_time, MemberConverter, UserConverter

# logger = logging.getLogger('discord')
# logger.setLevel(logging.INFO)
# handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
# handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
# logger.addHandler(handler)

class Response(object):
    def __init__(self, content, reply=False, delete_after=0):
        self.content = content
        self.reply = reply
        self.delete_after = delete_after

class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeError(message)

class R6Bot(discord.Client):
    def __init__(self):
        super().__init__(max_messages=50000)
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
        self.guild_whitelist = load_json('server_whitelist.json')
        self.twitch_watch_list = load_json('twitchwatchlist.json')
        self.muted_dict = {int(key): value for key, value in load_json('muted.json').items()}
        self.mod_mail_db = {int(key): value for key, value in load_json('modmaildb.json').items()}
        self.channel_bans = {int(key): value for key, value in load_json('channel_banned.json').items()}
        
        # Instance Storage (nothing saved between bot
        self.ban_list = {}
        self.voice_changes = {}
        self.twitch_is_live = {}
        self.slow_mode_dict = {}
        self.watched_messages = {}
        self.anti_stupid_modmail_list = []
        
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
        self.ready_check = False
        self.use_reactions = True
        
        # I separated these out from Constants because I wanted to ensure they could be easily found and changed.
        self.intro_msg = "Welcome to the official Rainbow6 Discord server, make sure to read <#{rules}>! You will need a role in order to chat and join voice channels. To obtain a role *(take note of the exclamation mark prefix)*:```!pc\n!xbox\n!ps4``` If you happen to run a Youtube or Twitch  channel w/ over 15k followers or work at Ubisoft, dm me (the bot) about it and the admins will get you set up with a fancy role!".format(rules=CHANS['rules'])
        self.dm_msg = "Hello and welcome to the official Rainbow6 Discord!\nPlease take a moment to review the rules in <#{rules}> and don't forget to assign yourself a role in <#{roleswap}> as you cannot use the text / voice channels until you do, if you have any further questions, simply message this bot back to send a mod mail to the server staff!".format(rules=CHANS['rules'], roleswap=CHANS['roleswap'])
        
        print('past init')

    # noinspection PyMethodOverriding
    def run(self):
        loop = asyncio.get_event_loop()
        try:
            loop.create_task(self.mod_mail_reminders())
            loop.create_task(self.backup_messages_log())
            loop.create_task(self.check_twitch_streams())
            loop.run_until_complete(self.start(self.token))
            loop.run_until_complete(self.connect())
        except Exception:
            for task in asyncio.Task.all_tasks():
                task.cancel()
        finally:
            loop.close()
            
    async def queue_timed_role(self, sec_time, user, timed_role, user_id):
        await asyncio.sleep(sec_time)
        if self.muted_dict[user_id]:
            datetime_timestamp = datetime.fromtimestamp(self.muted_dict[user_id])
            if datetime.utcnow() < datetime_timestamp:
                return
                print('Mute extended for {} for {} more seconds'.format(user.name if user != None else user_id, (datetime_timestamp - datetime.utcnow()).total_seconds()))
        else:
            return
        if not user:
            del self.muted_dict[user_id]
            write_json('muted.json', self.muted_dict)
            return
        user_roles = user.roles
        if timed_role in user_roles:
            user_roles.remove(timed_role)
            if not ROLES['staff'] in [role.id for role in user.roles]: await user.edit(roles = user_roles)
        await user.edit(mute=False)
        del self.muted_dict[user.id]
        write_json('muted.json', self.muted_dict)
            
            
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
        while True:
            await asyncio.sleep(10)
            for filename, contents in self.messages_log.items():
                try:
                    write_json('channel_logs/%s.json' % str(filename), contents)
                except:
                    pass
            await asyncio.sleep(590)
            
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
                    with aiohttp.ClientSession() as session:
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
        print(string_query)
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
                self.channel_bans[role.id] = [member.id for member in discord.utils.get(self.guilds, id=SERVERS['main']).members if role in member.roles]
                write_json('channel_banned.json', self.channel_bans)     
        print('Done!\n\nFinalizing User Login...')
        await self.user_http.static_login(self.user_token, bot=False)
        print('Done!\n\nDeserializing Mutes...')
        target_server = discord.utils.get(self.guilds, id=SERVERS['main'])
        mutedrole = discord.utils.get(target_server.roles, id=ROLES['muted'])
        temp_dict = dict(self.muted_dict)
        for user_id, timestamp in temp_dict.items():
            user = discord.utils.get(target_server.members, id=user_id)
            if user:
                try:
                    if not ROLES['staff'] in [role.id for role in user.roles]: await user.edit(roles = [mutedrole])
                    await user.edit(mute=True)
                except discord.Forbidden:
                    print('cannot add role to %s, permission error' % user.name)
            if timestamp:
                datetime_timestamp = datetime.fromtimestamp(timestamp)
                if datetime.utcnow() < datetime_timestamp:
                    asyncio.ensure_future(self.queue_timed_role((datetime_timestamp-datetime.utcnow()).total_seconds(), user, mutedrole, user_id))
                    print('Queueing serialized mute for {} for {} seconds'.format(user.name if user != None else user_id, (datetime_timestamp - datetime.utcnow()).total_seconds()))
                else:
                    asyncio.ensure_future(self.queue_timed_role(0, user, mutedrole, user_id))
                    print('Serialized mute period has passed for {}'.format(user.name if user != None else user_id))
                
        
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

    async def safe_edit_message(self, message, *, new_content=None, expire_in=0, send_if_fail=False, quiet=False, embed=None):
        msg = None
        try:
            if not embed:
                await message.edit(new_content=new_content)
                msg = message
            else:
                await message.edit(new_content=new_content, embed=embed)
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
            
    def mods_only(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            orig_msg = _get_variable('message')

            if [role for role in orig_msg.author.roles if role.id  in [ROLES['staff']]]:
                # noinspection PyCallingNonCallable
                return await func(self, *args, **kwargs)
            else:
                return

        wrapper.mod_cmd = True
        return wrapper
        
    @mods_only
    async def cmd_whitelistserver(self, author, server_id):
        """
        Usage: {command_prefix}whitelistserver server_id
        Adds a server's id to the whitelist!
        """
        if server_id not in self.guild_whitelist:
            self.guild_whitelist.append(server_id)
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
        Usage: {command_prefix}changegame ["new game name"]
        Changes the "Now Playing..." game on Discord!
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
        return Response('I\'ve removed all platform roles from you!', reply=True, delete_after=15)
    
    @mods_only
    async def cmd_eval(self, author, guild, message, channel, mentions, code):
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

        stdout = StringIO()

        to_compile = 'async def func():\n{}'.format(textwrap.indent(code, "  "))

        try:
            exec(to_compile, env)
        except Exception as e:
            return Response('```py\n{}: {}\n```'.format(e.__class__.__name__, e))

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            return Response('```py\n{}{}\n```'.format(value, traceback.format_exc()))
        else:
            value = stdout.getvalue()
            try:
                await message.add_reaction('\u2705')
            except:
                pass

            if ret is None:
                if value:
                    return Response('```py\n{}\n```'.format(value))
            else:
                self._last_result = ret
                return Response('```py\n{}{}\n```'.format(value, ret))

    @mods_only
    async def cmd_changegame(self, author, string_game):
        """
        Usage: {command_prefix}changegame ["new game name"]
        Changes the "Now Playing..." game on Discord!
        """
        await self.change_presence(game=discord.Game(name=string_game))
        return Response(':thumbsup:', reply=True)
        
    async def cmd_tag(self, message, author, channel, mentions, leftover_args):
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
                        if not [role for role in author.roles if role.id  in [ROLES['staff']]]:
                            return Response('Tag cannot be used by nonstaff members')
                    return Response(clean_bad_pings(self.tags[tag][1]))
            raise CommandError('Tag doesn\'t exist')
    
    async def cmd_id(self, message, author, guild):
        """
        Usage: {command_prefix}ping
        Replies with "PONG!"; Use to test bot's responsiveness
        """
        if message.channel.id != CHANS['genbotspam']:
            return
        return Response('Your ID is `{}`!'.format(author.id), reply=True)
    
    async def cmd_staff(self, message, channel, author, guild):
        """
        Usage: {command_prefix}ping
        Replies with "PONG!"; Use to test bot's responsiveness
        """
        check_msg = await self.safe_send_message(channel, content='Please remember to *only* tag staff for things that **absolutely** require **immediate** attention and can only be addressed by server administration.\n\nFor non-immediate topics, *please* send a private message to <@!278980093102260225> to send mod-mail to the administration.\n\nPlease react if you still wish to ping the staff')
        await check_msg.add_reaction('✅')
        def check(reaction, user):
            e = str(reaction.emoji)
            if user == author and reaction.message.id == message.id:
                return e.startswith(('✅'))
            else:
                return False
        try:
            reac, user = await self.wait_for('reaction_add', check=check, timeout=300)
        except:
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
                            dedent(cmd.__doc__)
                        ).format(command_prefix=self.prefix),
                        delete_after=60
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

                return Response(helpmsg, reply=True, delete_after=60)
        else:
            if command:
                cmd = getattr(self, 'cmd_' + command, None)
                if cmd and not hasattr(cmd, 'mod_cmd'):
                    return Response(
                        "```\n{}```".format(
                            dedent(cmd.__doc__)
                        ).format(command_prefix=self.prefix),
                        delete_after=60
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

                return Response(helpmsg, reply=True, delete_after=60)
            
    @mods_only  
    async def cmd_check(self, message, mentions, author, guild, leftover_args):
        """
        Usage: TELL RHINO TO ADD THIS
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
    async def cmd_removestream(self, author, channel_name):
        """
        Usage {command_prefix}addstream [twitch channel name]
        Adds the stream to the checks for online streams
        """
        if channel_name in self.twitch_watch_list:
            self.twitch_watch_list.remove(channel_name)
            write_json('twitchwatchlist.json', self.twitch_watch_list)
            return Response(':thumbsup:')
        else:
            raise ComamandError('ERROR: Channel not in watch list')

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
        Fetches the help info for the bot's commands
        """
        chan_mention = message.channel_mentions[0]
        leftover_args = leftover_args[1:]
        await self.safe_send_message(chan_mention, content=' '.join(leftover_args))
        return Response(':thumbsup:')

    @mods_only
    async def cmd_markread(self, author, guild,  auth_id):
        """
        Usage {command_prefix}echo #channel "ENTER MESSAGE HERE"
        Fetches the help info for the bot's commands
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
        Usage {command_prefix}echo #channel "ENTER MESSAGE HERE"
        Fetches the help info for the bot's commands
        """
        auth_id = int(auth_id)
        if auth_id not in self.mod_mail_db:
            raise CommandError('ERROR: User ID not found in Mod Mail DB')
        quick_switch_dict = {}
        quick_switch_dict[auth_id] = {'embed': discord.Embed(), 'member_obj': await self.get_user_info(auth_id)}
        quick_switch_dict[auth_id]['embed'].set_author(name='{}({})'.format(quick_switch_dict[auth_id]['member_obj'].name, quick_switch_dict[auth_id]['member_obj'].id), icon_url=quick_switch_dict[auth_id]['member_obj'].avatar_url)
        
        current_index = 0
        current_msg = None
        message_dict = collections.OrderedDict(sorted(self.mod_mail_db[auth_id]['messages'].items(), reverse=True))
        loop_dict = quick_switch_dict
        while True:
            od = collections.OrderedDict(islice(message_dict.items(),current_index, current_index+20))
            od = collections.OrderedDict(reversed(list(od.items())))
            for timestamp, msg_dict in od.items():
                user = None
                if msg_dict['modreply'] is not None:
                    try:
                        user = discord.utils.get(guild.members, id=msg_dict['modreply']).name
                    except:
                        user = await self.get_user_info(msg_dict['modreply'])
                        user = user.name
                else:
                    user = loop_dict[auth_id]['member_obj'].name
                if len(msg_dict['content']) > 1020:
                    msg_dict['content'] = msg_dict['content'][:1020] + '...'
                loop_dict[auth_id]['embed'].add_field(name='{} | *{}*'.format(user, datetime.utcfromtimestamp(float(timestamp)).strftime('%H:%M %d.%m.%y' )), value=msg_dict['content'], inline=False)
            if not current_msg:
                current_msg = await self.safe_send_message(channel, embed=loop_dict[auth_id]['embed'])
            else:
                current_msg = await self.safe_edit_message(current_msg, embed=loop_dict[auth_id]['embed'])
            
            if current_index != 0:
                await current_msg.add_reaction('⬅')
            await current_msg.add_reaction('ℹ')
            if (current_index+1) != len(quick_switch_dict):
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
                await self.safe_send_message(current_msg.channel, content=loop_dict[auth_id]['member_obj'].id)
            elif str(reac.emoji) == '➡' and current_index != len(quick_switch_dict):
                current_index+=1
                await current_msg.remove_reaction(reac.emoji, user)
            elif str(reac.emoji) == '⬅' and current_index != 0:
                current_index-=1
                await current_msg.remove_reaction(reac.emoji, user)
            else:
                return
            await current_msg.clear_reactions()
        
    @mods_only
    async def cmd_mmqueue(self, author, channel, guild):
        """
        Usage {command_prefix}echo #channel "ENTER MESSAGE HERE"
        Fetches the help info for the bot's commands
        """
        unanswered_threads = [member_id for member_id in self.mod_mail_db if not self.mod_mail_db[member_id]['answered']]
        if not unanswered_threads:
            return Response('Everything is answered!')
        quick_switch_dict = {}
        for member_id in unanswered_threads:
            quick_switch_dict[member_id] = {'embed': discord.Embed(), 'member_obj': await self.get_user_info(member_id)}
            quick_switch_dict[member_id]['embed'].set_author(name='{}({})'.format(quick_switch_dict[member_id]['member_obj'].name, quick_switch_dict[member_id]['member_obj'].id), icon_url=quick_switch_dict[member_id]['member_obj'].avatar_url)
            od = collections.OrderedDict(sorted(self.mod_mail_db[member_id]['messages'].items(), reverse=True))
            od = collections.OrderedDict(islice(od.items(), 20))
            od = collections.OrderedDict(reversed(list(od.items())))
            for timestamp, msg_dict in od.items():
                user = None
                if msg_dict['modreply'] is not None:
                    user = (await self.get_user_info(msg_dict['modreply'])).name
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
    async def cmd_modmail(self, author, guild, auth_id, leftover_args):
        """
        Usage {command_prefix}echo #channel "ENTER MESSAGE HERE"
        Fetches the help info for the bot's commands
        """
        auth_id = int(auth_id)
        member = discord.utils.get(guild.members, id=auth_id)
        if not member:
            member = discord.utils.get(discord.utils.get(self.guilds, id=SERVERS['ban']).members, id=auth_id)
        if member:
            if leftover_args[0] == 'anon':
                msg_to_send = ' '.join(leftover_args[1:])
                await self.safe_send_message(member, content='**Admins:** {}'.format(msg_to_send))
                if member.id in self.mod_mail_db:
                    self.mod_mail_db[member.id]['messages']['{}'.format(datetime_to_utc_ts(datetime.now()))] = {'content': '(ANON){}'.format(msg_to_send), 'modreply': author.id}
                    self.mod_mail_db[member.id]['answered'] = True
                else:
                    self.mod_mail_db[member.id] = {'answered': True, 'messages': {'{}'.format(datetime_to_utc_ts(datetime.now())): {'modreply': author.id,'content': '(ANON){}'.format(msg_to_send)}}}

            else:
                msg_to_send = ' '.join(leftover_args)
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
    async def cmd_unmute(self, guild, author, mentions, leftover_args):
        """
        Usage {command_prefix}unmute [@mention OR User ID] <time>
        Unmutes ppl
        """
        if mentions:
            for user in mentions:
                leftover_args.pop(0)
        else:
            if len(leftover_args) == 2:
                user = discord.utils.get(guild.members, id=int(leftover_args.pop(0)))
                if user:
                    mentions = [user]
            if not mentions:
                raise CommandError('Invalid user specified')
        
        for user in mentions:
            try:
                if not ROLES['staff'] in [role.id for role in user.roles]: await user.edit(roles = [])
                await user.edit(mute=False)
                del self.muted_dict[user.id]
                write_json('muted.json', self.muted_dict)
            except discord.Forbidden:
                raise CommandError('Not enough permissions to mute user : {}'.format(user.name))
            except:
                traceback.print_exc()
                raise CommandError('Unable to mute user defined:\n{}\n'.format(user.name))
        return Response(':thumbsup:')
        
        
    @mods_only
    async def cmd_mute(self, guild, author, mentions, leftover_args):
        """
        Usage {command_prefix}mute [@mention OR User ID] <time>
        Mutes ppl
        """
        
        seconds_to_mute = None
        if mentions:
            for user in mentions:
                leftover_args.pop(0)
        else:
            if leftover_args:
                user = discord.utils.get(guild.members, id=int(leftover_args.pop(0)))
                if user:
                    mentions = [user]
                else:
                    raise CommandError('Invalid user specified')
            else:
                raise CommandError('No user specified')
                
        seconds_to_mute = timestamp_to_seconds(''.join(leftover_args))
        
        mutedrole = discord.utils.get(guild.roles, id=ROLES['muted'])
        if not mutedrole:
            raise CommandError('No Muted role created')
        for user in mentions:
            try:
                if not ROLES['staff'] in [role.id for role in user.roles]: await user.edit(roles = [mutedrole])
                await user.edit(mute=True)
            except discord.Forbidden:
                raise CommandError('Not enough permissions to mute user : {}'.format(user.name))
            except:
                traceback.print_exc()
                raise CommandError('Unable to mute user defined:\n{}\n'.format(user.name))
        response = ':thumbsup:'
        
        for user in mentions:
            if seconds_to_mute:
                muted_datetime = datetime.utcnow() + timedelta(seconds = seconds_to_mute)
                self.muted_dict[user.id] = muted_datetime.timestamp()
                print('user {} now timed muted'.format(user.name))
                await self.safe_send_message(user, content=MUTED_MESSAGES['timed'].format(time=' '.join(leftover_args), rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Muted user for {}'.format(' '.join(leftover_args)), reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                asyncio.ensure_future(self.queue_timed_role(seconds_to_mute, user, mutedrole, user.id))
                response += ' muted for %s seconds' % seconds_to_mute
            else:
                await self.safe_send_message(user, content=MUTED_MESSAGES['plain'].format(rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Muted user forever', reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
            await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=user.mention, id=user.id, reason='as they were muted'))

        return Response(response) 
        

    @mods_only
    async def cmd_slowmode(self, message, author, guild, channel_mentions, leftover_args):
        """
        Usage: {command_prefix}slowmode #channel <time between messages>
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
                    await self.slow_mode_dict[channel_mentions.id]['channel_muted_role'].delete_role()
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
                await slowed_channel.edit_channel_permissions(channel_muted_role, overwrite=overwrite)
                await self.safe_send_message(self.get_channel(channel_mentions.id), content='This channel is now in slow mode with a delay of **%s seconds**!' % seconds_to_slow)
                self.slow_mode_dict[channel_mentions.id] = {'time_between': seconds_to_slow,
                                                   'channel_muted_role': channel_muted_role}
            await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, discrim=user.discriminator ,id=user.id, optional_content='', action='Channel {} put in slow mode of {}'.format(channel_mentions.name, ' '.join(leftover_args[1:])), reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
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
            raise ComamandError('I do not have permissions to delete messages.')
        except discord.HTTPException as e:
            raise ComamandError(f'Error: {e} (try a smaller search?)')

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
            return Response(f'Successfully removed {deleted} messages.', delete_after=10) 
        else:
            return Response(to_send, delete_after=10) 

        
    @mods_only
    async def cmd_userinfo(self, guild, channel, author, mentions, leftover_args):
        """
        Usage {command_prefix}mute [@mention OR User ID] <time>
        Bans ppl
        """
        if not leftover_args:
            user = author
        else:
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
            em.add_field(name='Created On:', value='{} ({} ago)'.format(user.created_at.strftime('%c'), strfdelta(datetime.utcnow() - user.created_at)), inline=False)
            em.add_field(name='Joined On:', value='{} ({} ago)'.format(member.joined_at.strftime('%c'), strfdelta(datetime.utcnow() - member.joined_at)), inline=False)
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
            bans = [obj for obj in bans if obj.user.id == user.id]
            if bans:
                em.add_field(name='User Banned from Server:', value=f'Reason: {bans.reason}', inline=False)
                
        em.set_thumbnail(url=user.avatar_url)
        await self.safe_send_message(channel, embed=em)

    @mods_only
    async def cmd_ban(self, message, guild, author, mentions, raw_leftover_args):
        """
        Usage {command_prefix}mute [@mention OR User ID] <time>
        Bans ppl
        """
        converter = UserConverter()
        users = []
        ban_time = 0
        
        if raw_leftover_args and re.match(r'[0-7]', raw_leftover_args[-1]):
            ban_time = raw_leftover_args.pop()
        if mentions:
            for user in mentions:
                users.append(user)
        else:
            for item in raw_leftover_args:
                users.append(await converter.convert(message, self, item))
                
        for user in users:
            try:
                await self.safe_send_message(user, content=MSGS['banmsg'])
            except:
                pass
            try:
                await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Banned user', reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                await self.http.ban(user.id, guild.id, ban_time)
            except discord.Forbidden:
                raise CommandError('Not enough permissions to ban user : {}'.format(user.name))
            except:
                traceback.print_exc()
                raise CommandError('Unable to ban user defined:\n{}\n'.format(user.name))
        return Response(':thumbsup:')


    @mods_only
    async def cmd_softban(self, message, guild, author, mentions, raw_leftover_args):
        """
        Usage {command_prefix}mute [@mention OR User ID] <time>
        Bans ppl
        """
        converter = UserConverter()
        users = []
        ban_time = 7
        
        if raw_leftover_args and re.match(r'[0-7]', raw_leftover_args[-1]):
            ban_time = raw_leftover_args.pop()
        if mentions:
            for user in mentions:
                users.append(user)
        else:
            for item in raw_leftover_args:
                users.append(await converter.convert(message, self, item))
                
        for user in users:
            # Not sure if I actually wanna send ppl who were softbanned a msg since we don't do it for kicks.
            # Its implemented anyway if we decide otherwise
            # try:
                # await self.safe_send_message(user, content=MSGS['softbanmsg'])
            # except:
                # pass
            try:
                await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Softbanned user', reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
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
            em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user), colour=discord.Colour(0xFFFF00), timestamp=datetime.utcnow())
            em.set_author(name="𝅳𝅳𝅳User Edited Message in %s" % message.channel.mention, icon_url="https://i.imgur.com/NLpSnr2.png")
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
            em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user),colour=discord.Colour(0x305ebf), timestamp=datetime.utcnow())
            em.set_author(name="𝅳𝅳𝅳User's Message Deleted in <#%s>" % message['channel'], icon_url="https://i.imgur.com/MrrRQTo.png")
            em.set_thumbnail(url=user.avatar_url)
            if not message['content']:
                message['content'] = 'None!'
            if len(message['content']) > 1020:
                message['content'] = f'{message["content"][:1020]}...'
            em.add_field(name='Content: ', value=message['content'], inline=False)
            if after:
                em.add_field(name='ATTACHMENTS: ', value=', '.join([attachment.url for attachment in after]), inline=False)
                
        elif action == 'bulk_message_delete':
            actor = user
            author_dict = {msg.author: [] for msg in message}
            for msg in message:
                if msg.author in author_dict:
                    author_dict[msg.author].append(msg)
                else:
                    print('dumb fucking error in bulk delete action logging')
            for user, messages in author_dict.items():
                msgs_content = [f' - `{msg.content if len(msg.content) < 1020 else msg.content[:1020]+"..."}`{"ATTACHMENTS: ```" if msg.attachments else ""}{", ".join([attachment.url for attachment in msg]) if msg.attachments else ""}{"```" if msg.attachments else ""}\n' for msg in messages]
                em = discord.Embed(description='{0.mention} - `{0.name}#{0.discriminator} ({0.id})`'.format(user),colour=discord.Colour(0x305ebf), timestamp=datetime.utcnow())
                em.set_author(name=f"𝅳𝅳𝅳User's Messages Bulk Deleted in message[0].channel.mention by actor.mention", icon_url="https://i.imgur.com/RsOSopy.png")
                em.set_thumbnail(url=user.avatar_url)
                count = 1
                for msg_to_send in msgs_content:
                    if count < 21:
                        em.add_field(name=f'Message {count}', value=msg_to_send, inline=False)
                    count+=1
                if count > 20:
                    em.set_footer(icon_url='https://cdn.discordapp.com/emojis/414648560110403595.gif', text=f'along with {count-20} more messages.')
                    
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
        sent_msg = await self.safe_send_message(self.get_channel(CHANS['serverlog']), embed=em, file=file)
        
    async def on_raw_reaction_remove(self, emoji, message_id, channel_id, user_id):
        if not self.use_reactions: return
        if message_id in ROLE_REACT_MSGS:
            member = self.get_guild(SERVERS['main']).get_member(user_id)
            if emoji.id == REACTS['pc']:
                member_roles = discord.utils.get(member.guild.roles, id=ROLES['pc'])
                if member_roles:
                    await member.remove_roles(member_roles)
            if emoji.id  ==  REACTS['xbox']:
                member_roles = discord.utils.get(member.guild.roles, id=ROLES['xbox'])
                if member_roles:
                    await member.remove_roles(member_roles)
            if emoji.id  ==  REACTS['ps4']:
                member_roles = discord.utils.get(member.guild.roles, id=ROLES['ps4'])
                if member_roles:
                    await member.remove_roles(member_roles)
            if emoji.id  ==  REACTS['r6ping']:
                member_roles = discord.utils.get(member.guild.roles, id=ROLES['r6news'])
                if member_roles:
                    await member.remove_roles(member_roles)
            if emoji.id  ==  REACTS['invitationals']:
                member_roles = discord.utils.get(member.guild.roles, id=ROLES['invitationals'])
                if member_roles:
                    await member.remove_roles(member_roles)
            if emoji.id  ==  REACTS['serverping']:
                member_roles = discord.utils.get(member.guild.roles, id=ROLES['servernews'])
                if member_roles:
                    await member.remove_roles(member_roles)

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
    
    async def on_raw_message_delete(self, message_id, channel_id):
        if isinstance(self.get_channel(channel_id), discord.abc.PrivateChannel):
            return
        message = discord.utils.get(self._connection._messages, id=message_id)
        if message:
            hacky_code_dict = {'content': message.content, 'channel': message.channel.id}
            await self.log_action(message=hacky_code_dict, after=message.attachments, user=message.author, action='message_delete')
        else:
            if channel_id in self.messages_log and message_id in self.messages_log[channel_id]:
                cached_msg = self.messages_log[channel_id][message_id]
                author = await self.get_user_info(cached_msg['author'])
                hacky_code_dict = {'content': cached_msg['content'], 'channel': channel_id}
                await self.log_action(message=hacky_code_dict, user=author, action='message_delete')            
                    
    async def on_raw_reaction_add(self, emoji, message_id, channel_id, user_id):
        if not self.use_reactions: return
        if user_id == self.user.id:
            return
        if channel_id == CHANS['modmail']:
            modmail = self.get_channel(CHANS['modmail'])
            if emoji.name == 'ℹ':
                print(emoji.name)
                msg = await modmail.get_message(message_id)
                print(msg)
                match = re.search(r'Reply ID: `([0-9]+)`$', msg.content)
                if match:
                    await self.safe_send_message(modmail, content=match.group(1))
            elif emoji.name == '✅':
                msg = await modmail.get_message(message_id)
                match = re.search(r'Reply ID: `([0-9]+)`$', msg.content)
                if match:
                    auth_id = int(match.group(1))
                    if auth_id in self.mod_mail_db:
                        self.mod_mail_db[auth_id]['answered'] = True
                        write_json('modmaildb.json', self.mod_mail_db)
                        await self.safe_send_message(modmail, content=':thumbsup:')
                        
        if message_id in ROLE_REACT_MSGS:
            member = self.get_guild(SERVERS['main']).get_member(user_id)
            if emoji.id == REACTS['pc']:
                member_roles = discord.utils.get(member.guild.roles, id=ROLES['pc'])
                if member_roles:
                    await member.add_roles(member_roles)
            if emoji.id  ==  REACTS['xbox']:
                member_roles = discord.utils.get(member.guild.roles, id=ROLES['xbox'])
                if member_roles:
                    await member.add_roles(member_roles)
            if emoji.id  ==  REACTS['ps4']:
                member_roles = discord.utils.get(member.guild.roles, id=ROLES['ps4'])
                if member_roles:
                    await member.add_roles(member_roles)
            if emoji.id  ==  REACTS['r6ping']:
                member_roles = discord.utils.get(member.guild.roles, id=ROLES['r6news'])
                if member_roles:
                    await member.add_roles(member_roles)
            if emoji.id  ==  REACTS['invitationals']:
                member_roles = discord.utils.get(member.guild.roles, id=ROLES['invitationals'])
                if member_roles:
                    await member.add_roles(member_roles)
            if emoji.id  ==  REACTS['serverping']:
                member_roles =  discord.utils.get(member.guild.roles, id=ROLES['servernews'])
                if member_roles:
                    await member.add_roles(member_roles)

    async def on_reaction_add(self, reaction, member):
        if not self.use_reactions: return
        if member.id == self.user.id:
            return
        if reaction.message.channel.id in [CHANS['drama']]:
            user = discord.utils.get(reaction.message.guild.members, id=self.watched_messages[reaction.message.id]['author_id'])
            mutedrole = discord.utils.get(reaction.message.guild.roles, id=ROLES['muted'])
            if reaction.emoji.id == REACTS['delete']:
                await self.safe_delete_message(await self.get_channel(self.watched_messages[reaction.message.id]['channel_id']).get_message(self.watched_messages[reaction.message.id]['message_id']))
            if reaction.emoji.id == REACTS['mute']:
                try:
                    if not ROLES['staff'] in [role.id for role in user.roles]: await user.edit(roles = [mutedrole])
                    await user.edit(mute=True)
                except:
                    await self.safe_send_message(self.get_channel(CHANS['drama']), content='Cannot mute user {} ({}) for they\'re not on the server'.format(await self.get_user_info(self.watched_messages[reaction.message.id]['author_id']).name, self.watched_messages[reaction.message.id]['author_id']))
                    return
                await self.safe_send_message(user, content=MUTED_MESSAGES['plain'].format(rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Muted user', reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='as they were muted'))
            if reaction.emoji.id == REACTS['24mute']:
                try:
                    if not ROLES['staff'] in [role.id for role in user.roles]: await user.edit(roles = [mutedrole])
                    await user.edit(mute=True)
                except:
                    await self.safe_send_message(self.get_channel(CHANS['drama']), content='Cannot mute user {} ({}) for they\'re not on the server'.format(await self.get_user_info(self.watched_messages[reaction.message.id]['author_id']).name, self.watched_messages[reaction.message.id]['author_id']))
                    return
                muted_datetime = datetime.utcnow() + timedelta(hours = 24)
                self.muted_dict[user.id] = muted_datetime.timestamp()
                print('user {} now timed muted'.format(user.name))
                await self.safe_send_message(user, content=MUTED_MESSAGES['timed'].format(time='24 hours', rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Muted user for 24 hrs', reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='as they were muted for 24 hrs'))
                asyncio.ensure_future(self.queue_timed_role(86400, user, mutedrole, user.id))
            if reaction.emoji.id == REACTS['48mute']:
                try:
                    if not ROLES['staff'] in [role.id for role in user.roles]: await user.edit(roles = [mutedrole])
                    await user.edit(mute=True)
                except:
                    await self.safe_send_message(self.get_channel(CHANS['drama']), content='Cannot mute user {} ({}) for they\'re not on the server'.format(await self.get_user_info(self.watched_messages[reaction.message.id]['author_id']).name, self.watched_messages[reaction.message.id]['author_id']))
                    return
                muted_datetime = datetime.utcnow() + timedelta(hours = 48)
                self.muted_dict[user.id] = muted_datetime.timestamp()
                print('user {} now timed muted'.format(user.name))
                await self.safe_send_message(user, content=MUTED_MESSAGES['timed'].format(time='48 hours', rules=CHANS['rules'], muted=CHANS['muted']))
                await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Muted user for 48 hrs', reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='as they were muted for 48 hrs'))
                asyncio.ensure_future(self.queue_timed_role(172800, user, mutedrole, user.id))
            if reaction.emoji.id == REACTS['ban']:
                try:
                    await self.safe_send_message(user, content=MSGS['banmsg'])
                except:
                    if not user:
                        await self.safe_send_message(self.get_channel(CHANS['drama']), content=MSGS['dramaerror'].format('send ban message to ', self.watched_messages[reaction.message.id]['author_id'], 'Banning anyway...'))
                        await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=user.name, optional_content='', discrim=user.discriminator ,id=user.id, action='Banned user', reason='Action taken by {}#{}'.format(author.name, author.discriminator)))
                await self.http.ban(self.watched_messages[reaction.message.id]['author_id'], reaction.message.guild.id, 0)
                            
    async def on_member_join(self, member):
        if member.guild.id == SERVERS['ban']: return
        for role_id in self.channel_bans:
            if member.id in self.channel_bans[role_id]:
                member_roles = [discord.utils.get(member.guild.roles, id=role_id)] + member.roles
                if member_roles:
                    if not ROLES['staff'] in [role.id for role in member.roles]: await member.edit(roles = member_roles)
        if member.id in self.muted_dict:
            member_roles = [discord.utils.get(member.guild.roles, id=ROLES['muted'])]
            if member_roles:
                if not ROLES['staff'] in [role.id for role in member.roles]: await member.edit(roles = member_roles)
        else:   
            
            await asyncio.sleep(5)
            final_msg = '{}, {}'.format(member.mention, self.intro_msg)
            if self.use_reactions:
                await self.safe_send_message(member, content=self.dm_msg)
            else:
                await self.safe_send_message(self.get_channel(CHANS['registration']), content=final_msg)
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
                self.channel_bans[role.id] = [member.id for member in discord.utils.get(self.guilds, id=SERVERS['main']).members if role in member.roles]
                write_json('channel_banned.json', self.channel_bans)
        if before.nick != after.nick:
            await self.log_action(user=before, after=after, action='nickname_change')
        if before.name != after.name:
            await self.log_action(user=before, after=after, action='name_change')
        if before.avatar_url != after.avatar_url:
            await self.log_action(user=before, after=after, action='avatar_change')
        if before.roles != after.roles:
            merged_roles = list((set(before.roles) - set(after.roles))) + list((set(after.roles) - set(before.roles)))
            if [role.id for role in merged_roles if role.id not in UNPROTECTED_ROLES]:
                await self.log_action(user=before, after=after, action='important_role_change')
            try:
                self.serious_d_blacklist = list(set(self.serious_d_blacklist))
                
                if not [role for role in before.roles if role.id  in [ROLES['banteam']]] and [role for role in after.roles if role.id  in [ROLES['banteam']]]:
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
                        self.channel_bans[role_id].append(before.id)
                        print('user {} now channel banned'.format(before.name))
                        write_json('channel_banned.json', self.channel_bans)
                    if [role for role in before.roles if role.id == role_id] and not [role for role in after.roles if role.id == role_id]:
                        self.channel_bans[role_id].remove(before.id)
                        print('user {} no longer channel banned'.format(before.name))
                        write_json('channel_banned.json', self.channel_bans)
            except:
                pass

    async def on_message_edit(self, before, after):
        if before.author == self.user:
            return
        if not isinstance(before.channel, discord.abc.PrivateChannel):
            await self.log_action(user=before.author, message=before, after=after,  action='message_edit')
        await self.on_message(after, edit=True)
        
    async def on_voice_state_update(self, member, before, after):
        if before != after:
            if not (before and before.channel) and after and after.mute and not ROLES['staff'] in [role.id for role in member.roles]:
                await member.edit(mute=False)
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
                optional_content = ':radioactive: <@&{}> :radioactive: `(VC Ban Applied)` '.format(ROLES['staff'])
                member_roles = [vc_muted_role] + member.roles
                await member.edit(mute=True)
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

    async def on_message(self, message, edit=False):
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
                
        if self.last_modmail_poster == self.user.id: 
            self.divider_content = '__                                                                                                          __\n\n'
        else:
            self.divider_content = ''

        if isinstance(message.channel, discord.abc.PrivateChannel):
            print('pm')
            if message.author.id in [member.id for member in discord.utils.get(self.guilds, id=SERVERS['main']).members] and len(discord.utils.get(discord.utils.get(self.guilds, id=SERVERS['main']).members, id=message.author.id).roles) < 2 and message.author.id not in self.anti_stupid_modmail_list:
                await self.safe_send_message(message.author, content='I noticed you\'re attempting to send the staff a mod mail but have no roles, if this is your issue __**PLEASE**__ make sure to review the message you recieved when you joined __along__ with reading over <#>! If this didn\'t help, please resend your original message!')
                await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+'→ I sent a message to {}({}) to remind them to read the welcome DM as they attempted to DM me without any roles'.format(message.author.mention, message.author.id))

                self.anti_stupid_modmail_list.append(message.author.id)
                return
                
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
            await self.safe_send_message(self.get_channel(CHANS['modmail']), content=self.divider_content+'**{edited_alert}From:** *{mention}*:\n```{message_content}```{attachment_info}{alert_info}\nReply ID: `{author_id}`'.format(edited_alert = msg_edit,
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
                    await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='for sending some dumb shit in teams that was shorter than 60 chars or had a mention'))
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
                    await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='for mentioning someone in lf scrims'))
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
                    await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='for sending some dumb shit in lfg that was longer than 200 chars'))
                    await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=message.author.name, discrim=message.author.discriminator ,id=message.author.id, action='Deleted Message', reason='Sent some dumb shit in lfg that was longer than 200 chars', optional_content='Message sent in {}: `{}`\n'.format(message.channel.mention, message.clean_content)))
        
        # I don't feel like fixing all these IDs, they're all the staff channels just pretend I actually did the work pls.
        if not message.author.bot and message.channel.id not in [269519917693272074, 290274342904922112, 282076089927598081, 282076117651947520, 269566972977610753, 282076329829072897, 269567077805719552, 282076628153139200, 282076615784136705, 282076800698548224, 282076856201510914, 282076300838043648, 290428366312701962, 290428522080763904, 290428554968301569, 290428408465195008, 290428617773678592, 290428645883772928]:
            if re.search(REGEX['uplay'], message.content, re.IGNORECASE):
                em = discord.Embed(description='**Noteworthy mention found in %s:**' % message.channel.mention, colour=discord.Colour(0x9d9bf4), timestamp=datetime.utcnow())
                em.set_author(name="𝅳𝅳𝅳", icon_url="https://i.imgur.com/TVlATNp.png")
                async for msg in message.channel.history(limit=4, before=message, reverse=True):
                    em.add_field(name='%s#%s'% (msg.author.name, msg.author.discriminator), value=msg.content, inline=False)
                em.add_field(name='%s#%s'% (message.author.name, message.author.discriminator), value=message.content, inline=False)
                await self.safe_send_message(self.get_channel(CHANS['ubireports']), embed=em)
                
        if not message.author.bot and not [role for role in message.author.roles if role.id  in [ROLES['staff'], ROLES['bots']]]:
            drama_matches = re.search(REGEX['drama'], message.content, re.IGNORECASE)
            dox_matches = re.search(REGEX['dox'], message.content, re.IGNORECASE)
            sent_msg = None
            if message.id in [self.watched_messages[msg]['message_id'] for msg in self.watched_messages]:
                if not drama_matches and not dox_matches:
                    await self.safe_send_message(self.get_channel(CHANS['drama']), content='{}#{} has edited away the past potentially drama inducing item'.format(message.author.name, message.author.discriminator))
                else:
                    for msg_id, msg_dict in self.watched_messages.items():
                        if msg_dict['message_id'] == message.id:
                            await self.safe_delete_message(await self.get_channel(365448564261912576).get_message(msg_id))
            if drama_matches:
                em = discord.Embed(description='**Potential Drama found in %s:**' % message.channel.mention, colour=discord.Colour(0xffff00), timestamp=datetime.utcnow())
                em.set_author(name="𝅳𝅳𝅳", icon_url="https://i.imgur.com/TVlATNp.png")
                async for msg in message.channel.history(limit=4, before=message, reverse=True):
                    em.add_field(name='%s#%s'% (msg.author.name, msg.author.discriminator), value=msg.content, inline=False)
                msg_value = message.content[:drama_matches.start()] + '**__' + message.content[drama_matches.start():drama_matches.end()] + '__**' + message.content[drama_matches.end():]
                em.add_field(name='%s#%s'% (message.author.name, message.author.discriminator), value=msg_value, inline=False)
                sent_msg = await self.safe_send_message(self.get_channel(CHANS['drama']), embed=em)
            if dox_matches:
                em = discord.Embed(description='**Potential DOXXING found in %s:**' % message.channel.mention, colour=discord.Colour(0xff0000), timestamp=datetime.utcnow())
                em.set_author(name="𝅳𝅳𝅳", icon_url="https://i.imgur.com/ozWtGXL.png")
                async for msg in message.channel.history(limit=4, before=message, reverse=True):
                    em.add_field(name='%s#%s'% (msg.author.name, msg.author.discriminator), value=msg.content, inline=False)
                msg_value = message.content[:dox_matches.start()] + '**__' + message.content[dox_matches.start():dox_matches.end()] + '__**' + message.content[dox_matches.end():]
                em.add_field(name='%s#%s'% (message.author.name, message.author.discriminator), value=msg_value, inline=False)
                sent_msg = await self.safe_send_message(self.get_channel(CHANS['drama']), embed=em)
            if sent_msg:
                self.watched_messages[sent_msg.id] = {'author_id': message.author.id, 'message_id': message.id, 'channel_id': message.channel.id}
                reactions = [emote for emote in self.emojis if emote.id in [REACTS['delete'], REACTS['mute'],REACTS['24mute'], REACTS['48mute'], REACTS['ban']]]
                for reaction in reactions:
                    await asyncio.sleep(1)
                    await sent_msg.add_reaction(reaction)

            
        message_content = message.content.strip()
        
        for item in message.content.strip().split():
            try:
                if 'discord.gg' in item:
                    invite = await self.get_invite(item)
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
                            await self.safe_send_message(self.get_channel(CHANS['modmail']), content=MSGS['modmailaction'].format(action_log_id=CHANS['actions'], username=message.author.mention, id=message.author.id, reason='for sending discord invites'))
                            await self.safe_send_message(self.get_channel(CHANS['actions']), content=MSGS['action'].format(username=message.author.name, action='Deleted message', discrim=message.author.discriminator ,id=message.author.id, reason='Sent a nonwhitelisted invite url ({} : {})'.format(item, invite.guild.id), optional_content='Message sent in {}: `{}`\n'.format(message.channel.mention, message.clean_content)))
                            return
            except:
                pass
        
        if [role for role in message.author.roles if role.id == ROLES['muted']]:
            if message.content != '!timeleft':
                return
        
        if not message_content.startswith(self.prefix) or edit:
            if message.channel.id in list(self.slow_mode_dict.keys()):
                time_out = self.slow_mode_dict[message.channel.id]['time_between']
                channel_muted_role = self.slow_mode_dict[message.channel.id]['channel_muted_role']
                await message.author.add_roles([channel_muted_role])
                await asyncio.sleep(time_out)
                await message.author.add_roles([channel_muted_role])
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
                await message.author.add_roles([channel_muted_role])
                await asyncio.sleep(time_out)
                await message.author.remove_roles([channel_muted_role])
            for tag in self.tags:
                if class_name.lower() == tag.lower():
                    if self.tags[tag][0]:
                        if not [role for role in author.roles if role.id  in [ROLES['staff']]]:
                            await self.safe_send_message(message.channel, content='Tag cannot be used by nonstaff members')
                            print("[Command] {0.id}/{0.name} ({1})".format(message.author, message_content))
                            return
                    await self.safe_send_message(message.channel, content=clean_bad_pings(self.tags[tag][1]))
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
                    await message.author.add_roles([channel_muted_role])
                    await asyncio.sleep(time_out)
                    await message.author.remove_roles([channel_muted_role])
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
        
        if message.channel.id in list(self.slow_mode_dict.keys()):
            time_out = self.slow_mode_dict[message.channel.id]['time_between']
            channel_muted_role = self.slow_mode_dict[message.channel.id]['channel_muted_role']
            await message.author.add_roles([channel_muted_role])
            await asyncio.sleep(time_out)
            await message.author.remove_roles([channel_muted_role])

if __name__ == '__main__':
    bot = R6Bot()
    bot.run()
