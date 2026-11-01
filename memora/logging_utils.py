"""Local rotating logs containing event types, never document contents."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(data_dir: Path):
    folder = data_dir / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "memora.log", maxBytes=256_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger("memora")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    # pypdf warnings can include PDF internals; keep those out of local logs.
    logging.getLogger("pypdf").addHandler(logging.NullHandler())
    logging.getLogger("pypdf").propagate = False
    return handler
