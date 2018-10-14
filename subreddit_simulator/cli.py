from pathlib import Path

import click

from . import __version__


def create_config_from_example(config, verbose, output):
    example = Path(config).with_name("subreddit_simulator.cfg.example")

    if verbose > 0:
        click.secho(
            f"Creating config file {config!r} from {example!r}.\n",
            fg="yellow",
            file=output,
        )

    with Path(config).open("w") as c, example.open("r") as e:
        for line in e.readlines():
            c.write(line)

    click.secho(
        f"Edit the created {config!r} and ensure it's configured correctly!",
        fg="green",
        file=output,
    )


def drop_database(config, verbose, output):
    click.secho("Dropping database...", fg="red", file=output)


def create_database(config, verbose, output):
    click.secho("Creating database...", fg="green", file=output)


def show_database(config, verbose, output):
    click.secho("Showing database...", fg="yellow", file=output)


@click.command()
@click.help_option("-h", "--help")
@click.version_option(__version__, "-v", "--version")
@click.option("--create-db", "-C", is_flag=True, help="Create the database schema.")
@click.option("--drop-db", "-D", is_flag=True, help="Drop the database schema")
@click.option(
    "--config",
    "-f",
    type=click.Path(exists=False, dir_okay=False, resolve_path=True, readable=True),
    default=str(Path(__file__).with_name("subreddit_simulator.cfg")),
    metavar="PATH",
    help="Specify configuration file.",
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
def main(create_db, drop_db, show_db, config, verbose, output):
    """Subreddit simulator CLI."""

    if not Path(config).exists():
        create_config_from_example(config, verbose, output)
        return

    if verbose > 0:
        click.secho(f"Using config file: {config}", fg="yellow", file=output)

    if drop_db:
        drop_database(config, verbose, output)

    if create_db:
        create_database(config, verbose, output)

    if show_db:
        show_database(config, verbose, output)
