import os
import time

import praw


# TODO: add functionality to add the winner to the 'Hall of banned users'
# TODO: test
# TODO: organise code better now that this is going to production


__version__ = '0.3.0'


SUBREDDIT = 'TheGoldilocksZone'
USER_AGENT = f'python3.9.0:thegoldilockszone-bot:v{__version__} (by /u/Sgp15)'

# Time to run each day, in the form hh:mm:ss. This is noon UCT.
RUN_TIME = '12:00:00'
# The flair ID for the winner announcement flair
ANNOUNCEMENT_FLAIR_ID = 'e682b0e6-358c-11eb-b352-0e5ad39b714b'
# The post ID for the Hall of banned users post. Must be created manually as a post on the bot account
HOF_SUBMISSION_ID = ''

reddit = praw.Reddit(client_id=os.environ['REDDIT_CLIENT_ID'],
                     client_secret=os.environ['REDDIT_CLIENT_SECRET'],
                     password=os.environ['REDDIT_PASSWORD'],
                     user_agent=USER_AGENT,
                     username=os.environ['REDDIT_USERNAME'])
print('Logged in.')

subreddit = reddit.subreddit(SUBREDDIT)

old_announcement = ''

while True:
    if time.strftime('%H:%M:%S') == RUN_TIME:
        # Get all top posts for the day
        posts_today = list(subreddit.top(time_filter='day'))
        # Sort them by score
        # Currently, they're sorted by score - the sum of upvotes and downvotes.
        # However, it's probably possible to get exactly how many upvotes and downvotes they had.
        posts_today.sort(key=lambda submission: submission.score, reverse=True)
        top_post = posts_today[0]
        bottom_post = posts_today[-1]

        date = time.strftime('%d/%m/%Y')

        # Ban the top poster for today
        ban_reason_top = f"Most upvoted post of the day {date}"
        subreddit.banned.add(top_post.author.name, ban_reason=ban_reason_top)

        # Ban the bottom poster for today
        ban_reason_bottom = f"Least upvoted post of the day {date}"
        subreddit.banned.add(bottom_post.author.name, ban_reason=ban_reason_bottom)

        # Make a new announcement post
        announcement_post_title = f"Today's ({date}) winner and loser!"
        announcement_post_body = f"""u/{top_post.author.name} is our unfortunate [winner]({top_post.permalink})!    
u/{bottom_post.author.name} is our equally as unfortunate [loser]({bottom_post.permalink})!    
Keep the posts coming fellas, you could be added to our hall of winners and losers if you’re (un)lucky enough!"""
        new_announcement = subreddit.submit(title=announcement_post_title,
                                            selftext=announcement_post_body,
                                            flair_id=ANNOUNCEMENT_FLAIR_ID)
        # Sticky today's post and unsticky yesterday's
        new_announcement.mod.distinguish(sticky=True)
        if old_announcement:
            old_announcement.mod.distinguish(sticky=False)
        old_announcement = new_announcement

        # Edit the hall of fame post
        hof_post = reddit.submission(HOF_SUBMISSION_ID)
        hof_body_current = hof_post.selftext

        hof_body_addition = f"""    
u/{top_post.author.name} : [post]({top_post.permalink})    
u/{bottom_post.author.name} : [post]({bottom_post.permalink})"""
        hof_body_new = hof_body_current + hof_body_addition

        hof_post.edit(hof_body_new)

        # Ensure no double dipping
        time.sleep(2)

    time.sleep(0.5)
