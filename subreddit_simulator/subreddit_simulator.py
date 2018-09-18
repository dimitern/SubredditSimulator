import html.parser
import random
import re
from datetime import datetime, timedelta

import praw
import pytz

from .database import db
from .models import Account, Settings


class Simulator(object):
    def __init__(self):
        self.accounts = {}
        self.subreddit = Settings["subreddit"].lower()

        if self.subreddit.startswith("r/"):
            self.subreddit = self.subreddit[2:]

        for account in db.query(Account):
            subreddit = account.subreddit
            if account.name == Settings["moderator"]:
                subreddit = self.subreddit
            self.accounts[subreddit] = account

        self.mod_account = self.accounts[self.subreddit]

    def pick_account_to_comment(self):
        accounts = [a for a in list(self.accounts.values()) if a.can_comment]

        # if any account hasn't commented yet, pick that one
        try:
            return next(a for a in accounts if not a.last_commented)
        except StopIteration:
            pass

        # pick an account from the 25% that commented longest ago
        kept_accounts = sorted(accounts, key=lambda a: a.last_commented)
        num_to_keep = int(len(kept_accounts) * 0.25)
        if num_to_keep:
            return random.choice(kept_accounts[:num_to_keep])
        return random.choice(accounts)

    def pick_account_to_submit(self):
        accounts = [a for a in list(self.accounts.values()) if a.is_able_to_submit]

        # if any account hasn't submitted yet, pick that one
        try:
            return next(a for a in accounts if not a.last_submitted)
        except StopIteration:
            pass

        # pick an account from the 25% that submitted longest ago
        kept_accounts = sorted(accounts, key=lambda a: a.last_submitted)
        num_to_keep = int(len(kept_accounts) * 0.25)
        if num_to_keep:
            return random.choice(kept_accounts[:num_to_keep])

        return random.choice(accounts)

    def make_comment(self):
        account = self.pick_account_to_comment()
        if not account:
            return False
        account.train_from_comments()

        # get the newest submission in the subreddit
        subreddit = account.session.subreddit(self.subreddit)
        for submission in subreddit.new(limit=5):
            if submission.locked or submission.author.name == Settings["owner"]:
                continue

            return account.post_comment_on(submission)

        return False

    def make_submission(self):
        account = self.pick_account_to_submit()
        if not account:
            return False
        account.train_from_submissions()
        return account.post_submission(self.subreddit)

    def update_leaderboard(self, limit=100):
        session = self.mod_account.session
        subreddit = session.subreddit(self.subreddit)

        accounts = sorted(
            [a for a in list(self.accounts.values()) if a.can_comment],
            key=lambda a: a.mean_comment_karma,
            reverse=True,
        )

        leaderboard_md = "\\#|Account|Avg Karma\n--:|:--|--:"
        for rank, account in enumerate(accounts, start=1):
            leaderboard_md += "\n{}|/u/{}|{:.2f}".format(
                rank, account.name, account.mean_comment_karma
            )
            if rank >= limit:
                break

        start_delim = "[](/leaderboard-start)"
        end_delim = "[](/leaderboard-end)"
        try:
            current_sidebar = subreddit.mod.settings()["description"]
        except praw.exceptions.PRAWException as err:
            print(f"UPDATE ERROR: {err!s}")
            return False

        current_sidebar = html.parser.HTMLParser().unescape(current_sidebar)
        replace_pattern = re.compile(
            "{}.*?{}".format(re.escape(start_delim), re.escape(end_delim)),
            re.IGNORECASE | re.DOTALL | re.UNICODE,
        )
        new_sidebar = re.sub(
            replace_pattern,
            "{}\n\n{}\n\n{}".format(start_delim, leaderboard_md, end_delim),
            current_sidebar,
        )
        subreddit.mod.update(description=new_sidebar)

        flair_map = [
            {
                "user": account.name,
                "flair_text": "#{} / {} ({:.2f})".format(
                    rank, len(accounts), account.mean_comment_karma
                ),
            }
            for rank, account in enumerate(accounts, start=1)
        ]

        try:
            subreddit.flair.update(flair_map)
        except praw.exceptions.PRAWException as err:
            print(f"UPDATE ERROR: {err!s}")
            return False

        return True

    def print_accounts_table(self):
        accounts = sorted(list(self.accounts.values()), key=lambda a: a.added)

        print("\nSubreddit|Added|Posts Comments?|Posts Submissions?")
        print(":--|--:|:--|:--")

        checkmark = html.unescape("&#10003;")
        for account in accounts:
            print(
                "[{}]({})|{}|{}|{}".format(
                    account.subreddit,
                    "/u/" + account.name,
                    account.added.strftime("%Y-%m-%d"),
                    checkmark if account.can_comment else "",
                    checkmark if account.can_submit else "",
                )
            )
