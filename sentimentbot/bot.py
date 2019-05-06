import asyncio
import discord
import aiohttp
import logging
import functools
import traceback

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.cbook as cbook

from matplotlib.collections import LineCollection
from matplotlib.colors import ListedColormap, BoundaryNorm

from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


# logger = logging.getLogger('discord')
# logger.setLevel(logging.INFO)
# handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
# handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
# logger.addHandler(handler)

def run_in_executor(f):
    @functools.wraps(f)
    def inner(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, lambda: f(*args, **kwargs))

    return inner

class SentimentBot(discord.Client):
    def __init__(self):
        super().__init__(max_messages=500, fetch_offline_members=False)
        self.token = 'PUT YOUR TOKEN HERE'

        self.guild_scores = {}
        
        self.ready_check = False

        self.guild_periodical = {}

        self.target_channel = None

        self.analyzer = SentimentIntensityAnalyzer()

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(self.dump_short_term_data, 'cron', id='dump_short_term_data',  minute='*/10')
        self.scheduler.add_job(self.dump_long_term_data, 'cron', id='dump_long_term_data',  day='*', jitter=120)
        self.scheduler.start()
        
        print('past init')
        
    async def wait_until_really_ready(self):
        while not self.ready_check:
            await asyncio.sleep(1)

    async def regenerate_short_term(self):
        for guild in self.guilds:
            for channel in guild.channels:
                self.guild_scores[channel.id] = {}

    async def dump_short_term_data(self):
        if not self.ready_check: return
        
        ts_now = datetime.utcnow().timestamp()
        senti_list = [item for sublist in self.guild_scores.values() for item in sublist.values()]

        average_sentiment = (sum(senti_list) / len(senti_list))
        self.guild_periodical[ts_now] = average_sentiment
        await self.regenerate_short_term()

    async def dump_long_term_data(self):
        if not self.ready_check: return
        await self.generate_graph()
        file = discord.File("figure.png", filename="figure.png")
        await self.target_channel.send(file=file)
        self.guild_periodical = {}
        
    async def generate_graph(self):
        
        lists = sorted(self.guild_periodical.items()) # sorted by key, return a list of tuples

        x, y = zip(*lists) # unpack a list of pairs into two tuples
        def ts_to_string(timestamp):
            return datetime.utcfromtimestamp(timestamp)
        highres_x, highres_y = await self.highResPoints(x, y, 30)
        highres_x = [ts_to_string(item) for item in highres_x]
        x = [ts_to_string(item) for item in x]
        highres_y = np.asarray(list(highres_y))
        
        upper = 0.05
        lower = -0.05


        supper = np.ma.masked_where(highres_y < upper, highres_y)
        slower = np.ma.masked_where(highres_y > lower, highres_y)
        smiddle = np.ma.masked_where(np.logical_or(highres_y < lower, highres_y > upper), highres_y)

        fig, ax = plt.subplots()
        

        # format the ticks
        ax.xaxis.set_major_locator(mdates.HourLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        ax.xaxis.set_minor_locator(mdates.MinuteLocator(interval=5))

        ax.grid(True)
        
        ax.set_facecolor('xkcd:grey')
        
        middle_marks = list(smiddle)
        lower_marks = list(slower)
        upper_marks = list(supper)
        
        middle_marks = [middle_marks.index(item) for item in y if item in middle_marks]
        lower_marks = [lower_marks.index(item) for item in y if item in lower_marks]
        upper_marks = [upper_marks.index(item) for item in y if item in upper_marks]
        
        
        ax.plot(highres_x, smiddle, color='gold', marker='o', markevery=middle_marks)
        
        ax.plot(highres_x, slower, color='darkred', marker='o', markevery=lower_marks)
            
        ax.plot(highres_x, supper, color='darkgreen', marker='o', markevery=upper_marks)
        
        step_over = 0
        
        for xy in zip(x, y):
            if step_over == 3:
                ax.annotate('%s' % str(round(xy[1], 2)), xy=xy, textcoords='data')
                step_over = 0
            else:
                step_over += 1
        
        
        fig.autofmt_xdate()
        plt.ylim((-1, 1))
        plt.savefig('figure.png')
        plt.clf()
        
    async def highResPoints(self, x,y,factor):
        '''
        Take points listed in two vectors and return them at a higher
        resultion. Create at least factor*len(x) new points that include the
        original points and those spaced in between.

        Returns new x and y arrays as a tuple (x,y).
        '''

        # r is the distance spanned between pairs of points
        r = [0]
        for i in range(1,len(x)):
            dx = x[i]-x[i-1]
            dy = y[i]-y[i-1]
            r.append(np.sqrt(dx*dx+dy*dy))
        r = np.array(r)

        # rtot is a cumulative sum of r, it's used to save time
        rtot = []
        for i in range(len(r)):
            rtot.append(r[0:i].sum())
        rtot.append(r.sum())

        dr = rtot[-1]/(len(y)*factor-1)
        xmod=[x[0]]
        ymod=[y[0]]
        rPos = 0 # current point on walk along data
        rcount = 1 
        while rPos < r.sum():
            x1,x2 = x[rcount-1],x[rcount]
            y1,y2 = y[rcount-1],y[rcount]
            dpos = rPos-rtot[rcount] 
            theta = np.arctan2((x2-x1),(y2-y1))
            rx = np.sin(theta)*dpos+x1
            ry = np.cos(theta)*dpos+y1
            xmod.append(rx)
            ymod.append(ry)
            rPos+=dr
            try:
                while rPos > rtot[rcount+1]:
                    rPos = rtot[rcount+1]
                    rcount+=1
                    if rcount>rtot[-1]:
                        break
            except:
                pass

        return xmod,ymod
        

    # noinspection PyMethodOverriding
    def run(self):
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.start(self.token))
        except Exception as e:
            for task in asyncio.Task.all_tasks():
                task.cancel()
            traceback.print_exc()
        finally:
            loop.close()
                       
    async def on_ready(self):
        print('Connected!\n')
        await self.regenerate_short_term()  
        self.target_channel = self.get_channel(460214338003795989)
        self.ready_check = True
        print('\n~')
            

    @run_in_executor
    def do_sentiment_analysis(self, string):
        score = self.analyzer.polarity_scores(string)
        return score['compound']

    async def on_message_edit(self, before, after):
        if after.author == self.user or after.webhook_id or after.author.bot or isinstance(after.channel, discord.abc.PrivateChannel):
            return
            
        if after.id in self.guild_scores[after.channel.id]:
            await self.on_message(after)            

    async def on_message(self, message):
        await self.wait_until_really_ready()
        if message.author == self.user or message.webhook_id or message.author.bot or isinstance(message.channel, discord.abc.PrivateChannel):
            return

        sentiment_weight = await self.do_sentiment_analysis(message.clean_content)
        
        self.guild_scores[message.channel.id][message.id] = sentiment_weight
            
if __name__ == '__main__':
    bot = SentimentBot()
    bot.run()
