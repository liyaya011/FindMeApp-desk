import logging
import sys

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=_FORMAT)


def getLogger(name: str) -> logging.Logger:
    return logging.getLogger(name)
