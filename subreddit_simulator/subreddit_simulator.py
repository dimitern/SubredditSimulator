import html.parser
import random
import re
from datetime import datetime, timedelta

import pytz

import praw

from .models import Account
from .utils import echo


class Simulator:
    def __init__(self, config=None, engine=None, output=None):
        self.config = config
        self.engine = engine
        self.db = self.engine.create_session()
        self.accounts = {}
        self.subreddit = self.config.subreddit
        self.output = output

        for account in self.db.query(Account):
            subreddit = account.subreddit
            if account.name == self.config.moderator:
                subreddit = self.subreddit

            account.output = self.output
            account.config = self.config
            account.engine = self.engine
            account.db = self.db

            self.accounts[subreddit] = account

        self.mod_account = self.accounts[self.subreddit]

    def pick_account_to_comment(self):
        now = datetime.now(pytz.utc)
        accounts = [
            a
            for a in list(self.accounts.values())
            if a.can_comment
            and (
                not a.last_commented
                or (now - a.last_commented > timedelta(seconds=600))
            )
        ]

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

    def pick_account_to_vote(self):
        accounts = [
            a for a in list(self.accounts.values()) if a.can_comment or a.can_submit
        ]
        random.shuffle(accounts)

        try:
            return next(a for a in accounts if (a.comment_karma + a.link_karma) > 2)
        except StopIteration:
            return None

    def can_comment_on(self, submission):
        return (
            not submission.locked
            and not submission.author.name == self.config.owner
            and 2 <= submission.num_comments <= random.randint(5, 25)
        )

    def make_comment(self):
        account = self.pick_account_to_comment()
        if not account:
            return False

        if not account.train_from_comments():
            return False

        subreddit = account.session.subreddit(self.subreddit)
        submissions = subreddit.new(limit=25)

        for submission in submissions:
            if self.can_comment_on(submission):
                return account.post_comment_on(submission)
        else:
            submissions = subreddit.top("all", limit=50)
            for submission in submissions:
                if self.can_comment_on(submission):
                    return account.post_comment_on(submission)

        return False

    def make_submission(self):
        account = self.pick_account_to_submit()
        if not account:
            return False

        if not account.train_from_submissions():
            return False

        return account.post_submission(self.subreddit)

    def make_vote(self):
        account = self.pick_account_to_vote()
        if not account:
            return False

        max_candidates = 15

        subreddit = account.session.subreddit(self.subreddit)
        submissions = subreddit.hot(limit=25)

        candidates = []
        for submission in submissions:
            if len(candidates) >= max_candidates // 2:
                break

            if not submission.locked:
                candidates.append(submission.fullname)

        else:
            submissions = subreddit.new(limit=50)
            for submission in submissions:
                if len(candidates) >= max_candidates // 2:
                    break

                if not submission.locked:
                    candidates.append(submission.fullname)

        for comment in subreddit.comments(limit=25):
            if len(candidates) >= max_candidates:
                break

            candidates.append(comment.fullname)

        random.shuffle(candidates)

        for candidate in account.session.info(candidates):
            try:
                direction = 1
                echo(
                    f"Voting $BOLD {direction} $NORMAL on $FG_CYAN "
                    f"{candidate.fullname!r} $FG_RESET with "
                    f"$FG_MAGENTA {account.name!r} $FG_RESET...",
                    file=self.output,
                    max_length=-1,
                )

                candidate.upvote() if direction == 1 else candidate.downvote()

            except praw.exceptions.PRAWException as err:
                echo(
                    "$BG_RED$FG_YELLOW${BOLD}UPDATE ERROR:${NORMAL} ${err}",
                    err=str(err),
                    file=self.output,
                    max_length=-1,
                )
                return False

        return True

    def update_leaderboard(self, limit=100):
        session = self.mod_account.session
        subreddit = session.subreddit(self.subreddit)

        accounts = sorted(
            [a for a in list(self.accounts.values()) if a.can_comment],
            key=lambda a: a.mean_comment_karma,
            reverse=True,
        )

        leaderboard_md = (
            "\\#|Account|Avg Karma|\\#Com|\\#Sub|SR\n--:|:--|--:|--:|--:|:--"
        )
        for rank, account in enumerate(accounts, start=1):
            leaderboard_md += "\n{}|/u/{}|{:.2f}|{}|{}|/r/{}".format(
                rank,
                account.name,
                account.mean_comment_karma,
                account.num_comments,
                account.num_submissions,
                account.subreddit,
            )
            if rank >= limit:
                break

        start_delim = "[](/leaderboard-start)"
        end_delim = "[](/leaderboard-end)"
        try:
            current_sidebar = subreddit.mod.settings()["description"]
        except praw.exceptions.PRAWException as err:
            echo(
                "$BG_RED$FG_YELLOW${BOLD}UPDATE ERROR:${NORMAL} ${err}",
                err=str(err),
                file=self.output,
                max_length=-1,
            )
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
            echo(
                "$BG_RED$FG_YELLOW${BOLD}UPDATE ERROR:${NORMAL} ${err}",
                err=str(err),
                file=self.output,
                max_length=-1,
            )
            return False

        return True

    def print_accounts_table(self):
        accounts = sorted(list(self.accounts.values()), key=lambda a: a.added)

        columns = (
            "Subreddit",
            "Account",
            "Added",
            "C. Karma",
            "L. Karma",
            "#Comments",
            "#Submissions",
            "Can Comment?",
            "Can Submit?",
        )
        formatting = "|{:<20}|{:<20}|{:<10}|{:>11}|{:>11}|{:>13}|{:>13}|{:^13}|{:^13}|"
        header = f"{formatting.replace('<', '^').replace('>', '^')}".format(*columns)
        separator = "-" * len(header)

        print("", separator, header, separator, sep="\n", file=self.output)

        checkmark = html.unescape("&#10003;")
        for account in accounts:
            print(
                formatting.format(
                    "/r/" + account.subreddit,
                    "/u/" + account.name,
                    account.added.strftime("%Y-%m-%d"),
                    f"{account.comment_karma:.2f}",
                    f"{account.link_karma:.2f}",
                    account.num_comments,
                    account.num_submissions,
                    checkmark if account.can_comment else "",
                    checkmark if account.can_submit else "",
                ),
                file=self.output,
            )

        print(separator, file=self.output)
