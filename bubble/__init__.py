# hmm

from . import (
    boot,
    cred,
    chat,
    mind,
    mint,
    prfx,
    repo,
    slop,
    util,
    vars,
    wiki,
    stat,
    caps,
    json,
    macs,
    main,
)

import rdflib.term

from pydantic import SecretStr
import logging

logger = logging.getLogger(__name__)


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
    "util",
    "vars",
    "wiki",
    "stat",
    "caps",
    "json",
    "macs",
    "main",
]
