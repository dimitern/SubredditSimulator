import logging
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import IO, Callable, Tuple

import click

from . import __version__
from .config import DEFAULT_SUBREDDIT_SIMULATOR_CONFIG, Config
from .database import Engine
from .models import Base
from .subreddit_simulator import Simulator
from .utils import ColorStreamHandler, echo, separator


def describe_command(
    description: str,
    success: str,
    subreddit: str,
    verbose: int,
    prefix: str,
    output: IO,
    callback: Callable[[], bool],
    on_success_update: str,
    config: Config,
):
    if verbose > 1:
        echo(
            "\n" + prefix + "${DIM}Trying to $description in ${BOLD}r/${subreddit}...",
            subreddit=subreddit,
            description=description,
            file=output,
        )
    if callback():
        echo(
            prefix + "$success on $BOLD${time}",
            time=datetime.now().isoformat(),
            file=output,
            success=success,
        )
        setattr(config, on_success_update, time.time())
        config.update_db(only=[on_success_update])


def run_main_loop(config: Config, simulator: Simulator, verbose: int, output: IO):
    echo(
        "\n$FG_GREEN${DIM}Starting main loop on $BOLD${time}",
        time=datetime.now().isoformat(),
        file=output,
    )

    try:
        while True:
            now = time.time()

            if (
                now - config.last_update >= config.leaderboard_update_delay_seconds
                and config.leaderboard_update_delay_seconds > 0
            ):
                describe_command(
                    "update the leaderboard",
                    "Leaderboard updated",
                    simulator.subreddit,
                    verbose,
                    prefix="${FG_YELLOW}",
                    output=output,
                    callback=simulator.update_leaderboard,
                    on_success_update="last_update",
                    config=config,
                )

            if (
                now - config.last_comment >= config.comment_delay_seconds
                and config.comment_delay_seconds > 0
            ):
                describe_command(
                    "make a comment",
                    "Comment posted",
                    simulator.subreddit,
                    verbose,
                    prefix="${FG_GREEN}",
                    output=output,
                    callback=simulator.make_comment,
                    on_success_update="last_comment",
                    config=config,
                )

            if (
                now - config.last_submission >= config.submission_delay_seconds
                and config.submission_delay_seconds > 0
            ):
                describe_command(
                    "make a submission",
                    "Submission posted",
                    simulator.subreddit,
                    verbose,
                    prefix="${FG_BLUE}",
                    output=output,
                    callback=simulator.make_submission,
                    on_success_update="last_submission",
                    config=config,
                )

            if (
                now - config.last_vote >= config.voting_delay_seconds
                and config.voting_delay_seconds > 0
            ):
                describe_command(
                    "vote on a submission / comment",
                    "Voted",
                    simulator.subreddit,
                    verbose,
                    prefix="${FG_MAGENTA}",
                    output=output,
                    callback=simulator.make_vote,
                    on_success_update="last_vote",
                    config=config,
                )

            time.sleep(config.main_loop_delay_seconds)

    except KeyboardInterrupt:
        echo(
            "\n$FG_RED${DIM}Stopped main loop on $BOLD${time}",
            time=datetime.now().isoformat(),
            file=output,
        )

    except Exception as err:
        echo(
            "\n$FG_RED${BOLD}ERROR: $NORMAL${err}\n",
            err=repr(err),
            file=output,
            max_length=-1,
        )
        for line in traceback.format_exc().splitlines():
            echo("$DIM$FG_RED${line}", line=line, file=output, max_length=-1)


def unexpected_command(ctx, output: IO) -> None:
    echo(
        "$FG_RED${BOLD}ERROR:$NORMAL Expected at least one of "
        "the options: $BOLD$FG_YELLOW"
        + "$NORMAL, $BOLD$FG_YELLOW".join(
            ["--run", "--create-db", "--drop_db", "--show_db"]
        ),
        file=output,
    )
    echo(ctx.get_help(), file=output)
    ctx.exit(1)


def create_config_from_example(ctx, config_file: str, verbose: int, output: IO) -> None:
    cwd = Path(".").resolve()
    config = Path(config_file)
    example = config.with_name("subreddit_simulator.cfg.example")

    if verbose > 0:
        echo(
            "${FG_YELLOW}Using template: $BOLD${example}",
            file=output,
            example=str(example.relative_to(cwd)),
        )

    echo(
        "$FG_YELLOW${DIM}Creating: $BOLD${config}",
        config=str(config.relative_to(cwd)),
        file=output,
    )

    with config.open("w") as c, example.open("r") as e:
        for line in e.readlines():
            c.write(line)

    echo(
        "$BOLD$FG_GREEN\nIMPORTANT:${NORMAL} "
        "Edit the created config file and ensure it's configured correctly!",
        file=output,
        max_length=-1,
    )
    ctx.exit(0)


