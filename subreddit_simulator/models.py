import html
import random
import sys
from datetime import datetime
from logging import getLogger

import markovify
import praw
import prawcore
import pytz
import requests
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

from .database import JSONSerialized
from .utils import echo

MAX_OVERLAP_RATIO = 0.7
MAX_OVERLAP_TOTAL = 20


Base = declarative_base()

logger = getLogger(__name__)


class SubredditSimulatorText(markovify.Text):
    def __init__(self, input_text, state_size=2, **kwargs):
        input_text = html.unescape(input_text)
        try:
            super().__init__(input_text, state_size=state_size, **kwargs)
        except KeyError as err:
            if markovify.text.BEGIN in str(err):
                raise ValueError(f"Ignoring bad input_text: {input_text!r}") from err

    def test_sentence_output(self, *args, **kwargs):
        r = super().test_sentence_output(*args, **kwargs)
        return r if random.random() > 0.5 else random.choice((True, False))

    @staticmethod
    def prepare_sentance(sentence):
        if not sentence or not sentence.strip():
            return ""

        sentence = " ".join(map(str.strip, sentence.strip().splitlines()))

        if not sentence.endswith((".", "!", "?", ":", ";", "-", ",")):
            sentence += random.choice((".", "!", "?"))

        if sentence[0].upper() != sentence[0]:
            sentence = sentence[0].upper() + sentence[1:]

        return sentence

    def sentence_join(self, sentences):
        return " ".join(map(self.prepare_sentance, sentences))

    def sentence_split(self, text):
        text = " ".join(map(self.prepare_sentance, text.strip().splitlines()))
        return markovify.split_into_sentences(text)


class Setting(Base):  # type: ignore
    __tablename__ = "settings"

    name = Column(String(100), primary_key=True)
    value = Column(JSONSerialized)


