from typing import List, Optional, Tuple
import discord
from discord.ext import commands
import praw
import asyncio
import auths
import random
from time import gmtime
from food_post import FoodPost
import logging
import subprocess
import os
from predicates import is_admin
from help_commands import *
import redis_connector


logger = logging.getLogger()
logger.setLevel(logging.INFO)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
file_handler = logging.FileHandler(f'{os.getcwd()}/log.txt')  # TODO: figure out how to do this dynamically
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
stream_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


MAX_ALLOWED_SEARCH_SIZE = 500  # Not sure if the API actually lets me do this


# Instantiate the bot
bot_presence = discord.Activity(
    name='Finding good food Reddit posts. https://github.com/SaxyPandaBear/discord-food-bot',
    type=discord.ActivityType.playing)
bot = commands.Bot(command_prefix="!food ", description=bot_description(), activity=bot_presence)


stored_hour = None  # use this to determine when to post hourly


# function that posts a picture to the server on a timer
async def post_new_picture():
    global stored_hour
    await bot.wait_until_ready()  # doesn't execute until the client is ready
    while not bot.is_closed():
        current_time = gmtime().tm_hour
        if stored_hour is None or is_scheduled_time(current_time, stored_hour):
            # set stored_hour for next scheduled post
            stored_hour = current_time

            post_id, em = get_random_embedded_post()  # get a single post, and post it to each server
            for guild in bot.guilds:  # each server that this bot is active in
                channel = get_text_channel(guild)
                # because we can't filter for posts that are already there in each server before
                # generating the post, make the check here
                if redis_connector.post_already_used(post_id, logger):
                    # if the post is already there, generate a new one specific to this guild and return
                    p_id, diff_em = get_random_embedded_post(guild.id) # already written to file
                    await channel.send(embed=diff_em)
                    redis_connector.store_post_from_server(p_id, guild.id, logger)
                    continue
                await channel.send(embed=em)  # post to the default text channel
            # after the post has been posted to all connected servers,
            # persist the post
            redis_connector.store_post_from_server(post_id, 'all', logger) # right now, we don't use the value stored in Redis
        await asyncio.sleep(30)  # wait 30 seconds before checking again


# return True if is next hour, false otherwise
def is_scheduled_time(current_time: int, stored_hour: Optional[int] = None) -> bool:
    # if the hour that we store is 23, that means the next hour should be 0
    if stored_hour == 23:
        return current_time < 23
    else:
        # otherwise compare normally
        return current_time > stored_hour


# returns a discord.Embed with all of the necessary information for an embedded message
# this function accepts a guild parameter so that the ID can be written for the specific guild
# If a server ID is passed in, then the post is persisted in Redis,
# associated with the given server ID so that it doesn't get reposted
# elsewhere later
def get_random_embedded_post(server = None) -> Tuple[str, discord.Embed]:
    subs = get_list_of_subs()

    submission = get_submission_from_subs(subs)
    post = transpose_submission_to_food_post(submission)
    # need to write the id of this post into our file so we don't post it again later
    if server is not None:
        # write_id_to_file(post.id, server)
        redis_connector.store_post_from_server(post.id, server, logger)
    em = transpose_food_post_to_embed(post)
    return post.id, em


# takes a search query and returns the first result within the given
# subreddits. no duplicates are allowed
def search_posts(query: str, server: str) -> discord.Embed:
    subs = get_list_of_subs()

    # This searches, and returns a new post that isn't already persisted
    # to Redis
    submission = search_submission_from_subs(subs, query)
    
    # if submission is None, then the search returned no results
    if submission is None:
        return None
    
    # write_id_to_file(submission.id, server)
    redis_connector.store_post_from_server(submission.id, server, logger)
    post = transpose_submission_to_food_post(submission)
    em = transpose_food_post_to_embed(post)
    return em


# find the first, most relevant result from the search. do not include duplicates
def search_submission_from_subs(subs: List[str], query: str):
    subs_list = '+'.join(subs)
    for submission in reddit.subreddit(subs_list).search(query=query, sort='relevance', syntax='lucene'):
        if not redis_connector.post_already_used(submission.id, logger):
            return submission
    # if we didn't return in the iteration, just return the first relevant one this month
    try:
        # call to next() can raise StopIteration error if the list generator has no values left, meaning there were no results for this search
        result = next(reddit.subreddit(subs_list).search(query=query, sort='relevance', syntax='lucene', time_filter='month'))
        return result
    except StopIteration:
        logger.error(f'No results found for {query} in subs: {subs}')
        return None


# take a list of strings and concatenate them
def concat_strings(strings: List[str]) -> str:
    return ' '.join(strings)  # use join instead of + concatenation


# function that reads from the subreddits.txt file and returns a list of strings that are the read
# subreddits in the file
# Note: This assumes that the file exists in the same directory as this script
def get_list_of_subs() -> List[str]:
    with open('subreddits.txt', 'r') as file:
        subs = file.read().splitlines()  # readlines() returns strings with newline characters
    return list(filter(None, subs))  # just for sanity, purge empty strings before returning


# takes a Guild object and returns the first channel that the bot has access to post to.
# this is determined by using the Channel class's `permissions_for(..)` function
def get_text_channel(guild):
    member = guild.me
    for channel in guild.channels:
        if isinstance(channel, discord.TextChannel) and channel.permissions_for(member).send_messages:
            return channel
    return None  # somehow there isn't a text channel (not sure if it's even possible to get to this state


