import json
import re
import time
import asyncio
import discord
import inspect
from datetime import datetime, timezone
from .constants import DISCORD_EPOCH
from .exceptions import CommandError

class Converter:
    @asyncio.coroutine
    def convert(self, argument):
        raise NotImplementedError('Derived classes need to implement this.')

class IDConverter(Converter):
    def __init__(self):
        self._id_regex = re.compile(r'([0-9]{15,21})$')
        super().__init__()

    def _get_id_match(self, argument):
        return self._id_regex.match(argument)

class MemberConverter(IDConverter):

    @asyncio.coroutine
    def convert(self, guild, argument):
        match = self._get_id_match(argument) or re.match(r'<@!?([0-9]+)>$', argument)
        result = None
        if match is None:
            # not a mention...
            result = guild.get_member_named(argument)
        else:
            user_id = int(match.group(1))
            result = guild.get_member(user_id)

        if result is None:
            raise CommandError('Member "{}" not found'.format(argument))

        return result

class UserConverter(IDConverter):

    @asyncio.coroutine
    def convert(self, message, bot, argument):
        match = self._get_id_match(argument) or re.match(r'<@!?([0-9]+)>$', argument)
        result = None
        state = message._state

        if match is not None:
            user_id = int(match.group(1))
            result = bot.get_user(user_id)
            if result is None:
                try:
                    result = bot.get_user_info(user_id)
                except:
                    raise CommandError('User "{}" not found'.format(argument))
        else:
            arg = argument
            # check for discriminator if it exists
            if len(arg) > 5 and arg[-5] == '#':
                discrim = arg[-4:]
                name = arg[:-5]
                predicate = lambda u: u.name == name and u.discriminator == discrim
                result = discord.utils.find(predicate, state._users.values())
                if result is not None:
                    return result

            predicate = lambda u: u.name == arg
            result = discord.utils.find(predicate, state._users.values())

        if result is None:
            bot.get_user_info(user_id)
            raise CommandError('User "{}" not found'.format(argument))

        return result

class TextChannelConverter(IDConverter):

    @asyncio.coroutine
    def convert(self, guild, bot, argument):
        match = self._get_id_match(argument) or re.match(r'<#([0-9]+)>$', argument)
        result = None

        if match is None:
            # not a mention
            if guild:
                result = discord.utils.get(guild.text_channels, name=argument)
            else:
                def check(c):
                    return isinstance(c, discord.TextChannel) and c.name == argument
                result = discord.utils.find(check, bot.get_all_channels())
        else:
            channel_id = int(match.group(1))
            if guild:
                result = guild.get_channel(channel_id)
            else:
                result = _get_from_guilds(bot, 'get_channel', channel_id)

        if not isinstance(result, discord.TextChannel):
            raise CommandError('Channel "{}" not found.'.format(argument))

        return result

class VoiceChannelConverter(IDConverter):

    @asyncio.coroutine
    def convert(self, guild, bot, argument):
        match = self._get_id_match(argument) or re.match(r'<#([0-9]+)>$', argument)
        result = None

        if match is None:
            # not a mention
            if guild:
                result = discord.utils.get(guild.voice_channels, name=argument)
            else:
                def check(c):
                    return isinstance(c, discord.VoiceChannel) and c.name == argument
                result = discord.utils.find(check, bot.get_all_channels())
        else:
            channel_id = int(match.group(1))
            if guild:
                result = guild.get_channel(channel_id)
            else:
                result = _get_from_guilds(bot, 'get_channel', channel_id)

        if not isinstance(result, discord.VoiceChannel):
            raise CommandError('Channel "{}" not found.'.format(argument))

        return result

class CategoryChannelConverter(IDConverter):

    @asyncio.coroutine
    def convert(self, guild, bot, argument):
        match = self._get_id_match(argument) or re.match(r'<#([0-9]+)>$', argument)
        result = None

        if match is None:
            # not a mention
            if guild:
                result = discord.utils.get(guild.categories, name=argument)
            else:
                def check(c):
                    return isinstance(c, discord.CategoryChannel) and c.name == argument
                result = discord.utils.find(check, bot.get_all_channels())
        else:
            channel_id = int(match.group(1))
            if guild:
                result = guild.get_channel(channel_id)
            else:
                result = _get_from_guilds(bot, 'get_channel', channel_id)

        if not isinstance(result, discord.CategoryChannel):
            raise CommandError('Channel "{}" not found.'.format(argument))

        return result

