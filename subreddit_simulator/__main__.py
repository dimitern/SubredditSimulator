import logging
import os
import time
from collections import defaultdict
from datetime import datetime

from . import Simulator
from .database import cfg_file, db
from .models import Account, Setting, Settings

if os.environ.get("SUBREDDIT_SIMULATOR_PRAWCORE_LOGGING", False):
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    logger = logging.getLogger("prawcore")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)


def configure_settings():

    items = defaultdict(str)
    items.setdefault("subreddit", "")
    items.setdefault("owner", "")
    items.setdefault("max_corpus_size", "1000")
    items.setdefault("client_id", "")
    items.setdefault("client_secret", "")
    items.setdefault("user_agent", "")
    items.setdefault("comment_delay_seconds", "300")
    items.setdefault("submission_delay_seconds", "1200")
    items.setdefault("leaderboard_update_delay_seconds", "3600")
    items.setdefault("main_loop_delay_seconds", "60")
    items.setdefault("ignored_users", [])

    for key, value in dict(cfg_file.items("settings")).items():
        key, value = key.strip(), value.strip()

        if key not in items:
            raise ValueError(f"Invalid [settings] section key {key}!")

        if value:
            if value.startswith("r/"):
                value = value.lower()[2:]

            elif key == "ignored_users":
                value = [u.strip() for u in value.split(",") if u.strip()]

            else:
                try:
                    value = int(value)
                except ValueError:
                    pass

        setting = Setting(name=key, value=value)
        if db.query(Setting).filter_by(name=key).count() == 0:
            db.add(setting)
            db.commit()

    global Settings

    for setting in db.query(Setting):
        Settings[setting.name] = setting.value


def configure_accounts():

    items = defaultdict(list)
    items.setdefault("usernames_csv", [])
    items.setdefault("passwords_csv", [])
    items.setdefault("subreddits_csv", [])

    for key, value in dict(cfg_file.items("accounts")).items():
        key, value = key.strip(), value.strip()

        if key not in items:
            raise ValueError(f"Invalid [accounts] section key {key}!")

        if not value:
            raise ValueError(f"Empty value for [accounts] section key {key}!")

        value = [v.strip() for v in value.split(",") if v.strip()]

        items[key].extend(value)

    for name, subreddit, password in zip(
        items["usernames_csv"], items["subreddits_csv"], items["passwords_csv"]
    ):
        account = Account(name=name, subreddit=subreddit, password=password)
        if db.query(Account).filter_by(name=name).count() == 0:
            db.add(account)
            db.commit()


configure_settings()
configure_accounts()

print("\nSettings:\n---------")
print("\n".join(f"{s.name}: {s.value!r}" for s in db.query(Setting).all()))

s = Simulator()
s.print_accounts_table()
last_comment = last_submission = last_update = time.time()

print("\nStarting main loop on {}".format(datetime.now().isoformat()))

while True:
    time.sleep(Settings["main_loop_delay_seconds"])
    now = time.time()

    if now - last_update >= Settings["leaderboard_update_delay_seconds"]:
        print("Updating leaderboard on r/{}".format(s.subreddit))
        if s.update_leaderboard():
            last_update = time.time()

    if now - last_comment >= Settings["comment_delay_seconds"]:
        print("Making a comment on r/{}".format(s.subreddit))
        if s.make_comment():
            last_comment = time.time()

    if now - last_submission >= Settings["submission_delay_seconds"]:
        print("Making a submission on r/{}".format(s.subreddit))
        if s.make_submission():
            last_submission = time.time()

print("Stopped main loop on {}".format(datetime.now().isoformat()))
