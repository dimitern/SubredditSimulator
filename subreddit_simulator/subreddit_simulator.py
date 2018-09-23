import html.parser
import random
import re

import praw
from subreddit_simulator.models import CONFIG, Account, db


class Simulator(object):
    def __init__(self):
        self.accounts = {}
        self.subreddit = CONFIG.subreddit

        for account in db.query(Account):
            subreddit = account.subreddit
            if account.name == CONFIG.moderator:
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
        num_to_keep = int(len(kept_accounts) * 0.5)
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
        num_to_keep = int(len(kept_accounts) * 0.5)
        if num_to_keep:
            return random.choice(kept_accounts[:num_to_keep])

        return random.choice(accounts)

    def pick_account_to_vote(self):
        accounts = [
            a for a in list(self.accounts.values()) if a.can_comment or a.can_submit
        ]
        random.shuffle(accounts)

        # if any account hasn't commented yet, pick that one
        try:
            return next(
                a for a in accounts if (a.mean_comment_karma + a.mean_link_karma) > 0
            )
        except StopIteration:
            return None

    def can_comment_on(self, submission):
        return not submission.locked and not submission.author.name == CONFIG.owner

    def make_comment(self):
        account = self.pick_account_to_comment()
        if not account:
            return False

        if not account.train_from_comments():
            return False

        subreddit = account.session.subreddit(self.subreddit)
        submissions = subreddit.top("day", limit=25)

        for submission in submissions:
            if self.can_comment_on(submission):
                return account.post_comment_on(submission)
        else:
            submissions = subreddit.top("all", limit=25)
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

        max_candidates = 10

        subreddit = account.session.subreddit(self.subreddit)
        submissions = subreddit.top("day", limit=25)

        candidates = []
        for submission in submissions:
            if len(candidates) >= max_candidates // 2:
                break

            if not submission.locked:
                candidates.append(submission.fullname)

        else:
            submissions = subreddit.hot(limit=25)
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
                direction = 1 if random.random() < 0.9 else -1
                print(
                    f"Voting {direction} on {candidate.fullname!r} with {account.name!r}..."
                )

                candidate.upvote() if direction == 1 else candidate.downvote()

            except praw.exceptions.PRAWException as err:
                print(f"UPDATE ERROR: {err!s}")
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
