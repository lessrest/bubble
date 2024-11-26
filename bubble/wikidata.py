from collections import defaultdict
from io import StringIO
import httpx
import rdflib
import rich
import trio
from typing import Dict, List, Optional, Union
from urllib.parse import urlencode
from rdflib import Graph, IdentifiedNode, URIRef, Literal, Namespace, BNode
from rdflib.namespace import RDF, RDFS, XSD
from rdflib.query import ResultRow

from bubble.n3_utils import (
    get_objects,
    get_single_object,
    get_subjects,
    print_n3,
)

# Define some useful Wikidata namespaces
WD = Namespace("http://www.wikidata.org/entity/")
WDT = Namespace("http://www.wikidata.org/prop/direct/")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
SCHEMA = Namespace("http://schema.org/")


class WikidataSPARQLClient:
    """A simple async SPARQL client for Wikidata that works with RDFLib."""

    def __init__(self, endpoint: str = "https://query.wikidata.org/sparql"):
        self.endpoint = endpoint
        self.headers = {
            "Accept": "application/sparql-results+json,application/rdf+xml",
            "User-Agent": "RDFLibWikidataSPARQLClient/1.0",
        }

    async def query(self, sparql_query: str) -> Graph:
        params = {"query": sparql_query, "format": "json"}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.endpoint, params=params, headers=self.headers
            )
            response.raise_for_status()

            results = rdflib.query.Result.parse(
                StringIO(response.text), format="json"
            )

            g = Graph(bind_namespaces="core")
            for triple in results:
                assert isinstance(triple, ResultRow)
                s, p, o, c = triple

                assert c is None
                assert isinstance(p, IdentifiedNode)

                g.add((s, p, o))

            return g


async def query_wikidata(query: str) -> Graph:
    """Helper function to execute a SPARQL query and bind common namespaces."""
    client = WikidataSPARQLClient()
    g = await client.query(query)

    # Bind common namespaces for easier serialization/querying
    g.bind("wd", WD)
    g.bind("wdt", WDT)
    g.bind("rdfs", RDFS)
    g.bind("schema", SCHEMA)

    return g


async def get_un_countries_graph() -> Graph:
    """Get UN member states as an RDFLib graph."""
    query = """
    CONSTRUCT {
        ?country a schema:Country ;
                rdfs:label ?countryLabel ;
                schema:name ?countryLabel ;
                schema:capital ?capital ;
                schema:continent ?continent .
        ?capital rdfs:label ?capitalLabel ;
                schema:name ?capitalLabel .
        ?continent rdfs:label ?continentLabel .
    }
    WHERE {
        ?country wdt:P31 wd:Q3624078 .  # Instance of: sovereign state
        ?country wdt:P463 wd:Q1065 .     # Member of: United Nations
        OPTIONAL { ?country wdt:P36 ?capital . }
        OPTIONAL { ?country wdt:P30 ?continent . }
        
        SERVICE wikibase:label { 
            bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en" .
            ?country rdfs:label ?countryLabel .
            ?capital rdfs:label ?capitalLabel .
            ?continent rdfs:label ?continentLabel .
        }
    }
    """
    return await query_wikidata(query)


async def get_continents_graph() -> Graph:
    """Get continents as an RDFLib graph."""
    # Q5107 - continent
    query = """
    CONSTRUCT {
        ?continent a schema:Continent ;
                rdfs:label ?continentLabel .
    }
    WHERE {
        ?continent wdt:P31 wd:Q5107 .
        SERVICE wikibase:label { 
            bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en" .
            ?continent rdfs:label ?continentLabel .
        }
    }
    """
    return await query_wikidata(query)


async def demonstrate_graph_usage():
    """Show how to work with the resulting graph."""
    g = await get_un_countries_graph()

    print(f"Graph contains {len(g)} triples")
    print("\nFirst 5 countries and their capitals:")

    results = g.query(
        """
        SELECT DISTINCT ?country ?name ?continent
        WHERE {
            ?country schema:name ?name ;
                     schema:continent ?continent .
        }
        """
    )

    continents = defaultdict(list)
    for row in results:
        assert isinstance(row, ResultRow)
        continents[row.continent].append(row.country)

    rich.print(continents)


async def main():
    await demonstrate_graph_usage()


if __name__ == "__main__":
    trio.run(main)