class Account(Base):  # type: ignore
    __tablename__ = "accounts"

    name = Column(String(20), primary_key=True)
    password = Column(String(50))
    subreddit = Column(String(21))
    added = Column(DateTime(timezone=True))
    can_submit = Column(Boolean, default=False)
    link_karma = Column(Integer, default=0)
    num_submissions = Column(Integer, default=0)
    last_submitted = Column(DateTime(timezone=True))
    can_comment = Column(Boolean, default=True)
    comment_karma = Column(Integer, default=0)
    num_comments = Column(Integer, default=0)
    last_commented = Column(DateTime(timezone=True))
    num_votes = Column(Integer, default=0)
    last_voted = Column(DateTime(timezone=True))
    proxy_url = Column(String(255), default="")

    def __init__(
        self,
        name,
        password,
        subreddit,
        can_comment=True,
        can_submit=True,
        config=None,
        engine=None,
        output=None,
    ):
        self.name = name.lower()
        self.password = password
        self.subreddit = subreddit.lower()
        if self.subreddit.startswith("r/"):
            self.subreddit = self.subreddit[2:]

        self.can_comment = can_comment
        self.can_submit = can_submit
        if not self.added:
            self.added = datetime.now(pytz.utc)

        self.config = config
        self.db = engine.create_session()
        self.output = output

    @property
    def session(self):
        if not hasattr(self, "_session"):
            echo(
                "$FG_WHITE${DIM}Logging in as $FG_CYAN$BOLD${name}$NORMAL$FG_WHITE "
                "with $FG_LIGHTBLACK${password}$FG_WHITE$DIM...",
                name=self.name,
                password=self.password,
                file=self.output,
                max_length=-1,
            )

            requestor_kwargs = {}
            if self.config.allow_self_signed_ssl_certs:
                echo("$FG_YELLOW${DIM}Allowing self-signed SSL certs", file=self.output)
                requests.packages.urllib3.disable_warnings()
                unverified_session = requests.Session()
                unverified_session.verify = False
                requestor_kwargs = {"session": unverified_session}

            if self.config.random_proxy_per_account:
                session = requestor_kwargs.get("session", requests.Session())
                if not self.proxy_url:
                    self.proxy_url = self.config.random_proxy["https"]

                session.proxies = {
                    "https": self.proxy_url,
                    "http": self.proxy_url.replace("https:", "http:"),
                }
                echo(
                    "$FG_CYAN${DIM}Using proxy $BOLD${url}$NORMAL for account $BOLD${name}",
                    max_length=-1,
                    file=self.output,
                    url=self.proxy_url,
                    name=self.name,
                )

                requestor_kwargs = {"session": session}

            if not requestor_kwargs:
                requestor_kwargs = None

            self._session = praw.Reddit(
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
                user_agent=self.config.user_agent,
                username=self.name,
                password=self.password,
                reddit_url=self.config.reddit_url,
                oauth_url=self.config.oauth_url,
                short_url=self.config.short_url,
                comment_kind=self.config.comment_kind,
                message_kind=self.config.message_kind,
                redditor_kind=self.config.redditor_kind,
                submission_kind=self.config.submission_kind,
                subreddit_kind=self.config.subreddit_kind,
                requestor_kwargs=requestor_kwargs,
            )

        try:
            me = self._session.user.me(use_cache=False)
            self.link_karma = int(me.link_karma)
            self.comment_karma = int(me.comment_karma)
            if self.num_comments < self.comment_karma:
                self.num_comments = self.comment_karma
                self.last_commented = datetime.now(pytz.utc)
            if self.num_submissions < self.link_karma:
                self.num_submissions = self.link_karma
                self.last_submitted = datetime.now(pytz.utc)
            self.db.add(self)
            self.db.flush()
            self.db.commit()
        except prawcore.exceptions.OAuthException as err:
            echo(
                "$BG_RED$FG_YELLOW${BOLD}OAUTH ERROR:${NORMAL} ${err}",
                err=str(err),
                file=self.output,
                max_length=-1,
            )
            sys.exit(2)

        limits = self._session.auth.limits
        reset = (
            datetime.utcfromtimestamp(limits.get("reset_timestamp", 0))
            - datetime.utcnow()
        )
        used, remaining = limits.get("used", "?"), limits.get("remaining", "?")
        echo(
            "${DIM}API LIMITS for $BOLD$FG_CYAN${name}$NORMAL$DIM: "
            "$FG_RED${BOLD}used$NORMAL=${used}$DIM, "
            "$FG_YELLOW${BOLD}remaining$NORMAL=$DIM${remaining}, "
            "$FG_GREEN${BOLD}reset_after$NORMAL=$DIM${reset_after}",
            file=self.output,
            name=self.name,
            used=used,
            remaining=remaining,
            reset_after=reset,
            max_length=-1,
        )
        return self._session

    @property
    def can_vote(self):
        min_karma = self.config.min_karma_to_vote
        return self.can_submit and self.can_comment and self.total_karma >= min_karma

    @property
    def total_karma(self):
        return (self.comment_karma or 0) + (self.link_karma or 0)

    @property
    def mean_comment_karma(self):
        if self.num_comments == 0:
            return 0
        else:
            return round(self.comment_karma / float(self.num_comments), 2)

    @property
    def mean_link_karma(self):
        if self.num_submissions == 0:
            return 0
        else:
            return round(self.link_karma / float(self.num_submissions), 2)

    def get_comments_from_site(self, limit=100, store_in_db=True):
        echo(
            "$FG_WHITE${DIM}Getting up to ${limit} comments from $BOLD${subreddit}...",
            max_length=-1,
            limit=limit,
            subreddit=self.subreddit,
            file=self.output,
        )

        subreddit = self.session.subreddit(self.subreddit)

        seen_ids = set(
            c.id for c in self.db.query(Comment).filter_by(subreddit=self.subreddit)
        )

        comments = []

        for comment in subreddit.comments(limit=limit):
            comment = Comment(comment, config=self.config)

            if comment.id not in seen_ids:
                seen_ids.add(comment.id)
                comments.append(comment)

            if (
                store_in_db
                and not self.db.query(Comment).filter_by(id=comment.id).first()
            ):
                self.db.add(comment)
                self.db.flush()

        if store_in_db:
            self.db.commit()

        return comments

    def get_submissions_from_site(self, limit=100, store_in_db=True, top_of="day"):
        echo(
            "$FG_WHITE${DIM}Getting up to ${limit} top "
            "$BOLD${top}$NORMAL$DIM submissions "
            "from $BOLD${subreddit}...",
            max_length=-1,
            limit=limit,
            top="daily" if top_of == "day" else top_of,
            subreddit=self.subreddit,
            file=self.output,
        )

        subreddit = self.session.subreddit(self.subreddit)

        # get the newest submission we've previously seen as a stopping point
        last_submission = (
            self.db.query(Submission)
            .filter_by(subreddit=self.subreddit)
            .order_by(Submission.date.desc())
            .first()
        )

        seen_ids = set()
        submissions = []

        for submission in subreddit.top(top_of, limit=limit):
            submission = Submission(submission, config=self.config)
            if last_submission:
                if (
                    submission.id == last_submission.id
                    or submission.date <= last_submission.date
                ):
                    break

            # somehow there are occasionally duplicates - skip over them
            if submission.id in seen_ids:
                continue
            seen_ids.add(submission.id)

            submissions.append(submission)
            if store_in_db:
                self.db.add(submission)

        if store_in_db:
            self.db.commit()
        return submissions

    def should_include_comment(self, comment):
        if comment.author in self.config.ignored_users:
            return False

        return True

    def get_comments_for_training(self, limit=None):
        echo(
            "$FG_GREEN${DIM}Getting up to ${limit} recent comments for training "
            "from $BOLD${subreddit}...",
            max_length=-1,
            limit=limit or self.config.max_corpus_size,
            subreddit=self.subreddit,
            file=self.output,
        )

        comments = (
            self.db.query(Comment)
            .filter_by(subreddit=self.subreddit)
            .filter(Comment.body != "")
            .order_by(Comment.date.desc())
            .limit(self.config.max_corpus_size)
        )
        valid_comments = [
            comment for comment in comments if self.should_include_comment(comment)
        ]
        random.shuffle(valid_comments)
        logger.info("valid comments for training: %d", len(valid_comments))
        return valid_comments

    def get_submissions_for_training(self, limit=None):
        echo(
            "$FG_GREEN${DIM}Getting up to ${limit} recent submissions for training "
            "from $BOLD${subreddit}...",
            max_length=-1,
            limit=limit or self.config.max_corpus_size,
            subreddit=self.subreddit,
            file=self.output,
        )

        submissions = list(
            self.db.query(Submission)
            .filter_by(subreddit=self.subreddit)
            .order_by(Submission.date.desc())
            .limit(self.config.max_corpus_size)
        )
        logger.debug("%d total submissions for training", len(submissions))
        valid_submissions = [
            submission
            for submission in submissions
            if not submission.over_18
            and submission.author not in self.config.ignored_users
        ]
        random.shuffle(valid_submissions)
        logger.info("valid submissions for training: %d", len(valid_submissions))
        return valid_submissions

    def train_from_comments(self, get_new_comments=True):
        echo(
            "$FG_WHITE${DIM}Getting ${new}comments for training ",
            max_length=-1,
            new="new " if get_new_comments else " ",
            file=self.output,
        )

        if get_new_comments:
            self.get_comments_from_site()

        comments = []
        for comment in self.get_comments_for_training():
            comments.append(comment.body)

        self.avg_comment_len = sum(len(c) for c in comments) / float(
            len(comments) or 0.001
        )
        self.avg_comment_len = min(250, self.avg_comment_len)

        if self.avg_comment_len >= 140:
            state_size = 3
        else:
            state_size = 2

        try:
            self.comment_model = SubredditSimulatorText(
                " ".join(comments).strip(), state_size=state_size
            )
        except (ValueError, IndexError) as err:
            logger.error("Cannot construct comment model: %s", err, exc_info=True)
            self.comment_model = None
            return False

        return True

    def train_from_submissions(self, get_new_submissions=True):
        if get_new_submissions:
            submissions = self.get_submissions_from_site(top_of="day")
            if not submissions:
                submissions = self.get_submissions_from_site(top_of="all")
            if not submissions:
                submissions = self.get_submissions_for_training()
        else:
            submissions = self.get_submissions_for_training()

        titles = []
        selftexts = []
        self.link_submissions = []

        logger.debug("%d submissions selected for training", len(submissions))
        for submission in submissions:
            titles.append(submission.title)
            if submission.url:
                self.link_submissions.append(submission)
            else:
                selftexts.append(submission.body)

        self.link_submission_chance = len(self.link_submissions) / float(
            len(submissions) or 0.001
        )

        logger.debug("%d titles extracted: %r", len(titles), titles)
        try:
            self.title_model = SubredditSimulatorText(" ".join(titles), state_size=2)
        except (ValueError, IndexError) as err:
            logger.error("Cannot construct title model: %s", err, exc_info=True)
            self.title_model = None
            return False

        if selftexts:
            self.avg_selftext_len = sum(len(s) for s in selftexts) / float(
                len(selftexts)
            )
            self.avg_selftext_len = min(250, self.avg_selftext_len)
            # if the average selftext length is very low, we won't even bother
            # creating a model, and will submit with only titles
            if self.avg_selftext_len <= 50:
                self.selftext_model = None
            else:
                if self.avg_selftext_len >= 140:
                    state_size = 3
                else:
                    state_size = 2
                try:
                    self.selftext_model = SubredditSimulatorText(
                        " ".join(selftexts), state_size=state_size
                    )
                except (ValueError, IndexError) as err:
                    logger.error(
                        "Cannot construct selftext model: %s", err, exc_info=True
                    )
                    self.selftext_model = None
                    return False

        return True

    def make_comment_sentence(self):
        return (
            self.comment_model.make_sentence(
                tries=10000,
                max_overlap_total=MAX_OVERLAP_TOTAL,
                max_overlap_ratio=MAX_OVERLAP_RATIO,
            )
            if self.comment_model
            else None
        )

    def build_comment(self):
        comment = []
        while True:
            # For each sentence, check how close to the average comment length
            # we are, then use the remaining percentage as the chance of
            # adding another sentence. For example, if we're at 70% of the
            # average comment length, there will be a 30% chance of adding
            # another sentence. We're also adding a fixed 10% on top of that
            # just to increase the length a little, and have some chance of
            # continuing once we're past the average.
            portion_done = len("".join(comment)) / float(self.avg_comment_len)
            continue_chance = 1.0 - portion_done
            continue_chance = max(0, continue_chance)
            continue_chance += 0.1
            if random.random() > continue_chance:
                break

            new_sentence = self.make_comment_sentence()
            if not new_sentence:
                continue

            comment.append(new_sentence)

        comment = self.comment_model.sentence_join(comment)

        return comment

    def make_selftext_sentence(self):
        return (
            self.selftext_model.make_sentence(
                tries=10000,
                max_overlap_total=MAX_OVERLAP_TOTAL,
                max_overlap_ratio=MAX_OVERLAP_RATIO,
            )
            if self.selftext_model
            else None
        )

    def post_comment_on(self, submission):
        comment = self.build_comment()

        # decide if we're going to post top-level or reply
        if submission.num_comments <= 0 or random.random() < 0.5:
            try:
                submission.reply(comment)
            except praw.exceptions.PRAWException as err:
                echo(
                    "$BG_RED$FG_YELLOW${BOLD}REPLY ERROR:${NORMAL} ${err}",
                    err=str(err),
                    file=self.output,
                    max_length=-1,
                )
                return False

        else:
            submission.comments.replace_more(limit=None)
            comments = submission.comments.list()
            if not comments:
                return False
            reply_to = random.choice(comments)
            try:
                reply_to.reply(comment)
            except praw.exceptions.PRAWException as err:
                echo(
                    "$BG_RED$FG_YELLOW${BOLD}REPLY ERROR:${NORMAL} ${err}",
                    err=str(err),
                    file=self.output,
                    max_length=-1,
                )
                return False

        # update the database
        self.last_commented = datetime.now(pytz.utc)
        self.num_comments += 1
        self.db.add(self)
        self.db.flush()
        self.db.commit()
        self.session  # force refresh
        return True

    def pick_submission_type(self):
        if not self.link_submissions:
            return "text"

        if random.random() < self.link_submission_chance:
            return "link"
        else:
            return "text"

    def post_submission(self, subreddit, type=None):
        subreddit = self.session.subreddit(subreddit)

        title = (
            self.title_model.make_short_sentence(
                140,
                tries=10000,
                max_overlap_total=MAX_OVERLAP_TOTAL,
                max_overlap_ratio=MAX_OVERLAP_RATIO,
            )
            if self.title_model
            else None
        )
        if not title:
            return False

        title = title.rstrip(".")

        if not type:
            type = self.pick_submission_type()

        if type == "link":
            url_source = random.choice(self.link_submissions)

            if url_source.over_18:
                title = "[NSFW] " + title

            try:
                subreddit.submit(title, url=url_source.url, send_replies=False)
            except praw.exceptions.PRAWException as err:
                echo(
                    "$BG_RED$FG_YELLOW${BOLD}SUBMIT ERROR:${NORMAL} ${err}",
                    err=str(err),
                    file=self.output,
                    max_length=-1,
                )
                return False

        else:
            selftext = ""
            while len(selftext) < self.avg_selftext_len:
                new_sentence = SubredditSimulatorText.prepare_sentance(
                    self.make_selftext_sentence()
                )
                if not new_sentence:
                    break
                selftext += " " + new_sentence
            selftext = selftext.strip()

            # need to do this to be able to submit an empty self-post
            if len(selftext) == 0:
                selftext = " "

            try:
                subreddit.submit(title, selftext=selftext, send_replies=False)
            except praw.exceptions.PRAWException as err:
                echo(
                    "$BG_RED$FG_YELLOW${BOLD}SUBMIT ERROR:${NORMAL} ${err}",
                    err=str(err),
                    file=self.output,
                    max_length=-1,
                )
                return False

        # update the database
        self.last_submitted = datetime.now(pytz.utc)
        self.num_submissions += 1
        self.db.add(self)
        self.db.flush()
        self.db.commit()
        self.session  # force refresh
        return True


