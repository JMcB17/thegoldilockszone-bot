import os
import time
import logging

import praw
import prawcore
import bmemcached


# TODO: test
# TODO: organise code better now that this is going to production
# TODO: more elegant time checking
# TODO: account for post length limit by letting bot create new consecutive hall of fame posts


logging.basicConfig(level=logging.INFO)


__version__ = '0.4.0'


SUBREDDIT = 'TheGoldilocksZone'
USER_AGENT = f'python3.9.0:thegoldilockszone-bot:v{__version__} (by /u/Sgp15)'

# Time to run each day, in the form hh:mm:ss. This is noon UCT.
RUN_TIME = '12:00:00'
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
    STICKY_ANNOUNCEMENT = 'u/'


def first_post_not_exempt(post_list, exempt_flair_text=EXEMPT_FLAIR_TEXT):
    for post in post_list:
        if post.author_flair_text != exempt_flair_text:
            return post


def ban_winner_and_loser(subreddit, top_post, bottom_post, date=None):
    if date is None:
        date = time.strftime('%d/%m/%Y')

    # Ban the top poster for today
    ban_reason_top = f"Most upvoted post of the day {date}"
    subreddit.banned.add(top_post.author.name, ban_reason=ban_reason_top)
    logging.info('Banned winner.')

    # Ban the bottom poster for today
    ban_reason_bottom = f"Least upvoted post of the day {date}"
    subreddit.banned.add(bottom_post.author.name, ban_reason=ban_reason_bottom)
    logging.info('Banned loser.')


def main():
    memcache = bmemcached.Client(os.environ['MEMCACHEDCLOUD_SERVERS'].split(','),
                                 os.environ['MEMCACHEDCLOUD_USERNAME'],
                                 os.environ['MEMCACHEDCLOUD_PASSWORD'])
    logging.info('Connected to memcache.')

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
        if time.strftime('%H:%M:%S') == RUN_TIME:
            logging.info(f"The time is {time.strftime('%H:%M:%S')}, running.")

            # Get all top posts for the day
            posts_today = list(subreddit.top(time_filter='day'))
            logging.info('Got post list for today.')
            # Sort them by score
            # Currently, they're sorted by score - the sum of upvotes and downvotes.
            # However, it's probably possible to get exactly how many upvotes and downvotes they had.
            posts_today.sort(key=lambda submission: submission.score, reverse=True)
            top_post = first_post_not_exempt(posts_today)
            logging.info(f'Got top post {top_post.id} by {top_post.author.name}.')
            bottom_post = first_post_not_exempt(reversed(posts_today))
            logging.info(f'Got bottom post {bottom_post.id} by {bottom_post.author.name}.')

            date = time.strftime('%d/%m/%Y')

            if BAN_USERS:
                ban_winner_and_loser(subreddit, top_post, bottom_post, date)

            # Make a new announcement post
            announcement_post_title = f"Today's ({date}) winner and loser!"
            announcement_post_body = f"""{USER_MENTION}{top_post.author.name} is our unfortunate \
[winner]({top_post.permalink})!    
u/{bottom_post.author.name} is our equally as unfortunate [loser]({bottom_post.permalink})!    
Keep the posts coming fellas, you could be added to our hall of winners and losers if you’re (un)lucky enough!"""
            new_announcement = subreddit.submit(title=announcement_post_title,
                                                selftext=announcement_post_body,
                                                flair_id=ANNOUNCEMENT_FLAIR_ID)
            logging.info('Created new announcement post.')
            # Sticky today's post and unsticky yesterday's
            if STICKY_ANNOUNCEMENT and old_announcement_id:
                try:
                    old_announcement = reddit.submission(str(old_announcement_id))
                except prawcore.exceptions.NotFound:
                    logging.error('Unable to get the last announcement post to unsticky it. Skipping.')
                else:
                    logging.info(f'Got the old announcement post {old_announcement_id}.')
                    old_announcement.mod.distinguish(sticky=False)
                    new_announcement.mod.distinguish(sticky=True)
                    logging.info('Stickied the new announcement post and unstickied the old one.')
            # Make the just created announcement the old one for use next time, and save it to memcache for persistence.
            old_announcement_id = new_announcement.id
            memcache.set('old_announcement_id', old_announcement_id)

            # Edit the hall of fame post
            hof_post = reddit.submission(HOF_SUBMISSION_ID)
            logging.info(f'Got old hall of fame post {HOF_SUBMISSION_ID}.')
            hof_body_current = hof_post.selftext

            hof_body_addition = f"""    
{USER_MENTION}{top_post.author.name} : [post]({top_post.permalink})    
{USER_MENTION}{bottom_post.author.name} : [post]({bottom_post.permalink})"""
            hof_body_new = hof_body_current + hof_body_addition

            hof_post.edit(hof_body_new)
            logging.info('Edited hall of fame post successfully.')

            # Ensure no double dipping
            time.sleep(2)

        time.sleep(0.5)


if __name__ == '__main__':
    main()
