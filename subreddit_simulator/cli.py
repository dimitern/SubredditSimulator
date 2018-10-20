import logging
from datetime import datetime
from pathlib import Path

import click

from . import __version__, config


def create_config_from_example(conf, verbose, output):
    example = Path(conf).with_name("subreddit_simulator.cfg.example")

    if verbose > 0:
        click.secho(
            "Using template: {}".format(click.style(str(example), bold=True)),
            fg="yellow",
            file=output,
        )

    click.secho(
        "Creating: {}".format(click.style(str(conf), bold=True)),
        fg="yellow",
        file=output,
    )

    with Path(conf).open("w") as c, example.open("r") as e:
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


def drop_database(file_config, verbose, output):
    config.CONFIG.merge(
        file_config,
        include=[
            "system",
            "username",
            "password",
            "host",
            "port",
            "database",
            "verbose",
        ],
    )

    from .database import engine
    from .models import Base

    click.secho("Dropping database...", fg="red", file=output)
    Base.metadata.drop_all(engine)


def create_database(file_config, verbose, output):
    config.CONFIG.merge(
        file_config,
        include=[
            "system",
            "username",
            "password",
            "host",
            "port",
            "database",
            "verbose",
        ],
    )

    from .database import engine
    from .models import Base

    click.secho("Creating database...", fg="green", file=output)
    Base.metadata.create_all(engine)


def show_database(output):
    from .database import engine
    from .models import Base

    click.secho("Showing database...", fg="yellow", nl=False, file=output)
    Base.metadata.reflect(bind=engine)

    tables = Base.metadata.sorted_tables
    click.echo(
        click.style(f"{len(tables)}", bold=True, fg="yellow")
        + click.style(" tables exist.\n", fg="yellow", bold=False),
        file=output,
    )
    for table in tables:
        click.echo(
            "\n Table " + click.style(f"{table.name} ", bold=True, fg="yellow"),
            nl=False,
            file=output,
        )
        rows = list(map(dict, engine.execute(table.select())))
        click.secho(f"({len(rows)} rows):\n", fg="yellow", nl=False, file=output)
        click.echo("+" + "=" * 83, file=output)

        for i, row in enumerate(rows):
            for field, value in row.items():
                click.echo("|", nl=False, file=output)
                click.secho(f"{field:<25}", fg="blue", nl=False, file=output)
                click.echo(" = ", nl=False, file=output)

                if isinstance(value, datetime):
                    value = value.isoformat()

                click.secho(f"{value!r:<35}", fg="green", file=output)

            click.echo(f"+(#{i+1})" + "-" * 78, file=output)


@click.command()
@click.help_option("-h", "--help")
@click.version_option(__version__, "-v", "--version")
@click.option("--run", "-r", is_flag=True, help="Run main loop.")
@click.option("--create-db", "-C", is_flag=True, help="Create the database schema.")
@click.option("--drop-db", "-D", is_flag=True, help="Drop the database schema")
@click.option(
    "--config-file",
    "-f",
    type=click.Path(exists=False, dir_okay=False, resolve_path=True, readable=True),
    default=str(Path(__file__).with_name(config.DEFAULT_SUBREDDIT_SIMULATOR_CONFIG)),
    metavar="PATH",
    help="Specify configuration file (default: {}).".format(
        config.DEFAULT_SUBREDDIT_SIMULATOR_CONFIG
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
def main(ctx, run, create_db, drop_db, show_db, config_file, verbose, output):
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

    if not Path(config_file).exists():
        create_config_from_example(config_file, verbose, output)
        ctx.exit(0)

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
    logging.getLogger("sqlalchemy.engine").setLevel(level)

    file_config = config.CONFIG.from_file(config_file)
    config.CONFIG.merge(file_config)

    if verbose > 0:
        click.secho(
            "Using config file: {}".format(
                click.style(str(config_file), fg="yellow", bold=True)
            ),
            fg="yellow",
            file=output,
        )

    if drop_db:
        drop_database(file_config, verbose, output)

    if create_db:
        create_database(file_config, verbose, output)

    from .database import engine, Session

    Session.configure(bind=engine)
    db = Session()

    db_config = config.CONFIG.from_db(db)
    db_config.merge(
        config.CONFIG,
        exclude=["last_comment", "last_submission", "last_vote", "last_update"],
    )
    config.CONFIG.update_db(db)

    if show_db:
        show_database(output)
