#!/usr/bin/env python

"""Bot for subreddit r/TheGoldilocksZone. Bans the users with the most downvoted and upvoted posts on the sub every day.

Environment variables:
    BAN_USERS -- users will be auto-banned if this is set to 'True'.
    STICKY_ANNOUNCEMENT -- new daily announcement post will be auto-stickied if this is set to 'True'.

    MEMCACHEDCLOUD_SERVERS, MEMCACHEDCLOUD_USERNAME, MEMCACHEDCLOUD_PASSWORD -- login for memcache.

    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_PASSWORD, REDDIT_USERNAME -- login for reddit account, should be mod.
"""

import os
import time
import logging

import praw
import prawcore
import bmemcached
import dateutil.rrule


# TODO: test
# TODO: account for post length limit by letting bot create new consecutive hall of fame posts


logging.basicConfig(level=logging.INFO)


__version__ = '0.6.0'


SUBREDDIT = 'TheGoldilocksZone'
USER_AGENT = f'python3.9.0:thegoldilockszone-bot:v{__version__} (by /u/Sgp15)'

# Hour (24H) to run each day. This is noon UCT.
RUN_TIME = 12
# The flair ID for the winner announcement flair
ANNOUNCEMENT_FLAIR_ID = 'e682b0e6-358c-11eb-b352-0e5ad39b714b'
# Flair text for exempt users
EXEMPT_FLAIR_TEXT = 'Exempt'
# The post ID for the Hall of banned users post. Must be created manually as a post on the bot account
HOF_SUBMISSION_ID = 'k82mtd'
# Determines whether the bot will auto ban the winner and loser, or leave it to be done manually.
# Intended for lower risk testing.
if os.environ.get('BAN_USERS'):
    if os.environ.get('BAN_USERS') == 'True':
        BAN_USERS = True
    else:
        BAN_USERS = False
else:
    BAN_USERS = False
# Whether or not to sticky the announcement post
if os.environ.get('STICKY_ANNOUNCEMENT'):
    if os.environ.get('STICKY_ANNOUNCEMENT') == 'True':
        STICKY_ANNOUNCEMENT = True
    else:
        STICKY_ANNOUNCEMENT = False
else:
    STICKY_ANNOUNCEMENT = True
# String to be added before usernames, u/ if you want to mention them or empty otherwise
if os.environ.get('USER_MENTION'):
    USER_MENTION = os.environ.get('USER_MENTION')
else:
    USER_MENTION = 'u/'
# If this constant is True, the bot will run on start as well as at the designated time
if os.environ.get('RUN_ON_START'):
    if os.environ.get('RUN_ON_START') == 'True':
        RUN_ON_START = True
    else:
        RUN_ON_START = False
else:
    RUN_ON_START = True


def get_time_till_next_run(run_hour=RUN_TIME):
    next_run_datetime = list(dateutil.rrule.rrule(freq=dateutil.rrule.HOURLY, count=1,
                                                  byhour=run_hour, byminute=0, bysecond=0))[0]
    next_run_seconds = next_run_datetime.timestamp()
    time_till_next_run = next_run_seconds - time.time()

    return time_till_next_run


def get_top_and_bottom_post(subreddit_instance):
    """Get the posts with highest and lowest score for the last day in a subreddit."""
    # Get all top posts for the day
    posts_today = list(subreddit_instance.top(time_filter='day'))
    logging.info('Got post list for today.')

    # Sort them by score
    # Currently, they're sorted by score - the sum of upvotes and downvotes.
    # However, it's probably possible to get exactly how many upvotes and downvotes they had.
    posts_today.sort(key=lambda submission: submission.score, reverse=True)

    top_post = first_post_not_exempt(posts_today)
    logging.info(f'Got top post {top_post.id} by {top_post.author.name}.')
    bottom_post = first_post_not_exempt(reversed(posts_today))
    logging.info(f'Got bottom post {bottom_post.id} by {bottom_post.author.name}.')

    return top_post, bottom_post


def first_post_not_exempt(post_list, exempt_flair_text=EXEMPT_FLAIR_TEXT):
    """Return the first submission object in the list whose author does not have the exempt flair."""
    for post in post_list:
        if post.author_flair_text != exempt_flair_text:
            return post


def ban_winner_and_loser(subreddit_instance, top_post, bottom_post, date=None):
    """Ban the authors of the two given posts from the given subreddit."""
    if date is None:
        date = time.strftime('%d/%m/%Y')

    # Ban the top poster for today
    ban_reason_top = f"Most upvoted post of the day {date}"
    subreddit_instance.banned.add(top_post.author.name, ban_reason=ban_reason_top)
    logging.info('Banned winner.')

    # Ban the bottom poster for today
    ban_reason_bottom = f"Least upvoted post of the day {date}"
    subreddit_instance.banned.add(bottom_post.author.name, ban_reason=ban_reason_bottom)
    logging.info('Banned loser.')


