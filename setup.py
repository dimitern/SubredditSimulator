from setuptools import find_packages, setup

from pipenv.project import Project
from pipenv.utils import convert_deps_to_pip
from subreddit_simulator import __version__

pfile = Project(chdir=False).parsed_pipfile
requirements = convert_deps_to_pip(pfile["packages"], r=False)

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
    install_requires=requirements,
    py_modules=["subreddit_simulator"],
    entry_points="""
    [console_scripts]
    subreddit_simulator=subreddit_simulator.cli:main
    """,
)
