from pydantic import SecretStr
from swash.util import (
    select_one_row,
)
from rdflib import Literal, URIRef
from swash.prfx import AI


class CredentialError(Exception):
    pass


class MissingCredentialError(CredentialError):
    pass


class TooManyCredentialsError(CredentialError):
    pass


class InsecureCredentialError(CredentialError):
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
        if not isinstance(value.value, SecretStr):
            raise InsecureCredentialError(
                f"credential for {service} is not a nt:SecretToken"
            )
        return value.value
    else:
        raise CredentialError(f"Unexpected credential type: {value}")


async def get_anthropic_credential() -> SecretStr:
    return await get_service_credential(URIRef(AI.AnthropicService))