def create_new_announcement_post(subreddit_instance, date, top_post, bottom_post):
    """Submit a new announcement post, and return it as a submission object."""
    announcement_post_title = f"Today's ({date}) winner and loser!"
    announcement_post_body = f"""{USER_MENTION}{top_post.author.name} is our unfortunate \
[winner]({top_post.permalink})!    
u/{bottom_post.author.name} is our equally as unfortunate [loser]({bottom_post.permalink})!    
Keep the posts coming fellas, you could be added to our hall of winners and losers if you’re (un)lucky enough!"""

    new_announcement = subreddit_instance.submit(title=announcement_post_title,
                                                 selftext=announcement_post_body,
                                                 flair_id=ANNOUNCEMENT_FLAIR_ID)
    logging.info('Created new announcement post.')

    return new_announcement


def update_stickied_announcement(reddit_instance, old_announcement_id, new_announcement):
    """Unsticky the post with ID old_announcement_id, and sticky the new one given as an object."""
    if old_announcement_id:
        try:
            old_announcement = reddit_instance.submission(str(old_announcement_id))
        except prawcore.exceptions.NotFound:
            logging.error('Unable to get the last announcement post to unsticky it. Skipping.')
        else:
            logging.info(f'Got the old announcement post {old_announcement_id}.')
            old_announcement.mod.distinguish(sticky=False)
            new_announcement.mod.distinguish(sticky=True)
            logging.info('Stickied the new announcement post and unstickied the old one.')


def update_hall_of_fame_post(reddit_instance, top_post, bottom_post, hof_submission_id=HOF_SUBMISSION_ID):
    """Edit the hall of fame post with ID HOF_SUBMISSION_ID to append the given posts to it."""
    hof_post = reddit_instance.submission(hof_submission_id)
    logging.info(f'Got old hall of fame post {hof_submission_id}.')
    hof_body_current = hof_post.selftext

    hof_body_addition = f"""    
{USER_MENTION}{top_post.author.name} : [post]({top_post.permalink})    
{USER_MENTION}{bottom_post.author.name} : [post]({bottom_post.permalink})"""
    hof_body_new = hof_body_current + hof_body_addition

    hof_post.edit(hof_body_new)
    logging.info('Edited hall of fame post successfully.')


def main():
    """Run the bot."""
    run_on_start = RUN_ON_START

    memcache = bmemcached.Client(os.environ['MEMCACHEDCLOUD_SERVERS'].split(','),
                                 os.environ['MEMCACHEDCLOUD_USERNAME'],
                                 os.environ['MEMCACHEDCLOUD_PASSWORD'])
    logging.debug('Connected to memcache.')

    reddit = praw.Reddit(client_id=os.environ['REDDIT_CLIENT_ID'],
                         client_secret=os.environ['REDDIT_CLIENT_SECRET'],
                         password=os.environ['REDDIT_PASSWORD'],
                         user_agent=USER_AGENT,
                         username=os.environ['REDDIT_USERNAME'])
    reddit.validate_on_submit = True
    logging.info('Logged in.')

    subreddit = reddit.subreddit(SUBREDDIT)

    old_announcement_id = memcache.get('old_announcement_id')

    while True:
        # Wait until it's time to run each day
        if run_on_start:
            run_on_start = False
        else:
            time.sleep(get_time_till_next_run())

        # Do the stuff
        date = time.strftime('%d/%m/%Y')
        logging.info(f"The time is {time.strftime('%H:%M:%S')} on {date}, running.")

        top_post, bottom_post = get_top_and_bottom_post(subreddit)

        if BAN_USERS:
            ban_winner_and_loser(subreddit, top_post, bottom_post, date)

        # Make a new announcement post
        new_announcement = create_new_announcement_post(subreddit, date, top_post, bottom_post)

        # Sticky today's post and unsticky yesterday's
        if STICKY_ANNOUNCEMENT:
            update_stickied_announcement(reddit, old_announcement_id, new_announcement)
        # Make the just created announcement the old one for use next time, and save it to memcache for persistence.
        old_announcement_id = new_announcement.id
        memcache.set('old_announcement_id', old_announcement_id)

        # Edit the hall of fame post
        update_hall_of_fame_post(reddit, top_post, bottom_post)

        # Ensure no double dipping
        time.sleep(2)


if __name__ == '__main__':
    main()
