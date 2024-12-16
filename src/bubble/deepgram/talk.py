"""
Real-time Audio Transcription with Semantic Grounding
==================================================

This code demonstrates a prototype of a real-time audio transcription system
that outputs semantically grounded RDF data. It uses the W3C PROV-O ontology
to represent the transcription process and its outputs, and the W3C Time
Ontology to anchor recognized speech in time.

The PROV-O ontology models the transcription process, tracking:

  * The transcription activity itself
  * Audio segments and transcript fragments as entities
  * How transcripts evolve from interim to final versions
  * Speakers (initially anonymous, with potential for later identity linking)

The Time Ontology provides temporal structure by defining:

  * A timeline as reference frame
  * Points and intervals in the audio stream
  * Temporal relationships between segments

The resulting RDF data can be queried, integrated, and extended for richer
downstream semantic applications. While this implementation is currently
rudimentary and not feature-complete, it outlines a scalable approach to
structuring real-time audio transcriptions within a semantic framework.
"""

import os

from typing import Optional
from datetime import UTC, datetime
from collections import defaultdict
from urllib.parse import urlencode

import trio
import structlog

from rdflib import XSD, Graph, URIRef, Literal, IdentifiedNode
from trio_websocket import WebSocketConnection, open_websocket_url, Endpoint
from rdflib.namespace import PROV, TIME

from swash.prfx import NT, TALK, Deepgram
from swash.util import (
    add,
    blank,
    new,
    is_a,
    decimal,
    make_list,
    get_single_object,
)
from swash.vars import in_graph
from bubble.mesh import (
    ServerActor,
    get_base,
    receive,
    send,
    spawn,
    this,
    with_transient_graph,
)
from bubble.time import make_instant, make_duration, make_interval
from bubble.mesh import (
    txgraph,
)
from bubble.deepgram.json import Word, DeepgramParams, DeepgramMessage

logger = structlog.get_logger()


def using_deepgram_live_session(params: DeepgramParams):
    """Create a websocket connection to Deepgram's streaming API"""
    query_params = params.model_dump(exclude_none=True)
    # lowercase the boolean values
    query_params = {
        k: str(v).lower() if isinstance(v, bool) else v
        for k, v in query_params.items()
    }
    url = f"wss://api.deepgram.com/v1/listen?{urlencode(query_params)}"

    logger.info("Connecting to Deepgram", url=url)
    headers = [("Authorization", f"Token {os.environ['DEEPGRAM_API_KEY']}")]
    return open_websocket_url(url, extra_headers=headers)


async def deepgram_results_actor():
    while True:
        await trio.sleep(1)


async def deepgram_transcription_receiver(process: URIRef, stream: URIRef):
    """Actor that processes Deepgram messages into RDF graphs using the TALK vocabulary"""

    speakers = defaultdict(lambda: new(PROV.Person))

    def speaker(i: Optional[int]) -> Optional[IdentifiedNode]:
        if i is None:
            return None
        return speakers[i]

    process = new(
        TALK.TranscriptionProcess,
        {
            PROV.startedAtTime: datetime.now(UTC),
            PROV.wasAssociatedWith: TALK.Deepgram,
        },
    )

    def represent_transcript(message: Graph, payload: DeepgramMessage):
        def word_segment(word: Word):
            return new(
                TALK.Transcript,
                {
                    TALK.hasTextWithoutPunctuation: word.word,
                    TALK.hasText: word.punctuated_word,
                    TALK.hasConfidence: decimal(word.confidence),
                    TIME.hasBeginning: make_instant(stream, word.start),
                    TIME.hasDuration: make_duration(word.end - word.start),
                    PROV.wasAttributedTo: speaker(word.speaker),
                },
            )

        alternative = payload.channel.alternatives[0]

        return new(
            TALK.Transcript if payload.is_final else TALK.DraftTranscript,
            {
                PROV.generatedAtTime: datetime.now(UTC),
                PROV.wasDerivedFrom: message.identifier,
                PROV.wasGeneratedBy: process,
                TALK.hasTime: make_interval(
                    stream, payload.start, payload.duration
                ),
                TALK.hasPunctuatedText: alternative.transcript,
                TALK.hasConfidence: decimal(alternative.confidence),
                TALK.hasSubdivision: make_list(
                    list(word_segment(word) for word in alternative.words),
                    subject=None,
                ),
            },
        )

    interim = None

    while True:
        message, payload = await receive_event()
        async with txgraph() as g:
            transcript = represent_transcript(message, payload)
            if interim is not None:
                add(transcript, {PROV.wasRevisionOf: interim})
                add(interim, {PROV.wasInvalidatedBy: process})

            if payload.is_final:
                interim = None
            else:
                interim = transcript

        with in_graph(message):
            add(
                message.identifier,
                {
                    PROV.wasUsedBy: process,
                    NT.resultedIn: g,
                },
            )


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
    from bubble.town import in_request_graph  # Import where needed

    # Wait for first chunk before starting session
    msg = await receive()

    with in_request_graph(msg) as request_graph:
        first_chunk = chunk_data(request_graph)
        async with using_deepgram_live_session(DeepgramParams()) as client:
            assert isinstance(client.remote, Endpoint)
            assert isinstance(client.local, Endpoint)
            async with txgraph():
                socket = new(
                    NT.WebSocket,
                    {
                        NT.hasClientAddress: Literal(
                            client.remote.url, datatype=XSD.anyURI
                        ),
                        NT.hasServerAddress: Literal(
                            client.local.url, datatype=XSD.anyURI
                        ),
                    },
                )

                stream = new(
                    TALK.AudioStream,
                    {
                        PROV.wasDerivedFrom: socket,
                        PROV.startedAtTime: datetime.now(UTC),
                    },
                )
                session = new(
                    TALK.LiveTranscriptionProcess,
                    {
                        PROV.wasAssociatedWith: TALK.Deepgram,
                        PROV.startedAtTime: datetime.now(UTC),
                        PROV.used: stream,
                    },
                )
            async with trio.open_nursery() as nursery:
                await spawn(
                    nursery,
                    receive_results,
                    stream,
                    session,
                    client,
                    results,
                )
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

                endpoint = blank(
                    NT.UploadEndpoint,
                    {
                        NT.method: NT.WebSocket,
                        NT.accepts: NT.AudioData,
                    },
                )
                add(root, {NT.has: session})
                add(root, {NT.has: results})
                add(root, {NT.has: endpoint})
                ws_url = (
                    str(session).replace("https://", "wss://") + "/upload"
                )
                logger.info("WebSocket URL", url=ws_url)
                add(
                    endpoint, {NT.url: Literal(ws_url, datatype=XSD.anyURI)}
                )

            logger.info("Returning result", result=result)
            return result


def create_affordance_button(deepgram_client: URIRef):
    return new(
        Deepgram.Client,
        {
            NT.affordance: blank(
                NT.Button,
                {
                    NT.label: Literal("Start", "en"),
                    NT.message: URIRef(Deepgram.Start),
                    NT.target: deepgram_client,
                },
            )
        },
        subject=deepgram_client,
    )


async def receive_results(
    session: URIRef,
    stream: URIRef,
    client: WebSocketConnection,
    results: URIRef,
):
    async with trio.open_nursery() as nursery:
        transcription_receiver = await spawn(
            nursery,
            deepgram_transcription_receiver,
            session,
            stream,
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
