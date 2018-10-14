import logging
from pathlib import Path

import click

from . import __version__
from .config import CONFIG, DEFAULT_SUBREDDIT_SIMULATOR_CONFIG


def create_config_from_example(config, verbose, output):
    example = Path(config).with_name("subreddit_simulator.cfg.example")

    if verbose > 0:
        click.secho(
            "Using template: {}".format(click.style(str(example), bold=True)),
            fg="yellow",
            file=output,
        )

    click.secho(
        "Creating: {}".format(click.style(str(config), bold=True)),
        fg="yellow",
        file=output,
    )

    with Path(config).open("w") as c, example.open("r") as e:
        for line in e.readlines():
            c.write(line)

    click.echo(
        "{}{}".format(
            click.style("\nIMPORTANT: ", bold=True, fg="green"),
            click.style(
                "Edit the created config file and ensure it's configured correctly!",
                fg="green",
            ),
        ),
        file=output,
    )


def drop_database(config, verbose, output):
    CONFIG.verbose = verbose
    CONFIG.merge(CONFIG.from_file(config), exclude=["verbose"])

    from .database import engine

    engine.echo = verbose > 1

    from .models import Base

    click.secho("Dropping database...", fg="red", file=output)
    Base.metadata.drop_all(engine)


def create_database(config, verbose, output):
    CONFIG.verbose = verbose
    CONFIG.merge(CONFIG.from_file(config), exclude=["verbose"])

    from .database import engine

    engine.echo = verbose > 1

    from .models import Base

    click.secho("Creating database...", fg="green", file=output)
    Base.metadata.create_all(engine)


def show_database(config, verbose, output):
    click.secho("Showing database...", fg="yellow", file=output)


@click.command()
@click.help_option("-h", "--help")
@click.version_option(__version__, "-v", "--version")
@click.option("--run", "-r", is_flag=True, help="Run main loop.")
@click.option("--create-db", "-C", is_flag=True, help="Create the database schema.")
@click.option("--drop-db", "-D", is_flag=True, help="Drop the database schema")
@click.option(
    "--config",
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
def main(ctx, run, create_db, drop_db, show_db, config, verbose, output):
    """Subreddit simulator CLI."""

    if not any([run, create_db, drop_db, show_db]):
        click.secho(
            click.style("ERROR: ", bold=True, fg="red")
            + click.style(
                "Expected at least one of the options: "
                + ", ".join(
                    map(
                        lambda o: click.style(o, bold=True, fg="red"),
                        ["--run", "--create-db", "--drop_db", "--show_db"],
                    )
                )
                + "\n",
                fg="red",
            ),
            file=output,
        )
        click.echo(ctx.get_help(), file=output)
        ctx.exit(1)

    if not Path(config).exists():
        create_config_from_example(config, verbose, output)
        ctx.exit(0)

    if verbose > 0:
        click.secho(
            "Using config file: {}".format(
                click.style(str(config), fg="yellow", bold=True)
            ),
            fg="yellow",
            file=output,
        )

    level = logging.ERROR
    if verbose >= 3:
        level = logging.DEBUG
    elif verbose >= 2:
        level = logging.INFO
    elif verbose >= 1:
        level = logging.WARNING

    handler = logging.StreamHandler(output)
    handler.setLevel(level)
    logging.basicConfig(level=level, handlers=[handler])

    if drop_db:
        drop_database(config, verbose, output)

    if create_db:
        create_database(config, verbose, output)

    if show_db:
        show_database(config, verbose, output)
