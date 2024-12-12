import os

from typing import Optional
from datetime import UTC, datetime
from collections import defaultdict
from urllib.parse import urlencode

import trio
import structlog

from rdflib import BNode, Graph, URIRef, Literal, IdentifiedNode
from trio_websocket import WebSocketConnection, open_websocket_url
from rdflib.namespace import PROV, TIME

from swash.desc import has, has_type, resource
from swash.mint import fresh_iri, fresh_uri
from swash.prfx import NT, VOX, Deepgram
from swash.util import (
    add,
    new,
    is_a,
    decimal,
    make_list,
    get_single_object,
)
from swash.vars import in_graph
from bubble.time import make_instant, make_duration, make_interval
from bubble.town import (
    ServerActor,
    send,
    this,
    spawn,
    receive,
    txgraph,
    get_base,
    in_request_graph,
    with_transient_graph,
)
from bubble.deepgram.json import Word, DeepgramParams, DeepgramMessage

logger = structlog.get_logger()


def using_deepgram_live_session(params: DeepgramParams):
    """Create a websocket connection to Deepgram's streaming API"""
    # Filter out None values and create the query string
    query_params = params.model_dump(exclude_none=True)
    url = f"wss://api.deepgram.com/v1/listen?{urlencode(query_params)}"

    logger.info("Connecting to Deepgram", url=url)
    headers = [("Authorization", f"Token {os.environ['DEEPGRAM_API_KEY']}")]
    return open_websocket_url(url, extra_headers=headers)


async def deepgram_results_actor():
    while True:
        await trio.sleep(1)


async def deepgram_transcription_receiver():
    """Actor that processes Deepgram messages into RDF graphs using the vox vocabulary"""

    stream = BNode()  # should use a real audio stream
    speakers = defaultdict(lambda: new(PROV.Person))

    def speaker(i: Optional[int]) -> Optional[IdentifiedNode]:
        if i is None:
            return None
        return speakers[i]

    process = new(
        VOX.TranscriptionProcess,
        {
            PROV.startedAtTime: datetime.now(UTC),
            PROV.wasAssociatedWith: VOX.Deepgram,
        },
    )

    def message_recognition(message: DeepgramMessage):
        def word_segment(word: Word):
            return new(
                VOX.Recognition,
                {
                    VOX.hasTextWithoutPunctuation: word.word,
                    VOX.hasText: word.punctuated_word,
                    VOX.hasConfidence: decimal(word.confidence),
                    TIME.hasBeginning: make_instant(stream, word.start),
                    TIME.hasDuration: make_duration(word.end - word.start),
                    PROV.wasAttributedTo: speaker(word.speaker),
                },
            )

        alternative = message.channel.alternatives[0]

        return new(
            VOX.Recognition if message.is_final else VOX.DraftRecognition,
            {
                PROV.generatedAtTime: datetime.now(UTC),
                PROV.wasDerivedFrom: stream,
                PROV.wasGeneratedBy: process,
                VOX.hasTime: make_interval(
                    stream, message.start, message.duration
                ),
                VOX.hasPunctuatedText: alternative.transcript,
                VOX.hasConfidence: decimal(alternative.confidence),
                VOX.hasSubdivision: make_list(
                    list(word_segment(word) for word in alternative.words),
                    subject=None,
                ),
            },
        )

    interim = None

    while True:
        message, payload = await receive_event()
        async with txgraph():
            recognition = message_recognition(payload)
            if interim is not None:
                add(recognition, {PROV.wasRevisionOf: interim})
                add(interim, {PROV.wasInvalidatedBy: process})
        with in_graph(message):
            add(message.identifier, {PROV.wasUsedBy: process})


async def receive_event():
    message = await receive()
    payload = DeepgramMessage.model_validate_json(
        get_single_object(message.identifier, NT.json, message)
    )
    return message, payload


def chunk_data(graph: Graph) -> bytes:
    """Extract audio chunk data from a message graph."""
    chunk = get_single_object(graph.identifier, NT.bytes)
    data = chunk.toPython()
    assert isinstance(data, bytes)
    return data


async def deepgram_session(results: URIRef):
    # Wait for first chunk before starting session
    msg = await receive()
    with in_request_graph(msg) as request_graph:
        first_chunk = chunk_data(request_graph)
        async with using_deepgram_live_session(DeepgramParams()) as client:
            async with trio.open_nursery() as nursery:
                await spawn(nursery, receive_results, client, results)
                await client.send_message(first_chunk)
                while True:
                    msg = await receive()
                    with in_request_graph(msg) as request_graph:
                        chunk = chunk_data(request_graph)
                        await client.send_message(chunk)


class DeepgramClientActor(ServerActor[str]):
    def __init__(self, name: str):
        super().__init__(os.environ["DEEPGRAM_API_KEY"], name=name)

    async def init(self):
        await super().init()
        async with txgraph():
            create_affordance_button(this())

    async def handle(self, nursery: trio.Nursery, graph: Graph) -> Graph:
        logger.info("Deepgram client actor handling message", graph=graph)
        request_id = graph.identifier
        async with txgraph(graph) as result:
            result.add((result.identifier, NT.isResponseTo, request_id))
            if is_a(request_id, Deepgram.Start):
                root = get_base()

                logger.info("Starting new Deepgram session")
                results = await spawn(nursery, deepgram_results_actor)

                logger.info("Spawned results actor", results=results)
                session = await spawn(nursery, deepgram_session, results)

                logger.info("Spawned session actor", session=session)
                assert isinstance(result.identifier, URIRef)

                with resource(
                    fresh_uri(graph), a=NT.UploadEndpoint
                ) as endpoint:
                    add(root, {NT.has: session})
                    add(root, {NT.has: results})
                    add(root, {NT.has: endpoint.node})
                    has(NT.method, NT.WebSocket)
                    has(NT.accepts, NT.AudioData)
                    ws_url = (
                        str(session).replace("https://", "wss://")
                        + "/upload"
                    )
                    logger.info("WebSocket URL", url=ws_url)
                    has(NT.url, ws_url)

            logger.info("Returning result", result=result)
            return result


def create_affordance_button(deepgram_client: URIRef):
    with resource(deepgram_client, Deepgram.Client) as client:
        with has(NT.affordance, fresh_iri()):
            has_type(NT.Button)
            has(NT.label, Literal("Start", "en"))
            has(NT.message, URIRef(Deepgram.Start))
            has(NT.target, deepgram_client)
        return client.node


async def receive_results(client: WebSocketConnection, results: URIRef):
    async with trio.open_nursery() as nursery:
        transcription_receiver = await spawn(
            nursery,
            deepgram_transcription_receiver,
            name="Deepgram transcription receiver",
        )

        while True:
            result = await client.get_message()
            message = DeepgramMessage.model_validate_json(result)

            if message.channel.alternatives[0].transcript:
                logger.info(
                    "Deepgram message",
                    message=message,
                )

                with with_transient_graph() as g:
                    add(
                        URIRef(g.identifier),
                        {
                            NT.json: Literal(result),
                            NT.replyTo: results,
                        },
                    )
                    await send(transcription_receiver)
