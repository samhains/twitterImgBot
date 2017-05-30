#!/usr/bin/python

import sqlite3
from settings import config
from bot import status
from bot import requests
from bot import timeline
from logs import logger
from logs import banner
import random
import argparse
import sys
import os

"""The glue that holds it all together: uses all the other modules
to handle requests, post tweets if chance is met, calls the logger
and parses the CLI arguments.

Some lingo used through the code:
    master_account is setted in the config, should be the owner of the bot.
    gift, gifted: a gift is a request for the bot to tweet an image for a third
                  person, like: "hey bot give my gf @girlfriend an image!"
"""

def handle_tweet_posting(text, reply_id, test=False):
    """Sends a tweet to twitter, making sure it is not repeated and logs
    it to our log file. If no non repeated or non banned images found, return
    False. If operation was succesful, return True.

    text = text to be tweeted,
    reply_id = the id of the tweet we'll be replying to,
    test = if bot was executed with test flag or not.
    """

    log = config.log_file
    tolerance = config.tolerance
    banned_list = config.banned_file
    #media, amount_media_available = get_random_image_from_folder(config.source_folder)
    url, caption = get_random_image_from_sql(test)
    print(caption)
    #t = status.Tweet(media, "", 0)
    t = status.Tweet(url, caption)

    tolerance = 0
    while t.is_already_tweeted(log, tolerance) or t.is_banned(banned_list):
        new_media = get_random_image_from_folder(config.source_folder)
        t.change_media(new_media)
        tolerance += 1
        if tolerance >= amount_media_available:
            return False

    if not test:
        tweet_id = t.post_to_twitter(api)
        #log_line = logger.log_line(tweet_id, media, reply_id)

        # if it was a test, don't post it and mark the log line as such
        #log_line = logger.log_line("0", 'TEST_ID', "TEST_PATH", reply_id)

    #logger.add_line_to_log(log_line, log)
    return True

def get_random_algo():
    prob = random.random()
    if (prob < 0.15):
        return 'v1_dcgan'
    elif (prob < 0.44):
        return 'v3_dcgan'
    else:
        return 'v3_p2p'

def get_random_caption(cap1, cap2):
    prob = random.random()
    if (prob < 0.75):
        print('oldcap')
        return cap1
    else:
        print('newcap')
        return cap2

def get_random_image_from_sql(test):
    """Returns a random file from folder and the amount of files in the folder.
    It's up the user to check (or not) if the return file is actually an
    image.
    """

    conn = sqlite3.connect('/tmp/test.db')
    c = conn.cursor()
    algo = get_random_algo()
    q = "SELECT url,caption,caption_im2txt,uuid FROM Image WHERE number == 0 AND algo == '{}' ORDER BY RANDOM()".format(algo)
    c.execute(q)
    print('querying', q)
    url, caption, caption_im2txt, uuid = c.fetchone()
    print('gettin sum', url, caption, caption_im2txt)
    caption = get_random_caption(caption, caption_im2txt)
    url = '/home/ubuntu/data/images/'+url.split('/')[-1]	
    print("tweeting:", uuid, caption, "test:", test)
    if not test:
        print("Updating image number to 1 with uuid:", uuid)
        q = "UPDATE Image SET number = 1 WHERE uuid == '{}'".format(uuid)
        c.execute(q) 
        conn.commit()
    conn.close()
    return url, caption


def get_random_image_from_folder(folder):
    """Returns a random file from folder and the amount of files in the folder.
    It's up the user to check (or not) if the return file is actually an
    image.
    """
    media_list = []
    for dirpath, dirnames, files in os.walk(folder):
        for f in files:
            media_list.append(os.path.join(dirpath, f))
    media = random.choice(media_list)
    return media, len(media_list)


def respond_to_simple_request(request_tweet):
    """Gets the information neccesary from request_tweet to reply to it.
    """
    reply_id = request_tweet.id
    user_name = request_tweet.user.screen_name
    answer = random.choice(config.request_answers)
    text = '@' + user_name + ' ' + answer
    return handle_tweet_posting(text, reply_id)


