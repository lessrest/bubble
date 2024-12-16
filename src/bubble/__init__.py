# hmm

from swash import prfx

from . import (
    boot,
    cred,
    chat,
    slop,
    stat,
)

import rdflib.term

from pydantic import SecretStr

rdflib.term.bind(prfx.NT.SecretToken, SecretStr)

__all__ = [
    "boot",
    "cred",
    "chat",
    "slop",
    "stat",
]
