from datetime import UTC, datetime

from rdflib import RDF, Graph, Literal

from swash.prfx import NT
from swash.util import new
from bubble.Vat import create_graph
from bubble.town import (
    ServerActor,
    this,
    txgraph,
)


class UptimeActor(ServerActor[datetime]):
    """Actor that tracks and reports uptime since its creation."""

    async def init(self):
        self.state = datetime.now(UTC)
        async with txgraph():
            new(NT.UptimeActor, {}, this())

    async def handle(self, nursery, graph: Graph) -> Graph:
        request_id = graph.identifier
        uptime = datetime.now(UTC) - self.state

        g = create_graph()
        g.add((g.identifier, RDF.type, NT.UptimeResponse))
        g.add((g.identifier, NT.uptime, Literal(str(uptime))))
        g.add((g.identifier, NT.isResponseTo, request_id))

        # If there's a replyTo field, add it to response
        for reply_to in graph.objects(request_id, NT.replyTo):
            g.add((g.identifier, NT.replyTo, reply_to))

        return g
