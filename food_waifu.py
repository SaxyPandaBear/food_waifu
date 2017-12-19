import discord
import praw
import asyncio
import auths
import random
from food_post import FoodPost


client: discord.Client = discord.Client()  # instantiate a new Discord Client
reddit = praw.Reddit(client_id=auths.reddit_client_id,
                     client_secret=auths.reddit_client_secret,
                     user_agent='discord:food_waifu:v0.1')  # instantiate a new Reddit Client

# TODO: rewrite parts of the bot to run asynchronously


@client.event
async def on_ready():
    print('Username: {0}\nID: {1}'.format(client.user.name, client.user.id))


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return  # we want to filter out messages from our bot
    if not message.content.startswith('!food'):
        return  # don't process messages without the "!food" tag
    msg_contents = message.content.split(' ')
    if len(msg_contents) < 2:
        msg = bot_description() + '\n' + help_message()  # send 1 concatenation rather than 2 messages
        await client.send_message(message.channel, msg)
        return
    msg_contents = msg_contents[1:]  # ignore the "!food" part of the message

    # "!food help [function]"
    # if an optional [function] argument is given, the bot prints a description
    # of that function's usage,
    # otherwise, it just prints out the generic help text that is printed out
    # when an unrecognized command is given, or no commands are given.
    if msg_contents[0].lower() == 'help':
        # help no longer is a single command usage.
        # it can be used to get more detailed info on other available functions
        if len(msg_contents) == 1:  # no args were passed in
            await client.send_message(message.channel, help_message())
        else:
            if msg_contents[1].lower() == 'random':
                await client.send_message(message.channel, help_bot_random())
            elif msg_contents[1].lower() == 'search':
                await client.send_message(message.channel, help_bot_search())
            else:
                await client.send_message(message.channel, help_message())
    elif msg_contents[0].lower() == 'random':
        em = get_embedded_post()
        await client.send_message(message.channel, embed=em)
    elif msg_contents[0].lower() == 'search':
        # need to make sure there is actually a term to be searched
        if len(msg_contents) < 2:
            await client.send_message(message.channel, help_bot_search())
            return
        else:
            # for now just concatenate the search terms and then print them out
            # to make sure I concatenated them correctly
            terms = concat_strings(msg_contents[1:])  # don't include "search"
            em = search_posts(query=terms)
            await client.send_message(message.channel, embed=em)
    else:
        msg = "Unrecognized operation: '{0}'\n{1}".format(msg_contents[0], help_message())
        await client.send_message(message.channel, msg)  # opt to send 1 message instead of 2.
    # TODO: see how difficult it will be to search for a specific dish
    pass


# function that posts a picture to the server on a timer
async def post_new_picture():
    await client.wait_until_ready()  # doesn't execute until the client is ready
    while not client.is_closed:
        em = get_embedded_post()  # get a single post, and post it to each server
        # TODO: figure out how to make this asynchronous to support a large number of servers
        '''
        Current error
        ==============
        Task exception was never retrieved
        future: <Task finished coro=<post_new_picture() done, defined at food_waifu.py:68> 
            exception=TypeError("'async for' requires an object with __aiter__ method, got dict_values",)>
        Traceback (most recent call last):
            File "food_waifu.py", line 72, in post_new_picture
            async for server in client.servers:  # each server that this bot is active in
        TypeError: 'async for' requires an object with __aiter__ method, got dict_values
        '''
        for server in client.servers:  # each server that this bot is active in
            channel = get_default_text_channel(server)
            await client.send_message(channel, embed=em)  # post to the default text channel
        # we successfully (hopefully) posted an image to each server this bot is in,
        # but we don't want to post duplicates later.
        # write all of the ids used to a file
        await asyncio.sleep(86400)  # once a day


# returns a discord.Embed with all of the necessary information for an embedded message
def get_embedded_post():
    subs = get_list_of_subs()
    ids = get_previous_post_ids()

    submission = get_submission_from_subs(subs, ids)
    post = transpose_submission_to_food_post(submission)
    # need to write the id of this post into our file so we don't post it again later
    write_id_to_file(post.id)
    em = transpose_food_post_to_embed(post)
    return em


# takes a search query and returns the first result within the given
# subreddits. this includes duplicates
def search_posts(query):
    subs = get_list_of_subs()
    ids = get_previous_post_ids()

    submission = search_submission_from_subs(subs, query)
    if submission.id not in ids:  # if it's not a duplicate, write the id
        write_id_to_file(submission.id)
    post = transpose_submission_to_food_post(submission)
    write_id_to_file(post.id)
    em = transpose_food_post_to_embed(post)
    return em


