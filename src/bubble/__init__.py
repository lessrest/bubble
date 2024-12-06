# hmm

from swash import prfx, mind, mint, vars

from . import (
    boot,
    cred,
    chat,
    repo,
    slop,
    wiki,
    main,
    http,
    stat,
)

import rdflib.term

from pydantic import SecretStr
import structlog

logger = structlog.get_logger()


rdflib.term.bind(prfx.NT.SecretToken, SecretStr)
logger.info("Bound SecretStr to https://node.town/2024/SecretToken")

__all__ = [
    "boot",
    "cred",
    "chat",
    "mind",
    "mint",
    "prfx",
    "repo",
    "slop",
    "vars",
    "wiki",
    "stat",
    "stat",
    "main",
    "http",
]
