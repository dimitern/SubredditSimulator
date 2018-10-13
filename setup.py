from setuptools import find_packages, setup

from subreddit_simulator import __version__

setup(
    name="SubredditSimulator",
    version=__version__,
    description="An automated bot-run subreddit using markov chains",
    author="Chad Birch, Dimiter Naydenov",
    author_email="chad.birch@gmail.com",
    platforms=["any"],
    license="MIT",
    url="https://github.com/dimitern/SubredditSimulator",
    packages=find_packages(),
    install_requires=[i.strip() for i in open("requirements.txt").readlines()],
    py_modules=["subreddit_simulator"],
    entry_points="""
    [console_scripts]
    subreddit_simulator=subreddit_simulator.cli:main
    """,
)
