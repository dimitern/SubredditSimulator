import attr
import click

from . import __version__


@attr.s
class Context:
    config: str = attr.ib()
    verbose: int = attr.ib()
    create_db: bool = attr.ib()
    drop_db: bool = attr.ib()
    show_db: bool = attr.ib()
    create_db: bool = attr.ib()

pass_context = click.make_pass_decorator(Context, ensure=True)

@click.group()
@click.help_option("-h", "--help")
@click.version_option(__version__, "-v", "--version")
@click.option("--create-db", "-C", is_flag=True, help="Create the database schema.")
@click.option("--drop-db", "-D", is_flag=True, help="Drop the database schema")
@click.option(
    "--config",
    "-f",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True, readable=True)
    default="subreddit_simulator.cfg",
    metavar="PATH",
    help="Specify configuration file.",
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
@pass_context
def main(ctx, ):
    """Subreddit simulator CLI."""
    pass


@main.command()
def cmd(create_db, drop_db, show_db, config, verbose):
    print(config, verbose)
    if create_db:
        click.secho("Creating database...", fg="green")
    if drop_db:
        click.secho("Creating database...", fg="red")
    if show_db:
        click.secho("Showing database...", fg="yellow")
