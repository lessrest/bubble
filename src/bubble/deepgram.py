import os

from datetime import UTC, datetime

from swash import mint
import trio

from rdflib import XSD, Graph, URIRef, Literal, Namespace
from trio_websocket import WebSocketConnection

from swash.prfx import NT
from swash.util import S, add, new, is_a, get_single_object
from bubble.talk import (
    DeepgramParams,
    DeepgramMessage,
    using_deepgram_live_session,
)
from bubble.town import (
    ServerActor,
    get_site,
    send,
    spawn,
    logger,
    receive,
    in_request_graph,
    this,
    with_new_transaction,
    with_transient_graph,
)

Deepgram = Namespace("https://node.town/2024/deepgram/#")


async def deepgram_results_actor():
    while True:
        await trio.sleep(1)


async def receive_results(client: WebSocketConnection, results: URIRef):
    while True:
        result = await client.get_message()
        message = DeepgramMessage.model_validate_json(result)
        if message.channel.alternatives[0].transcript:
            logger.info(
                "Deepgram message",
                message=message,
            )
            with with_transient_graph() as id:
                new(
                    Deepgram.Result,
                    {
                        Deepgram.transcript: message.channel.alternatives[
                            0
                        ].transcript
                    },
                    id,
                )
                await send(results)


def chunk_data(id: S) -> bytes:
    chunk = get_single_object(id, NT.bytes)
    data = chunk.toPython()
    assert isinstance(data, bytes)
    return data


async def deepgram_session(results: URIRef):
    # Wait for first chunk before starting session
    with in_request_graph(await receive()) as msg:
        first_chunk = chunk_data(msg)
        async with using_deepgram_live_session(DeepgramParams()) as client:
            async with trio.open_nursery() as nursery:
                await spawn(nursery, receive_results, client, results)
                await client.send_message(first_chunk)
                while True:
                    with in_request_graph(await receive()) as msg:
                        chunk = chunk_data(msg)
                        await client.send_message(chunk)


class DeepgramClientActor(ServerActor[str]):
    def __init__(self, name: str):
        super().__init__(os.environ["DEEPGRAM_API_KEY"], name=name)

    async def init(self):
        await super().init()
        create_affordance_button(this())

    async def handle(self, nursery: trio.Nursery, graph: Graph) -> Graph:
        request_id = graph.identifier
        with with_new_transaction(graph) as result:
            add(result.identifier, {NT.isResponseTo: request_id})
            if is_a(request_id, Deepgram.Start):
                results = await spawn(nursery, deepgram_results_actor)
                session = await spawn(nursery, deepgram_session, results)

                new(
                    Deepgram.Session,
                    {
                        NT.created: Literal(
                            datetime.now(UTC).isoformat(),
                            datatype=XSD.dateTime,
                        ),
                        NT.has: [
                            new(
                                NT.UploadEndpoint,
                                {
                                    NT.method: NT.WebSocket,
                                    NT.accepts: NT.AudioData,
                                    NT.url: str(session).replace(
                                        "https://", "wss://"
                                    )
                                    + "/upload",
                                },
                                session,
                            ),
                            new(
                                NT.EventStream,
                                {
                                    NT.method: NT.GET,
                                    NT.produces: Deepgram.TranscriptionHypothesis,
                                },
                                results,
                            ),
                        ],
                    },
                    result.identifier,
                )

            return result


def create_affordance_button(deepgram_client: URIRef):
    with with_new_transaction():
        new(
            URIRef("https://node.town/2024/deepgram/#Client"),
            {
                NT.affordance: [
                    new(
                        NT.Button,
                        {
                            NT.label: Literal("Start", "en"),
                            NT.message: URIRef(
                                "https://node.town/2024/deepgram/#Start"
                            ),
                            NT.target: deepgram_client,
                        },
                        mint.fresh_uri(get_site()),
                    )
                ]
            },
            deepgram_client,
        )
