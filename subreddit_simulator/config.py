import re
import sys
from configparser import SafeConfigParser
from operator import attrgetter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import attr
from sqlalchemy.orm import Session

BOOL_VALUES: Dict[bool, Tuple[str, ...]] = {
    True: ("true", "on", "yes", "1"),
    False: ("", "false", "off", "no", "0"),
}

StringParser = Callable[[str], str]
StringListParser = Callable[[str], List[str]]


def str_lower(value: str) -> str:
    return value.lower()


def parse_bool(value: Any) -> bool:
    if isinstance(value, str):
        value = value.lower().strip()
        for bool_value, str_variants in BOOL_VALUES.items():
            if value in str_variants:
                value = bool_value
                break
    return bool(value)


def parse_user(value: str) -> str:
    value = value.lower().strip()
    if value.startswith("/"):
        value = value[1:]
    if value.startswith(("u/", "user/")):
        *_, value = value.partition("/")
    return value


def parse_subreddit(value: str) -> str:
    value = value.lower().strip()
    if value.startswith("/"):
        value = value[1:]
    if value.startswith("r/"):
        value = value[2:]
    return value


def parse_csv(items_parser: StringParser) -> StringListParser:
    def inner(value: str) -> List[str]:
        if not value or not value.strip():
            return []
        return list(map(items_parser, map(str.strip, value.strip().split(","))))

    return inner


def parse_users_csv(items: str) -> StringListParser:
    return parse_csv(parse_user)


def parse_str_csv(items: str) -> StringListParser:
    return parse_csv(str)


def parse_subreddit_csv(items: str) -> StringListParser:
    return parse_csv(parse_subreddit)


@attr.s
class Config:
    # Database configuration.
    system: str = attr.ib(default="sqlite", converter=str_lower)
    username: str = attr.ib(default="")
    password: str = attr.ib(default="", repr=False)
    host: str = attr.ib(default="", converter=str_lower)
    port: int = attr.ib(default=0, converter=int)
    database: str = attr.ib(default="subreddit_simulator")

    # Subreddit configuration.
    subreddit: str = attr.ib(default="", converter=parse_subreddit)
    owner: str = attr.ib(default="", converter=parse_user)
    moderator: str = attr.ib(default="", converter=parse_user)

    # OAuth2 configuration.
    client_id: str = attr.ib(default="", repr=False)
    client_secret: str = attr.ib(default="", repr=False)
    user_agent: str = attr.ib(default="")

    # Optional settings.
    max_corpus_size: int = attr.ib(default=1000, converter=int)
    ignored_users: List[str] = attr.ib(factory=list, converter=parse_users_csv)

    # Main loop configuration.
    comment_delay_seconds: int = attr.ib(default=600, converter=int)
    submission_delay_seconds: int = attr.ib(default=1200, converter=int)
    leaderboard_update_delay_seconds: int = attr.ib(default=1800, converter=int)
    main_loop_delay_seconds: int = attr.ib(default=60, converter=int)
    voting_delay_seconds: int = attr.ib(default=60, converter=int)

    last_comment: float = attr.ib(default=0.0, converter=float)
    last_submission: float = attr.ib(default=0.0, converter=float)
    last_update: float = attr.ib(default=0.0, converter=float)
    last_vote: float = attr.ib(default=0.0, converter=float)

    # Accounts configuration.
    usernames_csv: List[str] = attr.ib(factory=list, converter=parse_users_csv)
    passwords_csv: List[str] = attr.ib(factory=list, converter=parse_str_csv)
    subreddits_csv: List[str] = attr.ib(factory=list, converter=parse_subreddit_csv)

    # Top subreddits configuration.
    url: str = attr.ib(default="")
    # Regular expression for subreddit names to match in the response.
    name_regexp: re.Pattern = attr.ib(default="", converter=re.compile)  # type: ignore

    # NOTE: The following config settings should not be changed,
    # unless using a custom Reddit instance, rather than reddit.com.
    comment_kind: str = attr.ib(default="t1", converter=str_lower)
    message_kind: str = attr.ib(default="t4", converter=str_lower)
    redditor_kind: str = attr.ib(default="t2", converter=str_lower)
    submission_kind: str = attr.ib(default="t3", converter=str_lower)
    subreddit_kind: str = attr.ib(default="t5", converter=str_lower)
    oauth_url: str = attr.ib(default="https://oauth.reddit.com")
    reddit_url: str = attr.ib(default="https://www.reddit.com")
    short_url: str = attr.ib(default="https://redd.it")
    allow_self_signed_ssl_certs: bool = attr.ib(default=False, converter=parse_bool)

    @classmethod
    def from_file(cls, filename: str = "subreddit_simulator.cfg") -> "Config":
        path = Path(__file__).with_name(filename)
        if not path.exists():
            print(f"ERROR: No {path!s} found!")
            sys.exit(1)

        parser = SafeConfigParser()
        parser.read(path, encoding="utf-8")

        config: Dict[str, Any] = dict.fromkeys(
            map(attrgetter("name"), attr.fields(cls)), ""
        )
        sections = ("database", "settings", "accounts", "top_subreddits")
        for section in sections:
            if not parser.has_section(section):
                print(f"ERROR: No [{section}] in {path!s}!")
                sys.exit(2)

            for key, value in parser.items(section):
                config[key] = value

        return cls(**config)

    @classmethod
    def from_db(cls, db: Session) -> "Config":
        from subreddit_simulator import models

        csvs = ("usernames_csv", "passwords_csv", "subreddits_csv", "ignored_users")
        config: Dict[str, Any] = {}
        for csv in csvs:
            config.setdefault(csv, [])

        for setting in db.query(models.Setting):
            config[setting.name] = setting.value

        for account in db.query(models.Account):
            config["usernames_csv"] += [account.name]
            config["passwords_csv"] += [account.password]
            config["subreddits_csv"] += [account.subreddit]

        for csv in csvs:
            config[csv] = ", ".join(config[csv])

        return cls(**config)

    def merge(self, other: "Config", exclude: Optional[List[str]] = None) -> None:
        for key, value in attr.asdict(other).items():
            if exclude and key in exclude:
                continue
            setattr(self, key, value)

    def update_db(self, db: Session, only: Optional[List[str]] = None) -> None:
        from subreddit_simulator import models

        settings = {s.name: s for s in db.query(models.Setting)}
        for name, value in attr.asdict(self).items():
            if name.endswith("_csv"):
                continue

            if only and name not in only:
                continue

            if name.endswith("_regexp"):
                value = str(value.pattern)

            if name not in settings:
                settings[name] = models.Setting(name=name, value=None)

            if settings[name].value != value:
                settings[name].value = value
                db.add(settings[name])

        if only and not set(
            ["usernames_csv", "passwords_csv", "subreddits_csv"]
        ).isdisjoint(set(only)):
            db.commit()
            return

        accounts = {a.name: a for a in db.query(models.Account)}
        for username, password, subreddit in zip(
            self.usernames_csv, self.passwords_csv, self.subreddits_csv
        ):
            if username not in accounts:
                accounts[username] = models.Account(username, None, None)

            if (
                accounts[username].password != password
                or accounts[username].subreddit != subreddit
            ):
                accounts[username].password = password
                accounts[username].subreddit = subreddit
                db.add(accounts[username])

        db.commit()

    @property
    def database_url(self):
        prefix = f"{self.system}://"
        auth = f"{self.username}:{self.password}@{self.host}:{self.port}"
        suffix = f"/{self.database}"

        if self.system == "sqlite":
            return prefix + suffix

        return prefix + auth + suffix


CONFIG = Config.from_file("subreddit_simulator.cfg")
