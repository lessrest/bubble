# hmm

import rdflib.term

from pydantic import SecretStr

from swash import prfx

from . import (
    cli,
    boot,
    chat,
    cred,
    slop,
    stat,
)

rdflib.term.bind(prfx.NT.SecretToken, SecretStr)

__all__ = [
    "boot",
    "cli",
    "cred",
    "chat",
    "slop",
    "stat",
]
