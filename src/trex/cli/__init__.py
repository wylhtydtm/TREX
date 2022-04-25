import logging

from trex.utils import NiceFormatter
from pathlib import Path
import shutil

logger = logging.getLogger(__name__)


class CommandLineError(Exception):
    pass


def setup_logging(debug: bool) -> None:
    """
    Set up logging. If debug is True, then DEBUG level messages are printed.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(NiceFormatter())

    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)