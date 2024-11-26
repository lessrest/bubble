from rdflib import Graph, Namespace

NT = Namespace("https://node.town/2024/")
SWA = Namespace("https://swa.sh/2024/")
JSON = Namespace("https://node.town/2024/json/#")
AS = Namespace("http://www.w3.org/ns/activitystreams#")
UUID = Namespace("urn:uuid:")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")


def bind_prefixes(g: Graph):
    g.bind("swa", SWA)
    g.bind("nt", NT)
    g.bind("as", AS)