# a FoodPost makes it more readable to interface with different attributes needed for a discord.Embed object
# take a submission and return it's resulting FoodPost
def transpose_submission_to_food_post(submission) -> FoodPost:
    logger.info(submission)
    sub_id = submission.id
    url = get_image_url(submission)
    # permalink does not give the full URL, so build it instead.
    permalink = 'https://www.reddit.com{}'.format(submission.permalink)
    title = submission.title
    return FoodPost(id=sub_id, title=title, image_url=url, permalink=permalink)


# because a submission's URL can either be the link to a hosted image, or to the comments section of it's own
# submission, let's try to get the actual image every time.
def get_image_url(submission) -> str:
    return submission.url  # TODO: figure out what kinds of data can appear


# takes a FoodPost and maps its attributes to attributes of a discord.Embed object
# that will be posted by the bot
def transpose_food_post_to_embed(post: FoodPost) -> discord.Embed:
    title = post.title
    desc = post.post_url
    color = 0xDB5172
    em = discord.Embed(title=title, description=desc, color=color)
    if post.image_url != '':  # safeguard for non-functional urls
        em.set_image(url=post.image_url)
    return em


# returns a random submission from the given list of subreddits
# uses the top 20 hot submissions
# has a list of ids for posts that were already posted.
def get_submission_from_subs(subs):
    submissions = []
    subs_list = '+'.join(subs)  # should have a string like "a+b+c"
    limit = 20  # this is the maximum number of submissions to poll
    for submission in reddit.subreddit(subs_list).hot(limit=limit):
        if not redis_connector.post_already_used(submission.id, logger):
            submissions.append(submission)
    # need a check in case all of the submissions were already posted
    hit_max_search = False
    while len(submissions) < 1:
        if limit == MAX_ALLOWED_SEARCH_SIZE and not hit_max_search:
            hit_max_search = True
        if limit == MAX_ALLOWED_SEARCH_SIZE and hit_max_search:
            raise Exception("Reached search limit, but couldn't find a new post")
        for submission in reddit.subreddit(subs_list).hot(limit=limit):
            if not redis_connector.post_already_used(submission.id, logger):
                submissions.append(submission)
        # at some point either we will get rate limited, or we'll find a new post
        # by including a max search size, a big TODO would be to actually paginate
        # the search... but oh well
        limit = min(limit * 2, MAX_ALLOWED_SEARCH_SIZE)
    return random.choice(submissions)


# delete all of the records stored in Redis
def clear_ids():
    redis_connector.flush_all_records(logger)


# takes a query for searching and applies the necessary restrictions
# we want to limit our searches to just the title of the post, and also
# exclude all self posts (text posts)
def build_query(terms) -> str:
    return 'title:"{}" self:no'.format(terms)


# restarts the bot using pm2's restart functionality.
# if the bot restarts successfully, then the bot will have been
# abruptly stopped, not gracefully.
def restart_bot():
    # first, need to get this process's ID from pm2.
    # then, invoke restart on it.
    id_output = subprocess.run(["pm2", "id", "food_waifu"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    logger.info(id_output)
    # the output of the above command would be in the form of "[ id ]" with the intended whitespace illustrated
    # need to strip the characters around the ID
    pm2_id = id_output.stdout.decode('utf-8').replace("[", "").replace("]", "").strip()
    if len(pm2_id) == 0: 
        return False
    logger.info(pm2_id)

    # attempt to restart the bot
    subprocess.run(["pm2", "restart", str(pm2_id)])
    return False


@bot.event
async def on_ready():
    logger.info(f"Username: {bot.user.name}")
    logger.info(f"ID: {bot.user.id}")

@bot.command(description="Post a new food picture into the channel", help=help_bot_random(), brief="Post a new food picture into the channel")
async def new(context):
    post_id, em = get_random_embedded_post(context.guild.id)
    await context.send(embed=em)

@bot.command(description="Searches for a new food picture to post into the channel", help=help_bot_search(), usage="something I want to search separated by spaces", brief="Searches for a new food picture to post into the channel")
async def search(context, *search_terms: str):
    if len(search_terms) < 1:
        await context.send("Specify at least one term to search for")
        return
    terms = concat_strings(search_terms)
    query = build_query(terms)
    em = search_posts(query, context.guild.id)
    if em is None:
        await context.send(f"No titles containing {terms} found in defined subreddits")
        return
    else:
        await context.send(embed=em)
        return

@bot.command(description="Clears the stored list of previous posts", help=help_bot_clear(), brief="Clears the stored list of previous posts")
@commands.guild_only()
@is_admin() # restrict this command to Guild channels
async def clear(context):
    clear_ids()
    await context.send("Successfully cleared contents")

@bot.command(description="Restarts the bot on request", help=help_bot_restart(), brief="Restarts the bot on request")
@commands.guild_only()
@is_admin() # restrict this command to Guild channels
async def restart(context):
    if not restart_bot():
        await context.send("Error when attempting to restart bot. Please restart manually.")

@bot.command(description="Print all stored Redis keys to log", help=help_bot_list_keys(), brief="Print all stored Redis keys to log")
@is_admin()
async def list_keys(context):
    if redis_connector.enumerate_keys(logger):
        await context.send("Successfully printed Redis keys to log")
    else:
        await context.send("Error occurred when printing Redis keys to log")

# Starts the discord client
logger.info("Creating looped task")
bot.loop.create_task(post_new_picture())  # looped task
logger.info("Finished creating looped task")
try:
    reddit = praw.Reddit(client_id=auths.reddit_client_id,
                     client_secret=auths.reddit_client_secret,
                     user_agent='discord:food_waifu:v0.2')  # instantiate a new Reddit Client
    bot.run(auths.discord_token)
except Exception as e:
    logger.error(repr(e))
