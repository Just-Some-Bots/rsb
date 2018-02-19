import json
import re
import time
import inspect
from datetime import datetime, timezone
from .constants import DISCORD_EPOCH


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
