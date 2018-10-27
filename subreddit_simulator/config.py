import random
import re
from configparser import SafeConfigParser
from operator import attrgetter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import attr

from . import database, models

DEFAULT_SUBREDDIT_SIMULATOR_CONFIG = "subreddit_simulator.cfg"

BOOL_VALUES: Dict[bool, Tuple[str, ...]] = {
    True: ("true", "on", "yes", "1"),
    False: ("", "false", "off", "no", "0"),
}

StringParser = Callable[[str], str]
StringListParser = Callable[[str], List[str]]


def str_lower(value: str) -> str:
    return value.lower()


def optional_float(value: str) -> float:
    return 0 if not value else float(value)


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
    return value.lower()


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


def parse_users_csv(items: str) -> List[str]:
    return parse_csv(parse_user)(items)


def parse_str_csv(items: str) -> List[str]:
    return parse_csv(str)(items)


def parse_subreddit_csv(items: str) -> List[str]:
    return parse_csv(parse_subreddit)(items)


@attr.s
class Config:
    # CLI-related.
    verbose: int = attr.ib(default=0, init=False, repr=False)

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

    last_comment: float = attr.ib(default=0.0, converter=optional_float)
    last_submission: float = attr.ib(default=0.0, converter=optional_float)
    last_update: float = attr.ib(default=0.0, converter=optional_float)
    last_vote: float = attr.ib(default=0.0, converter=optional_float)

    # Accounts configuration.
    usernames_csv: List[str] = attr.ib(factory=list, converter=parse_users_csv)
    passwords_csv: List[str] = attr.ib(factory=list, converter=parse_str_csv)
    subreddits_csv: List[str] = attr.ib(factory=list, converter=parse_subreddit_csv)

    # Top subreddits configuration.
    url: str = attr.ib(default="")
    # Regular expression for subreddit names to match in the response.
    name_regexp: re.Pattern = attr.ib(default="", converter=re.compile)  # type: ignore

    # Proxies configuration.
    proxy_hosts_csv: List[str] = attr.ib(factory=list, converter=parse_str_csv)
    proxy_ports_csv: List[str] = attr.ib(factory=list, converter=parse_str_csv)
    proxy_users_csv: List[str] = attr.ib(factory=list, converter=parse_str_csv)
    proxy_paswd_csv: List[str] = attr.ib(factory=list, converter=parse_str_csv)
    random_proxy_per_account: bool = attr.ib(default=False, converter=parse_bool)

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

    @property
    def proxy_urls(self):
        return [
            f"https://{user}:{paswd}@{host}:{port}/"
            for host, port, user, paswd in zip(
                self.proxy_hosts_csv,
                self.proxy_ports_csv,
                self.proxy_users_csv,
                self.proxy_paswd_csv,
            )
        ]

    @property
    def random_proxy(self):
        proxy = random.choice(self.proxy_urls)
        return {"https": proxy, "http": proxy.replace("https:", "http:")}

    @classmethod
    def from_file(cls, filename: str = None) -> "Config":
        if not filename:
            path = Path(__file__).with_name(DEFAULT_SUBREDDIT_SIMULATOR_CONFIG)
        else:
            path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(str(path))

        parser = SafeConfigParser()
        parser.read(path, encoding="utf-8")

        config: Dict[str, Any] = dict.fromkeys(
            map(attrgetter("name"), attr.fields(cls)), ""
        )

        sections = ("database", "settings", "accounts", "top_subreddits", "proxies")
        for section in sections:
            if not parser.has_section(section):
                raise KeyError(f"No [{section}] in {path!s}!")

            for key, value in parser.items(section):
                config[key] = value

        config.pop("verbose")
        return cls(**config)

    @classmethod
    def from_db(cls, db) -> "Config":
        csvs = (
            "usernames_csv",
            "passwords_csv",
            "subreddits_csv",
            "ignored_users",
            "proxy_users_csv",
            "proxy_hosts_csv",
            "proxy_ports_csv",
            "proxy_paswd_csv",
        )
        config: Dict[str, Any] = {}
        for csv in csvs:
            config.setdefault(csv, [])

        for setting in db.query(models.Setting):
            config[setting.name] = setting.value

        for account in db.query(models.Account):
            config["usernames_csv"] += [account.name.lower()]
            config["passwords_csv"] += [account.password]
            config["subreddits_csv"] += [account.subreddit]

        for csv in csvs:
            config[csv] = ", ".join(config[csv])

        config.pop("verbose", None)
        return cls(**config)

    def merge(
        self,
        other: "Config",
        exclude: Optional[List[str]] = None,
        include: Optional[List[str]] = None,
    ) -> None:
        for key, value in attr.asdict(other).items():
            if exclude and key in exclude:
                continue
            if include and key not in include:
                continue

            setattr(self, key, value)

    def update_db(self, db=None, only: Optional[List[str]] = None) -> None:
        db = database.Engine.from_config(self)
        session = db.create_session()

        settings = {s.name: s for s in session.query(models.Setting)}
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
                session.add(settings[name])

        if only and not set(
            [
                "usernames_csv",
                "passwords_csv",
                "subreddits_csv",
                "proxy_hosts_csv",
                "proxy_ports_csv",
                "proxy_users_csv",
                "proxy_paswd_csv",
            ]
        ).isdisjoint(set(only)):
            session.commit()
            return

        accounts = {a.name.lower(): a for a in session.query(models.Account)}
        for username, password, subreddit in zip(
            self.usernames_csv, self.passwords_csv, self.subreddits_csv
        ):
            username = username.lower()
            if username not in accounts:
                accounts[username] = models.Account(
                    username, "", "", config=self, engine=db
                )

            if (
                accounts[username].password != password
                or accounts[username].subreddit != subreddit
            ):
                accounts[username].password = password
                accounts[username].subreddit = subreddit
                session.add(accounts[username])

        session.commit()
