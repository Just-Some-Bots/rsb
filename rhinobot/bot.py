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

class Response(object):
    def __init__(self, content, reply=False, delete_after=0):
        self.content = content
        self.reply = reply
        self.delete_after = delete_after

class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeError(message)

class Rhinobot(discord.Client):
    def __init__(self):
        super().__init__(max_messages=50000)
        # Auth Related 
        self.prefix = '!'
        self.token = BOT_TOKEN
        self.user_token = USER_TOKEN
        self.twitAPI = TwitterAPI(TWITTER_CON_KEY, TWITTER_CON_SECRET, TWITTER_TOKEN_KEY, TWITTER_TOKEN_SECRET)
        self.twitch_client_id = TWITCH_CREDS
        
        # Local JSON Storage
        self.twitch_watch_list = ['s3xualrhinoceros']
        self.twitter_watch_list = ['SexualRhino_']
        
        # Instance Storage (nothing saved between bot
        self.twitch_is_live = {}
        self.twitter_id_cache = {}
        
        # Variables used as storage of information between commands
        self._last_result = None
        self.role_ping_toggle = {'everynone': None}
        self.last_ping = None
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        
        # Used to make RESTful calls using the User Token.
        self.user_http = HTTPClient(None, proxy=None, proxy_auth=None, loop=asyncio.get_event_loop())
        
        # Debug Garbage / work arounds for bugs I saw.
        self.twitch_debug = True
        self.twitter_debug = False
        self.ready_check = False
                
        #scheduler garbage
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()
        
        print('past init')

    # noinspection PyMethodOverriding
    def run(self):
        loop = asyncio.get_event_loop()
        try:
            loop.create_task(self.check_twitch_streams())
            loop.create_task(self.get_tweets())
            loop.run_until_complete(self.start(self.token))
            loop.run_until_complete(self.connect())
        except Exception:
            for task in asyncio.Task.all_tasks():
                task.cancel()
        finally:
            loop.close()            
            
    async def wait_until_really_ready(self):
        while not self.ready_check:
            await asyncio.sleep(1)
            
    async def get_tweets(self):
        await self.wait_until_really_ready()
        
        print('starting tweet fetching')
        
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
            print(f"{handle}: {highest_id}")
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
            
    async def generate_streaming_embed_online(self, resp, streamer):
        # em = discord.Embed(colour=discord.Colour(0x56d696), description=resp["stream"]["channel"]["status"], timestamp=datetime.strptime(resp["stream"]["created_at"], "%Y-%m-%dT%H:%M:%SZ"))
        # async with aiohttp.ClientSession() as sess:
            # async with sess.get(str(resp["stream"]["preview"]["large"])) as r:
                # data = await r.read()
                # with open("img.png", "wb") as f:
                    # f.write(data)
        # file = discord.File("/home/bots/rhinobotrw/img.png", filename="img.png")
        # em.set_image(url="attachment://img.png")
        
        # em.set_author(name=streamer, url='https://www.twitch.tv/{}'.format(streamer), icon_url=resp["stream"]["channel"]["logo"])
        # em.set_footer(text="Language: {}".format(resp["stream"]["channel"]["language"].upper()))

        # em.add_field(name="Status", value="LIVE", inline=True)
        # em.add_field(name="Viewers", value=resp["stream"]["viewers"], inline=True)
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
        file = discord.File("/home/bots/rhinobotrw/img.png", filename="img.png")
        em.set_image(url="attachment://img.png")
        em.set_author(name=streamer, url='https://www.twitch.tv/{}'.format(streamer), icon_url=prof_pic)
        em.set_footer(text="Language: {}".format(resp["stream"]["channel"]["language"].upper()))

        em.add_field(name="Status", value="LIVE", inline=True)
        em.add_field(name="Viewers", value=resp["stream"]["viewers"], inline=True)

        return em      
        
    async def generate_streaming_embed_offline(self, resp, streamer):
        em = discord.Embed(colour=discord.Colour(0x979c9f), description=resp["status"], timestamp=datetime.strptime(resp["updated_at"], "%Y-%m-%dT%H:%M:%SZ"))
        em.set_image(url=str(resp["video_banner"]))
        em.set_author(name=streamer, url='https://www.twitch.tv/{}'.format(streamer), icon_url=resp["logo"])
        em.set_footer(text="Language: {}".format(resp["language"].upper()))

        em.add_field(name="Status", value="OFFLINE", inline=True)
        em.add_field(name="Viewers", value='0', inline=True)
        return em
               
    async def check_twitch_streams(self):
        await self.wait_until_ready()
        def is_me(m):
            return m.author == self.user
        try:
            await self.get_channel(CHANS['stream_status']).purge(limit=100, check=is_me)
        except:
            async for entry in self.get_channel(CHANS['stream_status']).history(limit=10000):
                if entry.author == self.user:
                    await self.safe_delete_message(entry)
                    await asyncio.sleep(0.21)
        if self.twitch_debug: print('starting stream function')
        target_server = discord.utils.get(self.guilds, id=SERVERS['v3'])
        while True:
            for streamer in self.twitch_watch_list:
                try:
                    async with aiohttp.ClientSession() as session:
                        await asyncio.sleep(10)
                        resp = None
                        async with session.get('https://api.twitch.tv/kraken/streams/{}?client_id={}'.format(streamer, self.twitch_client_id)) as r:
                            try:
                                resp = await r.json()
                            except json.decoder.JSONDecodeError:
                                pass
                        if resp and "stream" in resp and resp["stream"]:
                            if streamer not in self.twitch_is_live:
                                role = discord.utils.get(discord.utils.get(self.guilds, id=SERVERS['v3']).roles, id=ROLES['everyone'])
                                await role.edit(mentionable=False)
                                if self.twitch_debug: print('Creating new online embed for user %s' % streamer)
                                self.twitch_is_live[streamer] = {'detected_start': datetime.utcnow(),
                                                                 'view_count_updated': datetime.utcnow(),
                                                                 'offline_cooldown': False,
                                                                 'mentioned_server': True,
                                                                 'embedded_object': await self.generate_streaming_embed_online(resp, streamer),
                                                                 'message': None}
                                self.twitch_is_live[streamer]['message'] = await self.safe_send_message(self.get_channel(CHANS['stream_status']), embed=self.twitch_is_live[streamer]['embedded_object'])
                                await self.safe_send_message(self.get_channel(CHANS['stream_status']), content='@everyone', expire_in=3600)
                                self.last_ping = datetime.utcnow()
                                await role.edit(mentionable=True)
                            else:
                                if datetime.utcnow() - timedelta(minutes=15) > self.twitch_is_live[streamer]['detected_start']:
                                    if self.twitch_debug: print('Recreating new embed for user %s' % streamer)
                                    if not self.twitch_is_live[streamer]['mentioned_server']:
                                        role = discord.utils.get(target_server.roles, id=ROLES['everyone'])
                                        await role.edit(mentionable=False)
                                        if not self.last_ping or datetime.utcnow() - timedelta(hours=3) > self.last_ping:
                                            await self.safe_send_message(self.get_channel(CHANS['stream_status']), content='@everyone', expire_in=3600)
                                            self.last_ping = datetime.utcnow()
                                        await role.edit(mentionable=True)
                                    await self.safe_delete_message(self.twitch_is_live[streamer]['message'])
                                    self.twitch_is_live[streamer] = {'detected_start': datetime.utcnow(),
                                                                     'view_count_updated': datetime.utcnow(),
                                                                     'offline_cooldown': False,
                                                                     'mentioned_server': self.twitch_is_live[streamer]['mentioned_server'],
                                                                     'embedded_object': await self.generate_streaming_embed_online(resp, streamer),
                                                                     'message': None}
                                    self.twitch_is_live[streamer]['message'] = await self.safe_send_message(self.get_channel(CHANS['stream_status']), embed=self.twitch_is_live[streamer]['embedded_object'])
                                elif datetime.utcnow() - timedelta(minutes=5) > self.twitch_is_live[streamer]['view_count_updated']:
                                    if self.twitch_debug: print('Updating embeds view count for user %s' % streamer)
                                    self.twitch_is_live[streamer]['embedded_object'] = await self.generate_streaming_embed_online(resp, streamer)
                                    self.twitch_is_live[streamer]['view_count_updated'] = datetime.utcnow()
                                    await self.safe_edit_message(self.twitch_is_live[streamer]['message'], embed=self.twitch_is_live[streamer]['embedded_object'])
                                    
                        elif streamer in self.twitch_is_live and not self.twitch_is_live[streamer]['offline_cooldown']:
                            if self.twitch_debug: print('User %s detected offline, marking as such' % streamer)
                            self.twitch_is_live[streamer]['embedded_object'].color = discord.Colour(0x979c9f)
                            self.twitch_is_live[streamer]['embedded_object'].set_field_at(0, name="Status", value="OFFLINE", inline=True)
                            self.twitch_is_live[streamer]['offline_cooldown'] = True
                            self.twitch_is_live[streamer]['mentioned_server'] = False
                            await self.safe_edit_message(self.twitch_is_live[streamer]['message'], embed=self.twitch_is_live[streamer]['embedded_object'])
                        elif streamer not in self.twitch_is_live:
                            async with session.get('https://api.twitch.tv/kraken/channels/{}?client_id={}'.format(streamer, self.twitch_client_id)) as r:
                                try:
                                    resp = await r.json()
                                except json.decoder.JSONDecodeError:
                                    pass
                            if self.twitch_debug: print('Creating new offline embed for user %s' % streamer)
                            self.twitch_is_live[streamer] = {'detected_start': datetime.utcnow(),
                                                             'view_count_updated': datetime.utcnow(),
                                                             'offline_cooldown': True,
                                                             'mentioned_server': False,
                                                             'embedded_object': await self.generate_streaming_embed_offline(resp, streamer),
                                                             'message': None}
                            self.twitch_is_live[streamer]['message'] = await self.safe_send_message(self.get_channel(CHANS['stream_status']), embed=self.twitch_is_live[streamer]['embedded_object'])
                            
                except RuntimeError:
                    return
                except:
                    traceback.print_exc()
                    print('error within twitch loop, handled to prevent breaking')

        
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
        print('Finalizing User Login...')
        await self.user_http.static_login(self.user_token, bot=False)
        print('Done!\n\nApplying Missed Role Ping...')
        everynone_role = discord.utils.get(discord.utils.get(self.guilds, id=SERVERS['v2']).roles, id=ROLES['everynone'])
        missed_coffee_filter = [member for member in discord.utils.get(self.guilds, id=SERVERS['v2']).members if everynone_role not in member.roles]
        for member in missed_coffee_filter:
            await member.add_roles(everynone_role)
        print('Done!')
        
        await self.change_presence(activity=discord.Game(name='and playing and playing and playing and playing'))
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
    async def cmd_restart(self, channel, author):
        """
        Usage: {command_prefix}restart
        Forces a restart
        """
        await self.safe_send_message(channel, content="Restarting....")
        await self.logout()
              
    @mods_only
    async def cmd_posttweet(self, twitter_id):
        """
        Usage: {command_prefix}posttweet {status ID}
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
        
            
    async def cmd_ping(self, message, author, guild):
        """
        Usage: {command_prefix}ping
        Replies with "PONG!"; Use to test bot's responsiveness
        """
        return Response('PONG!', reply=True)
    

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
    async def cmd_userinfo(self, guild, channel, author, mentions, raw_leftover_args):
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
        if vc_activity["total_results"] < 5:
            vc_string = 'Nothing'
        elif vc_activity["total_results"] < 30:
            vc_string = 'Very Low'
        elif vc_activity["total_results"] < 80:
            vc_string = 'Low'
        elif vc_activity["total_results"] < 120:
            vc_string = 'Medium'
        elif vc_activity["total_results"] < 350:
            vc_string = 'High'
        elif vc_activity["total_results"] < 700:
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
                em.add_field(name='User In HypeSquad', value='<:shillsquad:519318329286983711>', inline=True)
            if member_profile.partner: 
                em.add_field(name='User Is a Partner', value='<:howdypartner:519318400477167626>', inline=True)
            if member_profile.staff: 
                em.add_field(name='User Is Staff', value='<:nazi:519318453539176448>', inline=True)
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
                
        em.set_thumbnail(url=user.avatar_url)
        await self.safe_send_message(channel, embed=em)

    async def on_typing(self, channel, user, when):
        if channel.id == CHANS['at-everyone']:
            role = discord.utils.get(channel.guild.roles, id=ROLES['everynone'])
            self.role_ping_toggle['everynone'] = role
            await role.edit(mentionable=True)
            await asyncio.sleep(30)
            await role.edit(mentionable=False)
                            
    async def on_member_join(self, member):
        everynone_role = discord.utils.get(member.guild.roles, id=ROLES['everynone'])
        if everynone_role:
            await member.add_roles(everynone_role)
        
    async def on_message_edit(self, before, after):
        if before.author == self.user:
            return
        await self.on_message(after, edit=True)
        
    async def on_message(self, message, edit=False):
        if message.author == self.user or message.webhook_id or message.author.bot:
            return
            
        if self.role_ping_toggle['everynone'] and message.role_mentions:
            if self.role_ping_toggle['everynone'] and self.role_ping_toggle['everynone'] in message.role_mentions:
                await self.role_ping_toggle['everynone'].edit(mentionable=False)
                self.role_ping_toggle['everynone'] = None
                
        if isinstance(message.channel, discord.abc.PrivateChannel):
            print('pm')
            
        try:
            this = [role for role in message.author.roles if role.id in [ROLES['staff']]]
        except:
            try:
                message.author.roles = [role for role in message.author.roles if role is not None]
            except AttributeError as e:
                print(message.author.id)
                print(message.author.name)
                
        message_content = message.content.strip()
                
        try:
            command, *args = shlex.split(message.content.strip())
            command, *raw_args = message.content.strip().split()
        except:
            command, *args = message.content.strip().split()
            command, *raw_args = message.content.strip().split()
        command = command[len(self.prefix):].lower().strip()
        
        
        handler = getattr(self, 'cmd_%s' % command, None)
        if not handler:
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
    bot = Rhinobot()
    bot.run()