def setup_logging(verbose: int, output: IO) -> None:
    level = logging.ERROR
    if verbose >= 3:
        level = logging.DEBUG
    elif verbose >= 2:
        level = logging.INFO
    elif verbose >= 1:
        level = logging.WARNING

    handler = ColorStreamHandler(output)
    handler.setLevel(level)
    logging.basicConfig(level=level, handlers=[handler])
    logging.getLogger("sqlalchemy.engine").setLevel(level)
    logging.getLogger("praw").setLevel(level)
    logging.getLogger("prawcore").setLevel(level)


def load_config_file(config_file: str, verbose: int, output: IO) -> Config:
    config = Path(config_file).resolve().relative_to(Path(".").cwd())
    file_config = Config.from_file(config_file)
    if verbose > 0:
        echo(
            "${FG_YELLOW}Using config file: $BOLD${config}",
            config=str(config),
            file=output,
            max_length=-1,
        )
    return file_config


def update_db_config(file_config: Config) -> Tuple[Config, Engine]:
    engine = Engine.from_config(file_config)
    db = engine.create_session()
    db_config = Config.from_db(db)
    db_config.merge(
        file_config,
        exclude=["last_comment", "last_submission", "last_vote", "last_update"],
    )
    db_config.update_db(db)
    return db_config, engine


def drop_database(file_config: Config, verbose: int, output: IO):
    engine = Engine.from_config(file_config)

    echo("${FG_RED}Dropping database...", file=output)
    Base.metadata.drop_all(engine.create())


def create_database(file_config: Config, verbose: int, output: IO):
    engine = Engine.from_config(file_config)

    echo("${FG_GREEN}Creating database...", file=output)
    Base.metadata.create_all(engine.create())


def show_database(engine: Engine, output: IO):
    echo("${FG_YELLOW}Showing database...", nl=False, file=output)
    bound = engine.create()
    Base.metadata.reflect(bind=bound)

    tables = Base.metadata.sorted_tables
    echo(
        "$FG_YELLOW$BOLD${num_tables}$NORMAL tables exist.",
        file=output,
        num_tables=len(tables),
    )
    for table in tables:
        rows = list(map(dict, bound.execute(table.select())))
        num_rows = len(rows)
        echo(
            "\n Table $BOLD$FG_YELLOW${table}$NORMAL (${num_rows} rows):",
            file=output,
            table=table.name,
            num_rows=num_rows,
        )
        separator(char="=", prefix="+", file=output)

        for i, row in enumerate(rows):
            for field, value in row.items():
                display = repr(value)
                if isinstance(value, datetime):
                    display = value.isoformat()
                echo(
                    "|$FG_BLUE${name}$FG_RESET = $FG_GREEN${display}",
                    file=output,
                    name=f"{field:<20}",
                    display=f"{display:<35}",
                )

            separator(char="-", prefix=f"+(#{i+1}/{num_rows})", file=output)


@click.command()
@click.help_option("-h", "--help")
@click.version_option(__version__, "-V", "--version")
@click.option("--show-accounts", "-a", is_flag=True, help="Show accounts table.")
@click.option("--run", "-r", is_flag=True, help="Run main loop.")
@click.option("--create-db", "-C", is_flag=True, help="Create the database schema.")
@click.option("--drop-db", "-D", is_flag=True, help="Drop the database schema")
@click.option(
    "--config-file",
    "-f",
    type=click.Path(exists=False, dir_okay=False, resolve_path=True, readable=True),
    default=str(Path(__file__).with_name(DEFAULT_SUBREDDIT_SIMULATOR_CONFIG)),
    metavar="PATH",
    help="Specify configuration file (default: {}).".format(
        DEFAULT_SUBREDDIT_SIMULATOR_CONFIG
    ),
)
@click.option(
    "--output",
    "-o",
    type=click.File(mode="a"),
    default="-",
    required=False,
    help="Log all output to a specified file (default:- i.e. stdout).",
)
@click.option("--show-db", "-S", is_flag=True, help="Show the database contents.")
@click.option(
    "--verbose",
    "-v",
    default=0,
    type=click.IntRange(0, 3),
    count=True,
    help="Increase output verbosity (supports -v to -vvv).",
)
@click.pass_context
def main(
    ctx, run, create_db, drop_db, show_db, show_accounts, config_file, verbose, output
):
    """Subreddit simulator CLI."""

    if not any([run, create_db, drop_db, show_db]):
        unexpected_command(ctx, output)

    if not Path(config_file).exists():
        create_config_from_example(ctx, config_file, verbose, output)

    setup_logging(verbose, output)

    file_config = load_config_file(config_file, verbose, output)

    if drop_db:
        drop_database(file_config, verbose, output)

    if create_db:
        create_database(file_config, verbose, output)

    db_config, engine = update_db_config(file_config)

    if show_db:
        show_database(engine, output)

    if run:
        simulator = Simulator(config=db_config, engine=engine, output=output)
        if show_accounts:
            simulator.print_accounts_table()

        run_main_loop(db_config, simulator, verbose, output)

    ctx.exit(0)
