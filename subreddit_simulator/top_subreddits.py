import re
import sys
from html.parser import HTMLParser

import requests


class TopSubredditsParser(HTMLParser):
    def __init__(self, name_regexp, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name_regexp = re.compile(name_regexp)
        self.subreddits = {}

    def handle_data(self, data):
        match = self.name_regexp.match(data)
        if not match:
            return

        name = match.group(1).strip()
        if name:
            self.subreddits[name] = name


def fetch_subreddits(url, name_regexp):
    parser = TopSubredditsParser(name_regexp)
    with requests.get(url) as response:
        if not response.ok:
            response.raise_for_status()

        for line in response.iter_lines():
            parser.feed(str(line.strip()))

    return parser.subreddits


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: {} '<url>' '<name_regexp>'".format(sys.argv[0]))
        sys.exit(1)

    print(",".join(fetch_subreddits(*sys.argv[1:])))
