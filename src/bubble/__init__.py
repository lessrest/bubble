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

rdflib.term.bind(prfx.NT.SecretToken, SecretStr)

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