def normalize_html_text(html_text):
    if not html_text or not html_text.strip():
        return ""

    body = []

    class Parser(html.parser.HTMLParser):
        def handle_data(self, data):
            body.append(SubredditSimulatorText.prepare_sentance(data))

    p = Parser()
    p.feed(html.unescape(html_text))
    p.close()

    text = " ".join(map(str.strip, body))
    return SubredditSimulatorText.prepare_sentance(text)


class Comment(Base):  # type: ignore
    __tablename__ = "comments"

    id = Column(String(10), primary_key=True)
    subreddit = Column(String(21))
    date = Column(DateTime)
    is_top_level = Column(Boolean)
    author = Column(String(20))
    body = Column(Text)
    score = Column(Integer)
    permalink = Column(Text)

    __table_args__ = (Index("ix_comment_subreddit_date", "subreddit", "date"),)

    def __init__(self, comment, *, config=None):
        self.id = comment.id
        self.config = config
        self.subreddit = comment.subreddit.display_name.lower()
        self.date = datetime.utcfromtimestamp(comment.created_utc)
        self.is_top_level = comment.parent_id.startswith(
            f"{self.config.submission_kind}_"
        )
        if comment.author:
            self.author = comment.author.name
        else:
            self.author = "[deleted]"
        self.body = normalize_html_text(comment.body_html or comment.body)
        self.score = comment.score or 0
        permalink = getattr(comment, "permalink", "")
        self.permalink = f"{self.config.reddit_url}{permalink}"


class Submission(Base):  # type: ignore
    __tablename__ = "submissions"

    id = Column(String(10), primary_key=True)
    subreddit = Column(String(21))
    date = Column(DateTime)
    author = Column(String(20))
    title = Column(Text)
    url = Column(Text)
    body = Column(Text)
    score = Column(Integer)
    over_18 = Column(Boolean)
    permalink = Column(Text)

    __table_args__ = (Index("ix_submission_subreddit_date", "subreddit", "date"),)

    def __init__(self, submission, *, config=None):
        self.id = submission.id
        self.subreddit = submission.subreddit.display_name.lower()
        self.date = datetime.utcfromtimestamp(submission.created_utc)
        if submission.author:
            self.author = submission.author.name
        else:
            self.author = "[deleted]"
        self.title = submission.title
        if submission.is_self:
            self.body = normalize_html_text(submission.selftext_html)
            self.url = None
        else:
            self.body = None
            self.url = submission.url
        self.score = submission.score or 0
        self.over_18 = submission.over_18
        self.config = config
        permalink = getattr(submission, "permalink", "")
        self.permalink = f"{self.config.reddit_url}{permalink}"
