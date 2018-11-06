import html.parser
import random
import re
from datetime import datetime, timedelta
from logging import getLogger
from operator import attrgetter

import praw
import pytz

from .models import Account
from .utils import echo

logger = getLogger(__name__)


class Simulator:
    def __init__(self, config=None, engine=None, output=None):
        logger.debug("Using %r", config)
        logger.debug("Using %r", engine)

        self.config = config
        self.engine = engine
        self.db = self.engine.create_session()
        self.accounts = {}
        self.subreddit = self.config.subreddit
        self.output = output
        logger.info("Configured subreddit:  %r", self.subreddit)

        logger.debug("Loading accounts from the database...")
        for account in self.db.query(Account):
            account.name = account.name.lower()
            logger.info("Account %r uses subreddit %r", account.name, account.subreddit)

            subreddit = account.subreddit
            if account.name == self.config.moderator.lower():
                subreddit = self.subreddit
                logger.info(
                    "Subreddit %s moderator account is %r", subreddit, account.name
                )

            account.output = self.output
            account.config = self.config
            account.engine = self.engine
            account.db = self.db

            logger.debug("Establishing Reddit session for %r", account.name)
            account.session  # force a login to ensure account is up-to-date

            self.accounts[subreddit] = account

        self.mod_account = self.accounts[self.subreddit]
        logger.info("%d accounts loaded and initialized", len(self.accounts))

    def timedelta_since_last_comment(self, account):
        logger.debug("Checking time since account %r last commented...", account.name)
        min_interval = timedelta(seconds=self.config.min_seconds_since_last_comment)

        if not account.can_comment:
            logger.debug("Account %r not allowed to comment", account.name)
            return timedelta(seconds=0)

        if not account.last_commented:
            logger.debug("Account %r never commented before", account.name)
            return min_interval

        ago = datetime.now(pytz.utc) - account.last_commented
        logger.debug("Account %r's last comment was %s ago", account.name, ago)
        return ago

    def pick_account_to_comment(self):
        logger.debug("Picking account to comment...")

        min_interval = timedelta(seconds=self.config.min_seconds_since_last_comment)
        logger.debug("Minimum time required since last comment: %s", min_interval)

        accounts = list(
            filter(
                attrgetter("can_comment"),
                sorted(
                    self.accounts.values(),
                    key=self.timedelta_since_last_comment,
                    reverse=True,
                ),
            )
        )

        # If any account hasn't commented yet, pick that one.
        try:
            account = next(a for a in accounts if not a.last_commented)
            logger.info(
                "Picked account %r to comment: never commented before", account.name
            )
            return account

        except StopIteration:
            pass

        # Pick an account from the 25% that commented longest ago.
        num_accounts = len(accounts)
        num_to_keep = int(num_accounts * 0.25) or num_accounts

        logger.debug(
            "Keeping %d of %d least recently commented accounts",
            num_to_keep,
            num_accounts,
        )

        account = random.choice(accounts[:num_to_keep]) if accounts else None
        if not account:
            logger.error("Cannot pick account to comment: no suitable accounts")

        else:
            logger.info("Picked account %r to comment", account.name)

        return account

    def timedelta_since_last_submission(self, account):
        logger.debug("Checking time since account %r last submitted...", account.name)
        min_interval = timedelta(seconds=self.config.min_seconds_since_last_submission)

        if not account.can_submit:
            logger.debug("Account %r not allowed to submit", account.name)
            return timedelta(seconds=0)

        if not account.last_submitted:
            logger.debug("Account %r never submitted before", account.name)
            return min_interval

        ago = datetime.now(pytz.utc) - account.last_submitted
        logger.debug("Account %r's last submission was %s ago", account.name, ago)
        return ago

    def pick_account_to_submit(self):
        logger.debug("Picking account to make a submission...")

        min_interval = timedelta(seconds=self.config.min_seconds_since_last_submission)
        logger.debug("Minimum time required since last submission: %s", min_interval)

        accounts = list(
            filter(
                attrgetter("can_submit"),
                sorted(
                    self.accounts.values(),
                    key=self.timedelta_since_last_submission,
                    reverse=True,
                ),
            )
        )

        # If any account hasn't posted as submission yet, pick that one.
        try:
            account = next(a for a in accounts if not a.last_submitted)
            logger.info(
                "Picked account %r to submit: never made a submission before",
                account.name,
            )
            return account

        except StopIteration:
            pass

        # Pick an account from the 25% that submitted longest ago.
        num_accounts = len(accounts)
        num_to_keep = int(num_accounts * 0.25) or num_accounts

        logger.debug(
            "Keeping %d of %d accounts that least recently made a submission",
            num_to_keep,
            num_accounts,
        )

        account = random.choice(accounts[:num_to_keep]) if accounts else None
        if not account:
            logger.error(
                "Cannot pick account to make a submission: no suitable accounts"
            )

        else:
            logger.info("Picked account %r to make a submission", account.name)

        return account

    def timedelta_since_last_vote(self, account):
        logger.debug("Checking time since account %r last voted...", account.name)
        min_interval = timedelta(seconds=self.config.min_seconds_since_last_vote)
        min_karma = self.config.min_karma_to_vote

        if not account.can_comment:
            logger.debug("Account %r not allowed to comment", account.name)
            return timedelta(seconds=0)

        if not account.can_submit:
            logger.debug("Account %r not allowed to submit", account.name)
            return timedelta(seconds=0)

        total_karma = account.link_karma + account.comment_karma
        if total_karma < min_karma:
            logger.debug("Account %r has total karma %d", account.name, total_karma)
            return timedelta(seconds=0)

        if not account.last_voted:
            logger.debug("Account %r never voted before", account.name)
            return min_interval

        ago = datetime.now(pytz.utc) - account.last_voted
        logger.debug("Account %r's last vote was %s ago", account.name, ago)
        return ago

    def pick_account_to_vote(self):
        logger.debug("Picking account to vote...")

        min_interval = timedelta(seconds=self.config.min_seconds_since_last_vote)
        logger.debug("Minimum time required since last vote: %s", min_interval)
        min_karma = self.config.min_karma_to_vote
        logger.debug("Minimum total karma required to vote: %d", min_karma)

        accounts = list(
            filter(
                attrgetter("can_vote"),
                sorted(
                    self.accounts.values(),
                    key=self.timedelta_since_last_vote,
                    reverse=True,
                ),
            )
        )

        # If any account hasn't voted yet, pick that one.
        try:
            account = next(a for a in accounts if not a.last_voted)
            logger.info("Picked account %r to vote: never voted before", account.name)
            return account

        except StopIteration:
            pass

        # Pick an account from the 25% that voted longest ago.
        num_accounts = len(accounts)
        num_to_keep = int(num_accounts * 0.25) or num_accounts

        logger.debug(
            "Keeping %d of %d accounts that least recently voted",
            num_to_keep,
            num_accounts,
        )

        account = random.choice(accounts[:num_to_keep]) if accounts else None
        if not account:
            logger.error("Cannot pick account to vote: no suitable accounts")

        else:
            logger.info("Picked account %r to vote", account.name)

        return account

    def can_comment_on(self, submission):
        result = True
        reason = ""
        min_comments, max_comments = random.randint(0, 3), random.randint(10, 30)
        min_score, max_score = 1, 30
        min_ratio = 0.5

        if submission.locked:
            reason = "submission is locked"
            result = False

        if result and submission.upvote_ratio < min_ratio:
            reason = "submission upvote ratio ({}) is less than the minimum {}".format(
                submission.upvote_ratio, min_ratio
            )
            result = False

        if result and submission.score < min_score:
            reason = "submission score ({}) is less than the minimum {}".format(
                submission.score, min_score
            )
            result = False

        if result and submission.score > max_score:
            reason = "submission score ({}) is more than the maximum {}".format(
                submission.score, max_score
            )
            result = False

        if result and submission.author.name == self.config.owner:
            reason = "submission author ({}) is the target subreddit owner".format(
                submission.author.name
            )
            result = False

        if result and submission.author.name in self.config.ignored_users:
            reason = "submission author ({}) is in the ignored users".format(
                submission.author.name
            )
            result = False

        if result and submission.num_comments < min_comments:
            reason = "submission has fewer comments ({}) than the minimum {}".format(
                submission.num_comments, min_comments
            )
            result = False

        if result and submission.num_comments > max_comments:
            reason = "submission has more comments ({}) than current the maximum {}".format(
                submission.num_comments, max_comments
            )
            result = False

        if not result:
            echo(
                "${FG_YELLOW}${DIM}Cannot comment on $BOLD$sub$NORMAL: \n  $reason",
                file=self.output,
                sub=self.config.reddit_url + submission.permalink,
                reason=reason,
                max_length=-1,
            )
        else:
            echo(
                "${FG_GREEN}${DIM}Commenting on $BOLD$sub$NORMAL: \n  "
                + ";\n  ".join(
                    [
                        "not locked",
                        "with upvote ratio $BOLD$uvr$NORMAL (over the limit $uvrl)",
                        "score $BOLD$score$NORMAL (within the limits [$mns,$mxs])",
                        "has $BOLD${nc}$NORMAL comment(s) (within the limits [$mnc,$mxc])",
                        "author $BOLD${author}$NORMAL is not in ignored_users or the owner",
                    ]
                ),
                file=self.output,
                sub=self.config.reddit_url + submission.permalink,
                nc=submission.num_comments,
                mns=min_score,
                mxs=max_score,
                mnc=min_comments,
                mxc=max_comments,
                author=submission.author.name,
                score=submission.score,
                uvr=submission.upvote_ratio,
                uvrl=min_ratio,
                max_length=-1,
            )

        return result

    def make_comment(self):
        account = self.pick_account_to_comment()
        if not account:
            return False, "Cannot pick account to comment!"

        if not account.train_from_comments():
            return False, f"Cannot train account {account.name} from comments!"

        limit = 100
        echo(
            "$FG_WHITE${DIM}Getting $BOLD$limit$NORMAL$DIM new submissions "
            "in $BOLD$sub$NORMAL$DIM to comment on",
            file=self.output,
            limit=limit,
            sub=self.subreddit,
            max_length=-1,
        )

        subreddit = account.session.subreddit(self.subreddit)
        submissions = subreddit.new(limit=limit)

        candidates = []
        for submission in submissions:
            candidates += [submission]

        else:
            echo(
                "$FG_YELLOW${DIM}Getting $BOLD$limit$NORMAL$DIM top submissions "
                "in $BOLD$sub$NORMAL$DIM of all time to comment on",
                file=self.output,
                limit=limit,
                sub=self.subreddit,
                max_length=-1,
            )

            submissions = subreddit.top("all", limit=limit)
            for submission in submissions:
                candidates += [submission]

        if not candidates:
            return False, "Cannot find a suitable submission to comment on!"

        for submission in sorted(
            candidates,
            key=lambda s: (s.score or 1) / (s.num_comments or 1),
            reverse=True,
        ):
            if self.can_comment_on(submission):
                return account.post_comment_on(submission), account.name

        return False, f"Cannot post submission to comment on with {account.name}!"

    def make_submission(self):
        account = self.pick_account_to_submit()
        if not account:
            return False, "Cannot pick account to submit!"

        if not account.train_from_submissions():
            return False, f"Cannot train account {account.name} from submissions!"

        return account.post_submission(self.subreddit), account.name

    def make_vote(self):
        account = self.pick_account_to_vote()
        if not account:
            return False, "Cannot pick account to vote!"

        max_candidates = 15

        subreddit = account.session.subreddit(self.subreddit)
        submissions = subreddit.hot(limit=25)

        fullname_to_permalink = {}

        candidates = []
        for submission in submissions:
            if len(candidates) >= max_candidates // 2:
                break

            if not submission.locked:
                fullname_to_permalink[submission.fullname] = submission.permalink
                candidates.append(submission.fullname)

        else:
            submissions = subreddit.new(limit=50)
            for submission in submissions:
                if len(candidates) >= max_candidates // 2:
                    break

                if not submission.locked:
                    fullname_to_permalink[submission.fullname] = submission.permalink
                    candidates.append(submission.fullname)

        for comment in subreddit.comments(limit=25):
            if len(candidates) >= max_candidates:
                break

            fullname_to_permalink[comment.fullname] = (
                comment.submission.permalink + comment.id
            )
            candidates.append(comment.fullname)

        random.shuffle(candidates)

        for candidate in account.session.info(candidates):
            try:
                echo(
                    "Voting ${BOLD}+1${NORMAL} on $FG_CYAN "
                    f"$url$FG_RESET with $FG_MAGENTA{account.name!r} $FG_RESET...",
                    file=self.output,
                    url=self.config.reddit_url
                    + fullname_to_permalink.get(candidate.fullname, candidate.fullname),
                    max_length=-1,
                )
                candidate.upvote()

            except praw.exceptions.PRAWException as err:
                echo(
                    "$BG_RED$FG_YELLOW${BOLD}UPDATE ERROR:${NORMAL} ${err}",
                    err=str(err),
                    file=self.output,
                    max_length=-1,
                )
                return False, str(err)

        return True, account.name

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
            return False, None

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
            return False, None

        return True, self.mod_account.name

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