# find the first, most relevant result from the search. include duplicates
def search_submission_from_subs(subs, query):
    subs_list = '+'.join(subs)
    return next(reddit.subreddit(subs_list).search(query=query, sort='relevance', syntax='lucene', time_filter='month'))


# takes a Reddit submission ID and writes it to the file of previous post ids used.
# the 'a' mode for open() will create a new file if it does not already exist,
# and writes appending to the file as opposed to truncating.
def write_id_to_file(post_id):
    with open('post_ids.txt', 'a') as file:
        file.write('{}\n'.format(post_id))


# take a list of strings and concatenate them
def concat_strings(strings):
    return ' '.join(strings)  # use join instead of + concatenation


# function that reads from the subreddits.txt file and returns a list of strings that are the read
# subreddits in the file
# Note: This assumes that the file exists in the same directory as this script
def get_list_of_subs():
    with open('subreddits.txt', 'r') as file:
        subs = file.read().splitlines()  # readlines() returns strings with newline characters
    return list(filter(None, subs))  # just for sanity, purge empty strings before returning


# function that reads from the post_ids.txt file and returns a list of ids.
# the ids in the file are Reddit ids for given posts that the bot has already processed and used
# Note: This assumes that the file exists in the same directory as this script
def get_previous_post_ids():
    try:
        file = open('post_ids.txt', 'r')
    except IOError:
        return []
    # if made it this far, no error occurred.
    ids = file.read().splitlines()  # readlines() returns strings with newline characters
    file.close()  # almost forgot to close the file
    return list(filter(None, ids))  # no empty strings allowed


# returns a formatted string that describes the bot's usage
def bot_description():
    return 'This bot posts pictures of food on request, and on a daily schedule.\n' \
           'Read more about this bot, or contribute to it at https://github.com/SaxyPandaBear/food_waifu'


# returns a formatted string that lists the available functions
def help_message():
    return 'Available functions: [ random, search ]\n' \
           'Type "!food help [function]" for more details on a specific function and it\'s usage.'


# returns a string that details the usage of the 'random' function of the bot
def help_bot_random():
    return '[random] => the bot posts an embedded message with a picture of food.\n' \
           'Example usage: "!food random"'


# returns a string that details the usage of the 'search' function of the bot
def help_bot_search():
    return '[search] => the bot takes in search terms and posts the first picture it finds' \
           'based on those terms. If the picture has already been posted, the bot attempts' \
           'to post the next picture, until it exhausts all of its options.\n' \
           'Example usage: "!food search pizza"'


# takes a server object and searches for the first text channel it finds.
# Discord has decided to not designate a specific "default" text channel anymore,
# and the default is now the first text channel.
def get_default_text_channel(server: discord.Server):
    for channel in server.channels:
        if channel.type == discord.ChannelType.text:  # the first text channel is our default channel
            return channel
    return None  # somehow there isn't a text channel (not sure if it's even possible to get to this state


# a FoodPost makes it more readable to interface with different attributes needed for a discord.Embed object
# take a submission and return it's resulting FoodPost
def transpose_submission_to_food_post(submission):
    sub_id = submission.id
    url = get_image_url(submission)
    # permalink does not give the full URL, so build it instead.
    permalink = 'https://www.reddit.com{}'.format(submission.permalink)
    title = submission.title
    return FoodPost(id=sub_id, title=title, image_url=url, permalink=permalink)


# because a submission's URL can either be the link to a hosted image, or to the comments section of it's own
# submission, let's try to get the actual image every time.
def get_image_url(submission):
    return submission.url  # TODO: figure out what kinds of data can appear


# takes a FoodPost and maps its attributes to attributes of a discord.Embed object
# that will be posted by the bot
def transpose_food_post_to_embed(post: FoodPost):
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
def get_submission_from_subs(subs, already_posted):
    submissions = []
    subs_list = '+'.join(subs)
    # should have a string like "a+b+c"
    limit = 20  # this is the maximum number of submissions to poll
    for submission in reddit.subreddit(subs_list).hot(limit=limit):
        if submission.id not in already_posted:
            submissions.append(submission)
    # need a check in case all of the submissions were already posted
    while len(submissions) < 1:
        for submission in reddit.subreddit(subs_list).hot(limit=limit):
            if submission.id not in already_posted:
                submissions.append(submission)
        limit *= 2  # at some point either we will get rate limited, or we'll find a new post
    return random_submission(submissions)


def random_submission(submissions):
    index = random.randint(0, len(submissions) - 1)
    return submissions[index]


# Starts the discord client
client.loop.create_task(post_new_picture())  # looped task
client.run(auths.discord_token)
