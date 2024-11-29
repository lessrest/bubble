from pydantic import SecretStr
from bubble.util import (
    select_one_row,
)
from rdflib import Literal, URIRef
from bubble.prfx import AI


class CredentialError(Exception):
    pass


class MissingCredentialError(CredentialError):
    pass


class TooManyCredentialsError(CredentialError):
    pass


async def get_service_credential(service: URIRef) -> SecretStr:
    query = """
        SELECT ?value
        WHERE {
            ?account a nt:ServiceAccount ;
                nt:forService ?service ;
                nt:hasPart [ a nt:BearerToken ;
                            nt:hasValue ?value ] .
        }
    """
    value = select_one_row(query, {"service": service})[0]
    if isinstance(value, Literal):
        assert isinstance(value.value, SecretStr)
        return value.value
    else:
        raise ValueError(f"Unexpected credential type: {value}")


async def get_anthropic_credential() -> SecretStr:
    return await get_service_credential(URIRef(AI.AnthropicService))
