import logging
from logging.handlers import RotatingFileHandler

from launcher import paths

def setup_logging() -> logging.Logger:
    log_dir = paths.get_data_dir() / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "launcher.log"

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler = RotatingFileHandler(log_file, maxBytes=1024*1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(formatter)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)
    root_logger.addHandler(console)
    return root_logger