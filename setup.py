from setuptools import setup

from subreddit_simulator import __version__

setup(
    name="SubredditSimulator",
    version=__version__,
    description="An automated bot-run subreddit using markov chains",
    author="Chad Birch",
    author_email="chad.birch@gmail.com",
    maintainer="Dimiter Naydenov",
    maintainer_email="dimiter.naydenov@gmail.com",
    platforms=["any"],
    license="MIT",
    url="https://github.com/dimitern/SubredditSimulator",
    install_requires=[
        "click",
        "pipenv",
        "colorama",
        "praw",
        "attrs",
        "markovify",
        "requests",
        "SQLAlchemy",
    ],
    py_modules=["subreddit_simulator"],
    entry_points="""
    [console_scripts]
    subreddit_simulator=subreddit_simulator.cli:main
    """,
)
