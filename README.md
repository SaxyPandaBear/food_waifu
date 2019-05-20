Food Waifu
===========

Discord bot that posts a picture of food once a day.

## Features

`!food` is the command invoked in order to interact with this bot.

`!food help` prints a description of the bot, as well as lists out options for usage.

- `!food help [function]` prints a description of the given function, as well as example usage.

`!food random` picks a random picture of food and posts it to the channel.

`!food search [query]` takes in a search query and returns the first, most relevant result *that is not a duplicate*.
 
 `!food clear` clears the contents of the `post_ids.txt` file, which contains previously posted content. This allows reposted material.

## Setup

- Python 3.6.3
- [discord.py](https://github.com/Rapptz/discord.py) v1.1.0
- [PRAW](https://praw.readthedocs.io/en/latest/index.html) v6.2.0

A simple way to get the required libraries is through Pip: `pip install -r requirements.txt`

To set up the bot, it requires a file, `auths.py` (a template is provided). This file contains all of the 
authentication for both Discord and Reddit, and is necessary to interface with their APIs.

On top of this, a file called `subreddits.txt` must be in the same directory as the bot (template provided). This 
file will contain a list of subreddit names that will be used by the bot to find submissions to post. This list 
requires the items to be all lowercase, even if the subreddit itself uses capitalization.

For example: for a subreddit /r/FooBar, the entry in the text file would simply be `foobar`

This bot also generates a file that contains ids of submissions that have already been posted by the bot, in a file
named `post_ids.txt`. This file should not be modified unless the user wants to flush out all of the entries in the 
file and wants to start over without knowledge of previously posted material. The file functions as a safeguard against
duplicate posts, i.e.: cross posts between subreddits.

## TODO:

- Save previously posted content separately for different servers.