def load_json(filename):
    try:
        with open(filename, encoding='utf-8') as f:
            return json.loads(f.read())

    except IOError as e:
        print("Error loading", filename, e)
        return []


def load_file(filename):
    try:
        with open(filename) as f:
            results = []
            for line in f:
                line = line.strip()
                if line:
                    results.append(line)

            return results

    except IOError as e:
        print("Error loading", filename, e)
        return []


def write_file(filename, contents):
    with open(filename, 'w') as f:
        for item in contents:
            f.write(str(item))
            f.write('\n')


def write_json(filename, contents):
    with open(filename, 'w') as outfile:
        outfile.write(json.dumps(contents, indent=2))


def clean_string(string):
    string = re.sub('@', '@\u200b', string)
    string = re.sub('#', '#\u200b', string)
    return string
    
def clean_bad_pings(string):
    string = re.sub('@everyone', '@\u200beveryone', string)
    string = re.sub('@here', '@\u200bhere', string)
    return string

def datetime_to_utc_ts(datetime):
    return datetime.replace(tzinfo=timezone.utc).timestamp()

def snowflake_time(user_id):
    return datetime.utcfromtimestamp(((int(user_id) >> 22) + DISCORD_EPOCH) / 1000)

def timestamp_to_seconds(input_str):
    output_time = 0
    iterations = 0
    time_regex = {r"([0-9]+)(seconds|second|secs|sec|s)": 1,
                  r"([0-9]+)(minutes|minute|mins|min|m)": 60,
                  r"([0-9]+)(hours|hour|hrs|hr|h)": 3600,
                  r"([0-9]+)(days|day|ds|d)": 86400}
    input_str = input_str.replace(' ', '')
    while input_str:
        iterations+=1
        for regex, multiplier in time_regex.items():
            m = re.search(regex, input_str)
            if m:
                obj = m.group(1)
                try:
                    output_time += (int(obj) * multiplier)
                except ValueError:
                    return None
                input_str = input_str[:m.start()] + input_str[m.end():]
        if iterations > 5:
            break
    if output_time != 0:
        return output_time
    return None

def _get_variable(name):
    stack = inspect.stack()
    try:
        for frames in stack:
            try:
                frame = frames[0]
                current_locals = frame.f_locals
                if name in current_locals:
                    return current_locals[name]
            finally:
                del frame
    finally:
        del stack
    
    
def strfdelta(tdelta):
    t = {'days': 'days',
         'hours': 'hours',
         'minutes': 'minutes',
         'seconds': 'seconds'
         }

    d = {'days': tdelta.days}
    d['hours'], rem = divmod(tdelta.seconds, 3600)
    d['minutes'], d['seconds'] = divmod(rem, 60)
    if d['days'] is 1:
        t['days'] = 'day'
    if d['hours'] is 1:
        t['hours'] = 'hour'
    if d['minutes'] is 1:
        t['minutes'] = 'minute'
    if d['seconds'] is 1:
        t['seconds'] = 'second'
    if d['days'] is 0:
        if d['hours'] is 0:
            if d['minutes'] is 0:
                if d['seconds'] is 0:
                    return 'NOW'
                return '{} {}'.format(d['seconds'], t['seconds'], )
            return '{} {} {} {}'.format(d['minutes'], t['minutes'], d['seconds'], t['seconds'], )
        return '{} {} {} {} {} {}'.format(d['hours'], t['hours'], d['minutes'], t['minutes'], d['seconds'],
                                          t['seconds'], )
    return '{} {} {} {} {} {} {} {}'.format(d['days'], t['days'], d['hours'], t['hours'], d['minutes'], t['minutes'],
                                            d['seconds'], t['seconds'], )
