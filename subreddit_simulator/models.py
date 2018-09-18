import html
import os
import random
import sys
from datetime import datetime

import markovify
import praw
import prawcore
import pytz
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql.expression import func

from .database import JSONSerialized, db, engine

MAX_OVERLAP_RATIO = 0.5
MAX_OVERLAP_TOTAL = 10


Base = declarative_base()


def flatten_tree(tree, nested_attr="replies", depth_first=False):
    """Return a flattened version of the passed in tree.
    :param nested_attr: The attribute name that contains the nested items.
        Defaults to ``replies`` which is suitable for comments.
    :param depth_first: When true, add to the list in a depth-first manner
        rather than the default breadth-first manner.
    """
    stack = tree[:]
    retval = []
    while stack:
        item = stack.pop(0)
        nested = getattr(item, nested_attr, None)
        if nested and depth_first:
            stack.extend(nested)
        elif nested:
            stack[0:0] = nested
        retval.append(item)
    return retval


class SubredditSimulatorText(markovify.Text):
    def __init__(self, input_text, state_size=2, **kwargs):
        input_text = html.unescape(input_text)
        super().__init__(input_text, state_size=state_size, **kwargs)


class Setting(Base):
    __tablename__ = "settings"

    name = Column(String(100), primary_key=True)
    value = Column(JSONSerialized)


