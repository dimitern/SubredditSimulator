# SubredditSimulator

This is a fork of the original project described below.
I created it to be used for https://www.reddit.com/r/ProjectOblio/ - check in there for details.

Summary of the changes I did:

 * Converted all sources to Python 3.7, and reformatted them using `black` and `isort`.
 * Upgraded all `requirements.text` to the latest versions, incl. `psycopg2-binary`, `praw`.
 * Migrated to using `pipenv` for stable and easier to manager requirements.
 * Added `cli.py` to make the package easier to install and use (run `subreddit_simulator --help`
   for details).
 * Added `top_subreddits.py` to fetch lists of top crypto-currency subreddits.
 * Extended the `subreddit_simulator.cfg` to contain all the needed information.
 * Running with `-CD` drops and re-creates the database schema, with `-S` shows database contents.
 * Running with `-v` (up to `-vvv`) enables verbose logging of API hits.
 * Numerous fixes in the original code, lots of testing on a local instance of reddit and reddit.com

## Setting up

Clone the source first, you'll need `Python 3.7` or later (with f-strings), a database (SQLite
should work, but haven't tested - PostgreSQL is preferred), a `subreddit_simulator.cfg` file
(use the example provided; should be simple to customize), and `Linux` machine (only tested on
`Ubuntu 16.04 LTS`, but should in theory work on other OSes).

Install Python 3.7 and `pipenv` (if not present):

```
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.7
sudo python3.7 -mensurepip
sudo python3.7 -mpip install --upgrade pip wheel setuptools pipenv
```

Create a virtual environment and install required packages:
```
python3.7 -mpipenv --python 3.7
python3.7 -mpipenv shell
pipenv install --dev
```

Run (assuming everything is configured as needed, you should see info about the settings, accounts, etc.):
```
subreddit_simulator --help
```

To run the main loop of the bot, use `subreddit_simulator -r`.

The rest of this README is copied from the original project.

---

This is the code behind [/r/SubredditSimulator](https://www.reddit.com/r/SubredditSimulator), an automated subreddit populated by bots making submissions and comments, primarily using markov chains based on the actual posts in other subreddits.

## Disclaimer

This project is deliberately somewhat difficult to get running (requiring reading of the code and undocumented, manual configuration of some things). Markov chain bots can be hilarious, but they also have the potential to be annoying to real users if released "into the wild", so it is not my intention to make it extremely simple for anyone to start running similar bots.

## Suggestions/discussion/etc.

To discuss SubredditSimulator in general, make suggestions for changes to its behavior, and so on, please use [/r/SubredditSimMeta on reddit](https://www.reddit.com/r/SubredditSimMeta).
