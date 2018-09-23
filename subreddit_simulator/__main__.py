import logging
import os
import time
from datetime import datetime

from subreddit_simulator import Simulator
from subreddit_simulator.database import CONFIG, db

db_config = CONFIG.from_db(db)
db_config.merge(CONFIG, exclude=["last_comment", "last_submission", "last_update", "last_vote"])
db_config.update_db(db)
CONFIG = db_config

if os.environ.get("SUBREDDIT_SIMULATOR_PRAWCORE_LOGGING", False):
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    logger = logging.getLogger("prawcore")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

print(repr(CONFIG))

s = Simulator()
s.print_accounts_table()

print("\nStarting main loop on {}".format(datetime.now().isoformat()))

while True:
    now = time.time()

    if now - CONFIG.last_update >= CONFIG.leaderboard_update_delay_seconds:
        print("\nTrying to update the leaderboard on r/{}...".format(s.subreddit))
        if s.update_leaderboard():
            CONFIG.last_update = time.time()
            print("Leaderboard updated on {}".format(datetime.now().isoformat()))

    if now - CONFIG.last_comment >= CONFIG.comment_delay_seconds:
        print("\nTrying to make a comment on r/{}...".format(s.subreddit))
        if s.make_comment():
            CONFIG.last_comment = time.time()
            print("Comment posted on {}".format(datetime.now().isoformat()))

    if now - CONFIG.last_submission >= CONFIG.submission_delay_seconds:
        print("\nTrying to make a submission on r/{}...".format(s.subreddit))
        if s.make_submission():
            CONFIG.last_submission = time.time()
            print("Submission posted on {}".format(datetime.now().isoformat()))

    if now - CONFIG.last_vote >= CONFIG.voting_delay_seconds:
        print("\nTrying to vote on a submission / comment in r/{}...".format(s.subreddit))
        if s.make_vote():
            CONFIG.last_vote = time.time()
            print("Voted on {}".format(datetime.now().isoformat()))

    CONFIG.update_db(db)
    time.sleep(CONFIG.main_loop_delay_seconds)

print("Stopped main loop on {}".format(datetime.now().isoformat()))
