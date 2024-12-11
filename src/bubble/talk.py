import os

from typing import List, Optional
from datetime import UTC, datetime

import trio
import structlog

from rdflib import XSD, Graph, URIRef, Literal, Namespace
from pydantic import Field, BaseModel
from trio_websocket import WebSocketConnection, open_websocket_url

from swash import mint
from swash.prfx import NT
from swash.util import S, add, new, is_a, get_single_object
from bubble.town import (
    ServerActor,
    send,
    this,
    spawn,
    receive,
    get_site,
    in_request_graph,
    with_new_transaction,
    with_transient_graph,
)

Deepgram = Namespace("https://node.town/2024/deepgram/#")


logger = structlog.get_logger()


class ModelInfo(BaseModel):
    name: str
    version: str
    arch: str


class Metadata(BaseModel):
    request_id: str
    model_info: ModelInfo
    model_uuid: str


class Word(BaseModel):
    word: str
    start: float
    end: float
    confidence: float
    speaker: int
    punctuated_word: str


class Alternative(BaseModel):
    transcript: str
    confidence: float
    words: List[Word]


class Channel(BaseModel):
    alternatives: List[Alternative]


class DeepgramMessage(BaseModel):
    type: str
    channel_index: List[int]
    duration: float
    start: float
    is_final: bool
    speech_final: bool
    channel: Channel
    metadata: Metadata
    from_finalize: bool = Field(default=False)


class DeepgramParams(BaseModel):
    model: str = "nova-2"
    encoding: Optional[str] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    language: str = "en-US"
    interim_results: bool = True
    punctuate: bool = True
    diarize: bool = True


def using_deepgram_live_session(params: DeepgramParams):
    """Create a websocket connection to Deepgram's streaming API"""
    query_params = []

    query_params.append(f"model={params.model}")
    if params.encoding is not None:
        query_params.append(f"encoding={params.encoding}")
    if params.sample_rate is not None:
        query_params.append(f"sample_rate={params.sample_rate}")
    if params.channels is not None:
        query_params.append(f"channels={params.channels}")
    query_params.append(f"language={params.language}")
    query_params.append(
        f"interim_results={str(params.interim_results).lower()}"
    )
    query_params.append(f"punctuate={str(params.punctuate).lower()}")
    query_params.append(f"diarize={str(params.diarize).lower()}")

    url = "wss://api.deepgram.com/v1/listen?" + "&".join(query_params)

    logger.info("Connecting to Deepgram", url=url)

    headers = [("Authorization", f"Token {os.environ['DEEPGRAM_API_KEY']}")]

    return open_websocket_url(url, extra_headers=headers)


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
    return new(
        Deepgram.Client,
        {
            NT.affordance: [
                new(
                    NT.Button,
                    {
                        NT.label: Literal("Start", "en"),
                        NT.message: URIRef(Deepgram.Start),
                        NT.target: deepgram_client,
                    },
                    mint.fresh_uri(get_site()),
                )
            ]
        },
        deepgram_client,
    )
