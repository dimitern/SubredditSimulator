import html.parser
import random
import re
from datetime import datetime, timedelta

import praw
import pytz

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
        accounts = []
        min_interval = timedelta(seconds=600)

        for account in self.accounts.values():
            if not account.can_comment:
                echo(
                    "${FG_YELLOW}Skipping account $BOLD${name}$NORMAL: "
                    "cannot comment",
                    file=self.output,
                    name=account.name,
                    max_length=-1,
                )
                continue

            if account.last_commented:
                ago = now - account.last_commented
                if ago < min_interval:
                    echo(
                        "${FG_YELLOW}Skipping account $BOLD${name}$NORMAL: "
                        "last commented ${time} (less than ${min} ago - $BOLD${ago})",
                        file=self.output,
                        name=account.name,
                        time=account.last_commented.isoformat(),
                        ago=ago,
                        min=min_interval,
                        max_length=-1,
                    )
                    continue
                else:
                    echo(
                        "${FG_YELLOW}Choosing account $BOLD${name}$NORMAL: "
                        "last commented ${time} (more than ${min} ago - $BOLD${ago})",
                        file=self.output,
                        name=account.name,
                        time=account.last_commented.isoformat(),
                        ago=ago,
                        min=min_interval,
                        max_length=-1,
                    )
            else:
                echo(
                    "${FG_YELLOW}Choosing account $BOLD${name}$NORMAL: "
                    "never commented before",
                    file=self.output,
                    name=account.name,
                    max_length=-1,
                )

            accounts += [account]

        # if any account hasn't commented yet, pick that one
        try:
            account = next(a for a in accounts if not a.last_commented)
            echo(
                "${FG_GREEN}Picked account $BOLD${name}$NORMAL: "
                "never commented before.",
                file=self.output,
                name=account.name,
                max_length=-1,
            )
            return account

        except StopIteration:
            pass

        # pick an account from the 25% that commented longest ago
        kept_accounts = sorted(accounts, key=lambda a: a.last_commented)
        num_to_keep = int(len(kept_accounts) * 0.25)

        echo(
            "$FG_WHITE${DIM}Keeping 25% ($num) of all least "
            "recently commented accounts ($all)",
            file=self.output,
            num=num_to_keep,
            all=len(kept_accounts),
        )

        if num_to_keep:
            account = random.choice(kept_accounts[:num_to_keep])
            ago = now - account.last_commented
            echo(
                "${FG_GREEN}Picked random account $BOLD${name}$NORMAL: "
                "among the 25% least recently commented (at ${time} - $BOLD${ago} ago)",
                file=self.output,
                name=account.name,
                time=account.last_commented.isoformat(),
                ago=ago,
                max_length=-1,
            )
            return account

        account = random.choice(accounts) if accounts else None
        if account:
            ago = now - account.last_commented
            echo(
                "${FG_GREEN}Picked random account $BOLD${name}$NORMAL: "
                "among all least recently commented (at ${time} - $BOLD${ago} ago)",
                file=self.output,
                name=account.name,
                time=account.last_commented.isoformat(),
                ago=ago,
                max_length=-1,
            )
        return account

    def pick_account_to_submit(self):
        now = datetime.now(pytz.utc)
        accounts = []

        for account in self.accounts.values():
            if not account.is_able_to_submit:
                echo(
                    "${FG_YELLOW}Skipping account $BOLD${name}$NORMAL: "
                    "cannot submit",
                    file=self.output,
                    name=account.name,
                    max_length=-1,
                )
                continue

            echo(
                "${FG_YELLOW}Choosing account $BOLD${name}$NORMAL: can submit",
                file=self.output,
                name=account.name,
                max_length=-1,
            )

            accounts += [account]

        # if any account hasn't submitted yet, pick that one
        try:
            account = next(a for a in accounts if not a.last_submitted)
            echo(
                "${FG_GREEN}Picked account $BOLD${name}$NORMAL: "
                "never submitted before.",
                file=self.output,
                name=account.name,
                max_length=-1,
            )
            return account

        except StopIteration:
            pass

        # pick an account from the 25% that submitted longest ago
        kept_accounts = sorted(accounts, key=lambda a: a.last_submitted)
        num_to_keep = int(len(kept_accounts) * 0.25)

        echo(
            "$FG_WHITE${DIM}Keeping 25% ($num) of all accounts least "
            "recently made a submission ($all)",
            file=self.output,
            num=num_to_keep,
            all=len(kept_accounts),
        )

        if num_to_keep:
            account = random.choice(kept_accounts[:num_to_keep])
            ago = now - account.last_submitted
            echo(
                "${FG_GREEN}Picked random account $BOLD${name}$NORMAL: "
                "among the 25% of those least recently made a submission "
                "(at ${time} - $BOLD${ago} ago)",
                file=self.output,
                name=account.name,
                time=account.last_submitted.isoformat(),
                ago=ago,
                max_length=-1,
            )
            return account

        account = random.choice(accounts) if accounts else None
        if account:
            ago = now - account.last_commented
            echo(
                "${FG_GREEN}Picked random account $BOLD${name}$NORMAL: "
                "among all of those least recently made a submission "
                "(at ${time} - $BOLD${ago} ago)",
                file=self.output,
                name=account.name,
                time=account.last_submitted.isoformat(),
                ago=ago,
                max_length=-1,
            )
        return account

    def pick_account_to_vote(self):
        accounts = []
        min_karma = 2

        for account in self.accounts.values():
            if not account.can_comment:
                echo(
                    "${FG_YELLOW}Skipping account $BOLD${name}$NORMAL: "
                    "cannot comment",
                    file=self.output,
                    name=account.name,
                    max_length=-1,
                )
                continue

            if not account.can_submit:
                echo(
                    "${FG_YELLOW}Skipping account $BOLD${name}$NORMAL: "
                    "cannot submit",
                    file=self.output,
                    name=account.name,
                    max_length=-1,
                )
                continue

            if account.comment_karma + account.link_karma <= min_karma:
                echo(
                    "${FG_YELLOW}Skipping account $BOLD${name}$NORMAL: "
                    "total comment karma ($ck) and link karma ($lk) less than $min",
                    file=self.output,
                    name=account.name,
                    ck=account.comment_karma,
                    lk=account.comment_karma,
                    min=min_karma,
                    max_length=-1,
                )
                continue

            echo(
                "${FG_GREEN}Picked account $BOLD${name}$NORMAL: total karma $k",
                file=self.output,
                name=account.name,
                k=account.comment_karma + account.link_karma,
                max_length=-1,
            )
            accounts += [account]

        random.shuffle(accounts)

        try:
            account = next(a for a in accounts)
            echo(
                "${FG_GREEN}Picked account $BOLD${name}$NORMAL: "
                "has total comment karma ($ck) and link karma ($lk) over $min",
                file=self.output,
                name=account.name,
                ck=account.comment_karma,
                lk=account.link_karma,
                min=min_karma,
                max_length=-1,
            )
            return account

        except StopIteration:
            echo(
                "${FG_RED}No account has total comment and link karma over $min",
                file=self.output,
                min=min_karma,
                max_length=-1,
            )
            return None

    def can_comment_on(self, submission):
        result = True
        reason = ""
        min_comments, max_comments = random.randint(0, 3), random.randint(10, 30)
        min_score, max_score = 1, 30
        min_ratio = 1.0

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

        for submission in submissions:
            if self.can_comment_on(submission):
                return account.post_comment_on(submission), account.name
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
                if self.can_comment_on(submission):
                    return account.post_comment_on(submission), account.name

        return False, f"Cannot pick submission to comment on with {account.name}!"

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
