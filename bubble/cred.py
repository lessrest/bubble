from bubble.util import (
    select_one_row,
)
from rdflib import URIRef
from bubble.prfx import AI


class CredentialError(Exception):
    pass


class MissingCredentialError(CredentialError):
    pass


class TooManyCredentialsError(CredentialError):
    pass


async def get_service_credential(service: URIRef) -> str:
    query = (
        """
        SELECT ?value
        WHERE {
            ?account a nt:ServiceAccount ;
                nt:forService <%s> ;
                nt:hasPart [ a nt:BearerToken ;
                            nt:hasValue ?value ] .
        }
    """
        % service
    )
    return select_one_row(query)[0].toPython()


async def get_anthropic_credential() -> str:
    return await get_service_credential(URIRef(AI.AnthropicService))