class Account(Base):
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

    def __init__(self, name, password, subreddit, can_comment=True, can_submit=True):
        self.name = name
        self.password = password
        self.subreddit = subreddit.lower()
        if self.subreddit.startswith("r/"):
            self.subreddit = self.subreddit[2:]

        self.can_comment = can_comment
        self.can_submit = can_submit
        if not self.added:
            self.added = datetime.now(pytz.utc)

    @property
    def session(self):
        if not hasattr(self, "_session"):
            print(f"Logging in as {self.name!r} with {self.password!r}...")
            self._session = praw.Reddit(
                client_id=Settings["client_id"],
                client_secret=Settings["client_secret"],
                user_agent=Settings["user_agent"],
                username=self.name,
                password=self.password,
            )

            try:
                me = self._session.user.me()
                self.link_karma = int(me.link_karma)
                self.comment_karma = int(me.comment_karma)
            except prawcore.exceptions.OAuthException as err:
                print(f"OAUTH ERROR: {err!s}")
                sys.exit(2)

        return self._session

    @property
    def is_able_to_submit(self):
        # captcha_exempt = self.comment_karma > 5 or self.link_karma > 2
        return self.can_submit

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

    def get_comments_from_site(self, limit=1000, store_in_db=True):
        subreddit = self.session.subreddit(self.subreddit)

        # get the newest comment we've previously seen as a stopping point
        last_comment = (
            db.query(Comment)
            .filter_by(subreddit=self.subreddit)
            .order_by(Comment.date.desc())
            .first()
        )

        seen_ids = set()
        comments = []

        for comment in subreddit.comments(limit=limit):
            comment = Comment(comment)

            if last_comment:
                if comment.id == last_comment.id or comment.date <= last_comment.date:
                    break

            # somehow there are occasionally duplicates - skip over them
            if comment.id in seen_ids:
                continue
            seen_ids.add(comment.id)

            comments.append(comment)
            if store_in_db:
                db.add(comment)

        if store_in_db:
            db.commit()
        return comments

    def get_submissions_from_site(self, limit=1000, store_in_db=True):
        subreddit = self.session.subreddit(self.subreddit)

        # get the newest submission we've previously seen as a stopping point
        last_submission = (
            db.query(Submission)
            .filter_by(subreddit=self.subreddit)
            .order_by(Submission.date.desc())
            .first()
        )

        seen_ids = set()
        submissions = []

        for submission in subreddit.new(limit=limit):
            submission = Submission(submission)
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
                db.add(submission)

        if store_in_db:
            db.commit()
        return submissions

    def should_include_comment(self, comment):
        if comment.author in Settings["ignored_users"]:
            return False

        if "+/u/user_simulator" in comment.body.lower():
            return False

        return True

    def get_comments_for_training(self, limit=None):
        comments = (
            db.query(Comment)
            .filter_by(subreddit=self.subreddit)
            .order_by(func.random())
            .limit(Settings["max_corpus_size"])
        )
        valid_comments = [
            comment for comment in comments if self.should_include_comment(comment)
        ]
        return valid_comments

    def get_submissions_for_training(self, limit=None):
        submissions = (
            db.query(Submission)
            .filter_by(subreddit=self.subreddit)
            .order_by(func.random())
            .limit(Settings["max_corpus_size"])
        )
        valid_submissions = [
            submission
            for submission in submissions
            if not submission.over_18
            and submission.author not in Settings["ignored_users"]
        ]
        return valid_submissions

    def train_from_comments(self, get_new_comments=True):
        if get_new_comments:
            self.get_comments_from_site()

        comments = []
        for comment in self.get_comments_for_training():
            comments.append(comment.body)
        self.avg_comment_len = sum(len(c) for c in comments) / float(len(comments))
        self.avg_comment_len = min(250, self.avg_comment_len)
        if self.avg_comment_len >= 140:
            state_size = 3
        else:
            state_size = 2
        self.comment_model = SubredditSimulatorText(
            "\n".join(comments), state_size=state_size
        )

    def train_from_submissions(self, get_new_submissions=True):
        if get_new_submissions:
            self.get_submissions_from_site()

        titles = []
        selftexts = []
        self.link_submissions = []

        all_submissions = self.get_submissions_for_training()
        for submission in all_submissions:
            titles.append(submission.title)
            if submission.url:
                self.link_submissions.append(submission)
            else:
                selftexts.append(submission.body)

        self.link_submission_chance = len(self.link_submissions) / float(
            len(all_submissions)
        )

        self.title_model = SubredditSimulatorText("\n".join(titles), state_size=2)
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
                        "\n".join(selftexts), state_size=state_size
                    )
                except IndexError:
                    # I'm not sure what causes this yet
                    self.selftext_model = None

    def make_comment_sentence(self):
        return self.comment_model.make_sentence(
            tries=10000,
            max_overlap_total=MAX_OVERLAP_TOTAL,
            max_overlap_ratio=MAX_OVERLAP_RATIO,
        )

    def build_comment(self):
        comment = ""
        while True:
            # For each sentence, check how close to the average comment length
            # we are, then use the remaining percentage as the chance of
            # adding another sentence. For example, if we're at 70% of the
            # average comment length, there will be a 30% chance of adding
            # another sentence. We're also adding a fixed 10% on top of that
            # just to increase the length a little, and have some chance of
            # continuing once we're past the average.
            portion_done = len(comment) / float(self.avg_comment_len)
            continue_chance = 1.0 - portion_done
            continue_chance = max(0, continue_chance)
            continue_chance += 0.1
            if random.random() > continue_chance:
                break

            new_sentence = self.make_comment_sentence()
            comment += " " + new_sentence

        comment = comment.strip()

        return comment

    def make_selftext_sentence(self):
        if self.selftext_model:
            return self.selftext_model.make_sentence(
                tries=10000,
                max_overlap_total=MAX_OVERLAP_TOTAL,
                max_overlap_ratio=MAX_OVERLAP_RATIO,
            )
        else:
            return None

    def post_comment_on(self, submission):
        comment = self.build_comment()

        # decide if we're going to post top-level or reply
        if submission.num_comments == 0 or random.random() < 0.5:
            try:
                submission.reply(comment)
            except praw.exceptions.PRAWException as err:
                print(f"REPLY ERROR: {err!s}")
                return False

        else:
            comments = flatten_tree(submission.comments)
            if not comments:
                return False
            reply_to = random.choice(comments)
            try:
                reply_to.reply(comment)
            except praw.exceptions.PRAWException as err:
                print(f"REPLY ERROR: {err!s}")
                return False

        # update the database
        self.last_commented = datetime.now(pytz.utc)
        self.num_comments += 1
        db.add(self)
        db.commit()
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

        title = self.title_model.make_short_sentence(
            300,
            tries=10000,
            max_overlap_total=MAX_OVERLAP_TOTAL,
            max_overlap_ratio=MAX_OVERLAP_RATIO,
        )
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
                print(f"SUBMIT ERROR: {err!s}")
                return False

        else:
            selftext = ""
            while len(selftext) < self.avg_selftext_len:
                new_sentence = self.make_selftext_sentence()
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
                print(f"SUBMIT ERROR: {err!s}")
                return False

        # update the database
        self.last_submitted = datetime.now(pytz.utc)
        self.num_submissions += 1
        db.add(self)
        db.commit()
        return True


class Comment(Base):
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

    def __init__(self, comment):
        self.id = comment.id
        self.subreddit = comment.subreddit.display_name.lower()
        self.date = datetime.utcfromtimestamp(comment.created_utc)
        self.is_top_level = comment.parent_id.startswith("t3_")
        if comment.author:
            self.author = comment.author.name
        else:
            self.author = "[deleted]"
        self.body = comment.body
        self.score = comment.score
        self.permalink = f"https://www.reddit.com{comment.permalink}"


class Submission(Base):
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

    def __init__(self, submission):
        self.id = submission.id
        self.subreddit = submission.subreddit.display_name.lower()
        self.date = datetime.utcfromtimestamp(submission.created_utc)
        if submission.author:
            self.author = submission.author.name
        else:
            self.author = "[deleted]"
        self.title = submission.title
        if submission.is_self:
            self.body = submission.selftext
            self.url = None
        else:
            self.body = None
            self.url = submission.url
        self.score = submission.score
        self.over_18 = submission.over_18
        self.permalink = f"https://www.reddit.com{submission.permalink}"


if os.environ.get("SUBREDDIT_SIMULATOR_DROP_ALL", False):
    Base.metadata.drop_all(engine)

Base.metadata.create_all(engine)

Settings = {}
