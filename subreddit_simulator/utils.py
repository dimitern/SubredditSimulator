from logging import Formatter, StreamHandler
from string import Template

import click
import colorama

COLOR_MAP = dict(
    RESET=colorama.Style.RESET_ALL,
    BOLD=colorama.Style.BRIGHT,
    DIM=colorama.Style.DIM,
    NORMAL=colorama.Style.NORMAL,
    FG_RESET=colorama.Fore.RESET,
    FG_BLACK=colorama.Fore.BLACK,
    FG_BLUE=colorama.Fore.BLUE,
    FG_CYAN=colorama.Fore.CYAN,
    FG_GREEN=colorama.Fore.GREEN,
    FG_MAGENTA=colorama.Fore.MAGENTA,
    FG_RED=colorama.Fore.RED,
    FG_WHITE=colorama.Fore.WHITE,
    FG_YELLOW=colorama.Fore.YELLOW,
    FG_LIGHTBLACK=colorama.Fore.LIGHTBLACK_EX,
    FG_LIGHTBLUE=colorama.Fore.LIGHTBLUE_EX,
    FG_LIGHTCYAN=colorama.Fore.LIGHTCYAN_EX,
    FG_LIGHTGREEN=colorama.Fore.LIGHTGREEN_EX,
    FG_LIGHTMAGENTA=colorama.Fore.LIGHTMAGENTA_EX,
    FG_LIGHTRED=colorama.Fore.LIGHTRED_EX,
    FG_LIGHTWHITE=colorama.Fore.LIGHTWHITE_EX,
    FG_LIGHTYELLOW=colorama.Fore.LIGHTYELLOW_EX,
    BG_RESET=colorama.Back.RESET,
    BG_BLACK=colorama.Back.BLACK,
    BG_BLUE=colorama.Back.BLUE,
    BG_CYAN=colorama.Back.CYAN,
    BG_GREEN=colorama.Back.GREEN,
    BG_MAGENTA=colorama.Back.MAGENTA,
    BG_RED=colorama.Back.RED,
    BG_WHITE=colorama.Back.WHITE,
    BG_YELLOW=colorama.Back.YELLOW,
    BG_LIGHTBLACK=colorama.Back.LIGHTBLACK_EX,
    BG_LIGHTBLUE=colorama.Back.LIGHTBLUE_EX,
    BG_LIGHTCYAN=colorama.Back.LIGHTCYAN_EX,
    BG_LIGHTGREEN=colorama.Back.LIGHTGREEN_EX,
    BG_LIGHTMAGENTA=colorama.Back.LIGHTMAGENTA_EX,
    BG_LIGHTRED=colorama.Back.LIGHTRED_EX,
    BG_LIGHTWHITE=colorama.Back.LIGHTWHITE_EX,
    BG_LIGHTYELLOW=colorama.Back.LIGHTYELLOW_EX,
)


def echo(
    text: str, *, template=None, nl=True, reset=True, file=None, max_length=80, **params
):
    template = template or Template(text)
    message = template.safe_substitute(COLOR_MAP, **params)
    if max_length > 0:
        message = message[:max_length]
    click.secho(message, nl=nl, file=file, reset=reset)


def separator(char: str = "-", prefix="", max_length=80, file=None):
    echo(prefix + char * max_length, max_length=max_length, file=file)


class ColorStreamHandler(StreamHandler):
    """A colorized output SteamHandler."""

    color_map = {
        "DEBUG": colorama.Fore.CYAN,
        "INFO": colorama.Fore.GREEN,
        "WARN": colorama.Fore.YELLOW,
        "WARNING": colorama.Fore.YELLOW,
        "ERROR": colorama.Fore.RED,
        "CRIT": colorama.Back.RED + colorama.Fore.WHITE,
        "CRITICAL": colorama.Back.RED + colorama.Fore.WHITE,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFormatter(Formatter("%(message)s"))

    def emit(self, record):
        try:
            echo(
                "$BOLD${code}${levelname}$NORMAL:$DIM${name}:$RESET${message}${term}",
                code=self.color_map[record.levelname],
                term=getattr(self, "terminator", "\n"),
                nl=False,
                file=self.stream,
                levelname=record.levelname,
                name=record.name,
                message=self.format(record),
                max_length=-1,
            )
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)