def respond_to_gift_request(request_tweet):
    """Gets the information neccesary from request_tweet to reply to the user
    specified in the request_tweet, as this is a gift request.
    """
    reply_id = request_tweet.id
    user_giver = request_tweet.user.screen_name
    user_gifted = ('@' + requests.request_to_whom(request_tweet))
    answer = random.choice(config.request_to_third_answers)
    text = (user_gifted + ' ' + answer + ' @' + user_giver)
    return handle_tweet_posting(text, reply_id)


def orders():
    """Handle orders given to the bot via replies"""
    log = config.log_file
    time = config.time_tolerance
    master = config.master_account
    ban_command = config.ban_command
    master_account = config.master_account
    mentions = requests.mentions(config.bot_account, api)


    for tweet in relevant_mentions:
        if requests.is_img_request(tweet, config.request_command):
            if requests.mentions_third_user(tweet):
                respond_to_gift_request(tweet)
            else:
                respond_to_simple_request(tweet)

    for tweet in master_mentions:
        if requests.is_delete_order(tweet, master, ban_command):
            id_to_delete = tweet.in_reply_to_status_id
            timeline.delete_tweet_by_id(tweet.in_reply_to_status_id, api)
            banner.ban_image_by_tweet_id(id_to_delete,
                                         config.banned_file,
                                         config.log_file)

            logger.add_banned_to_log(post_number, tweet.id, config.log_file)


def get_post_number_from_log(log_file):
    """Tries to get a post number from the log. If it can't, it means
    it must be the first. Returns the number as a string.
    """
    try:
        post_number = open(log_file, 'r').readlines()[-1]
        post_number = post_number.split()[0]
        return str(int(post_number)+1)
    except (IndexError, ValueError):
        return "1"


def get_post_number(manual_post_number):
    """Gets the post number either from the manual_post_number set by
    the user from the CLI or from the log. Returns number as string.
    """
    if manual_post_number is not None:
        return manual_post_number
    else:
        return get_post_number_from_log(config.log_file)


def create_tweet_text(raw_text, post_number, tweet_post_number):
    """Decides which should be the tweet text based on the raw_text setted
    by the user, the post_number and the boolean tweet_post_number.
    """
    if tweet_post_number:
        if raw_text:
            tweet_text =  "No. " + str(post_number) + " " + raw_text
        else:
            tweet_text =  "No. " + str(post_number)
    else:
        tweet_text = raw_text

    return tweet_text


def parse_args(args):
    """Parses arguments from command line"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--tweet", help="Ignores execution chance, always run",
                        action="store_true")
    parser.add_argument("--test", help="Wont't tweet, just write to log",
                        action="store_true")
    parser.add_argument("--tweetnumber", help="If you were already using this "
                        "bot and you want to start using the post_tweet_number"
                        " function you'll need to tell the bot where to "
                        "start. Use this option ONLY ONCE ")
    return parser.parse_args(args)


def main():
    """Runs the whole program, the function of all functions
    Will check the arguments from the CLI, the settings from the settings file
    and will decide if a tweet must be posted by checking our
    tweet_chance in the settings against a random integer between 0 and 99
    """

    global post_number  # it's needed both here and in handle_tweet_posting()
    global api  # it's used absolutely everywhere, so might as well be global

    args = parse_args(sys.argv[1:])
    test = args.test
    forceTweet = args.tweet
    manual_post_number = args.tweetnumber

    api = config.api

    tweet_raw_text = config.tweet_this_text
    tweet_post_number = config.tweet_post_number

    tweet_text = create_tweet_text(tweet_raw_text, 0, tweet_post_number)

    #orders()

    if random.randint(0, 99) < config.chance or test or forceTweet:
        tweeted_successfully = handle_tweet_posting(tweet_text, None, test)
        if not tweeted_successfully:
            warning = "!CRITICAL! No non-repeated or non-banned images found"
            logger.add_warning_to_log(post_number, warning, config.log_file)

if __name__ == "__main__":
    main()
