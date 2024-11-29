import pytest
from rdflib import Graph, URIRef

from bubble import vars
from bubble.prfx import NT, AI
from bubble.cred import (
    get_service_credential,
)


from bubble.util import NoResultsFoundError, MultipleResultsError


@pytest.fixture
def graph():
    """Create a test graph with credential data"""
    with vars.graph.bind(Graph()) as g:
        g.bind("nt", NT)
        g.bind("ai", AI)
        yield g


async def test_get_service_credential_success(graph):
    """Test successful credential retrieval"""
    turtle_data = """
    @prefix nt: <https://node.town/2024/> .
    @prefix ai: <https://node.town/2024/ai/#> .

    [] a nt:ServiceAccount ;
        nt:forService ai:AnthropicService ;
        nt:hasPart [ a nt:BearerToken ;
                     nt:hasValue "test-api-key" ] .
    """

    graph.parse(data=turtle_data, format="turtle")

    credential = await get_service_credential(URIRef(AI.AnthropicService))
    assert credential == "test-api-key"


async def test_get_service_credential_missing(graph):
    """Test handling of missing credentials"""
    with pytest.raises(NoResultsFoundError):
        await get_service_credential(URIRef(AI.AnthropicService))


async def test_multiple_credentials(graph):
    """Test handling of multiple credentials"""
    turtle_data = """
    @prefix nt: <https://node.town/2024/> .
    @prefix ai: <https://node.town/2024/ai/#> .

    [] a nt:ServiceAccount ;
        nt:forService ai:AnthropicService ;
        nt:hasPart [ a nt:BearerToken ;
                     nt:hasValue "test-api-key" ] .

    [] a nt:ServiceAccount ;
        nt:forService ai:AnthropicService ;
        nt:hasPart [ a nt:BearerToken ;
                     nt:hasValue "test-api-key-2" ] .
    """
    graph.parse(data=turtle_data, format="turtle")
    with pytest.raises(MultipleResultsError):
        await get_service_credential(URIRef(AI.AnthropicService))
