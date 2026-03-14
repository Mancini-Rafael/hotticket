import logging
from pathlib import Path


def init(debug: bool = False) -> None:
    log_dir = Path.home() / ".hotticket"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "hotticket.log"

    level = logging.DEBUG if debug else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    logging.basicConfig(
        level=level,
        format=fmt,
        force=True,  # re-configure if already initialised
        handlers=[
            logging.StreamHandler(),  # stderr
            logging.FileHandler(log_file),
        ],
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
