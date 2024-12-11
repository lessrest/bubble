from dataclasses import dataclass, field
import os

from typing import List, Optional, Dict
from datetime import UTC, datetime

from swash.mint import fresh_iri, fresh_uri
import trio
import structlog

from rdflib import XSD, Graph, URIRef, Literal, Namespace
from pydantic import Field, BaseModel
from trio_websocket import WebSocketConnection, open_websocket_url

from swash.prfx import NT
from swash.desc import a, resource, property
from swash.util import S, add, get_single_object, is_a
from bubble.town import (
    ServerActor,
    get_base,
    send,
    this,
    spawn,
    receive,
    in_request_graph,
    with_new_transaction,
    with_transient_graph,
)
from rdflib.namespace import TIME, PROV

Deepgram = Namespace("https://node.town/2024/deepgram/#")
Vox = Namespace("https://swa.sh/2024/vox#")


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
    async with trio.open_nursery() as nursery:
        transcription_receiver = await spawn(
            nursery,
            DeepgramTranscriptionReceiver(
                DeepgramActorState(),
                "Deepgram transcription receiver",
            ),
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
        async with with_new_transaction():
            create_affordance_button(this())

    async def handle(self, nursery: trio.Nursery, graph: Graph) -> Graph:
        logger.info("Deepgram client actor handling message", graph=graph)
        request_id = graph.identifier
        async with with_new_transaction(graph) as result:
            result.add((result.identifier, NT.isResponseTo, request_id))
            if is_a(request_id, Deepgram.Start):
                root = get_base()

                logger.info("Starting new Deepgram session")
                results = await spawn(nursery, deepgram_results_actor)

                logger.info("Spawned results actor", results=results)
                session = await spawn(nursery, deepgram_session, results)

                logger.info("Spawned session actor", session=session)
                assert isinstance(result.identifier, URIRef)

                # with resource(session, a=Deepgram.Session):
                #     result.add((this(), NT.has, session))
                #     logger.debug("Creating session resource")
                #     property(NT.created, datetime.now(UTC).isoformat())

                with resource(
                    fresh_uri(graph), a=NT.UploadEndpoint
                ) as endpoint:
                    add(root, {NT.has: session})
                    add(root, {NT.has: results})
                    add(root, {NT.has: endpoint.node})
                    property(NT.method, NT.WebSocket)
                    property(NT.accepts, NT.AudioData)
                    ws_url = (
                        str(session).replace("https://", "wss://")
                        + "/upload"
                    )
                    logger.info("WebSocket URL", url=ws_url)
                    property(NT.url, ws_url)

                    # with property(NT.has, fresh_uri(graph)):
                    #     logger.debug("Creating event stream")
                    #     a(NT.EventStream)
                    #     property(NT.method, NT.GET)
                    #     property(
                    #         NT.produces,
                    #         Deepgram.TranscriptionHypothesis,
                    #     )

            logger.info("Returning result", result=result)
            return result


def create_affordance_button(deepgram_client: URIRef):
    with resource(deepgram_client, Deepgram.Client) as client:
        with property(NT.affordance, fresh_iri()):
            a(NT.Button)
            property(NT.label, Literal("Start", "en"))
            property(NT.message, URIRef(Deepgram.Start))
            property(NT.target, deepgram_client)
        return client.node


@dataclass
class DeepgramActorState:
    transcription_process: Optional[URIRef] = None
    audio_timeline: Optional[URIRef] = None
    last_end_time: float = 0.0
    last_audio_segment: Optional[S] = None
    last_transcription_hypothesis: Optional[URIRef] = None
    speaker_map: Dict[int, URIRef] = field(default_factory=dict)


class DeepgramTranscriptionReceiver(ServerActor[DeepgramActorState]):
    """Actor that processes Deepgram messages into RDF graphs using the vox vocabulary"""

    def __init__(self, state: DeepgramActorState, name: str):
        super().__init__(state, name=name)

    async def init(self):
        await super().init()
        logger.info("DeepgramRMLProcessor initialized", state=self.state)

    async def handle(self, nursery: trio.Nursery, graph: Graph) -> Graph:
        """Handle incoming Deepgram messages and convert to RDF"""
        state = self.state

        message = DeepgramMessage.model_validate_json(
            get_single_object(graph.identifier, NT.json, graph)
        )

        async with with_new_transaction(graph) as result:
            result.add(
                (result.identifier, NT.isResponseTo, graph.identifier)
            )

            # Create timeline if this is first message
            if state.audio_timeline is None:
                state.audio_timeline = fresh_iri()
                with resource(state.audio_timeline, a=Vox.AudioTimeline):
                    a(TIME.TRS)  # This is a temporal reference system
                    property(Vox.timeUnit, TIME.unitSecond)

            # Create/update transcript process
            if state.transcription_process is None:
                state.transcription_process = fresh_iri()

            with resource(
                state.transcription_process
            ) as transcription_process:
                # Create temporal interval for this segment
                segment_interval = fresh_iri()
                with resource(segment_interval):
                    a(TIME.ProperInterval)
                    property(TIME.hasTRS, state.audio_timeline)
                    property(
                        TIME.hasBeginning,
                        Literal(message.start, datatype=XSD.decimal),
                    )
                    property(
                        TIME.hasEnd,
                        Literal(
                            message.start + message.duration,
                            datatype=XSD.decimal,
                        ),
                    )

                    # Link to previous segment if exists
                    if message.start > state.last_end_time:
                        property(TIME.after, state.last_end_time)

                    state.last_end_time = message.start + message.duration

                # create entity for the audio segment itself
                with property(PROV.used) as audio_segment:
                    a(Vox.AudioSegment)
                    property(TIME.hasTime, segment_interval)
                    if state.last_audio_segment is not None:
                        property(
                            TIME.intervalMetBy, state.last_audio_segment
                        )
                    state.last_audio_segment = audio_segment.node

                # Add temporal relationship between intervals
                if state.last_audio_segment is not None:
                    with resource(segment_interval):
                        property(
                            TIME.intervalMetBy, state.last_audio_segment
                        )

                assert message.channel.alternatives
                alternative = message.channel.alternatives[0]

                # Create hypothesis as a generated entity
                with resource(a=Vox.TranscriptionHypothesis) as hypothesis:
                    transcription_process.add(PROV.generated, hypothesis)
                    property(TIME.intervalEquals, segment_interval)
                    property(PROV.generatedAtTime, datetime.now(UTC))
                    property(PROV.value, alternative.transcript)
                    property(
                        Vox.confidence,
                        Literal(
                            round(alternative.confidence, 2),
                            datatype=XSD.decimal,
                        ),
                    )

                    if message.is_final:
                        a(Vox.FinalHypothesis)
                    else:
                        a(Vox.InterimHypothesis)

                    # Process individual words
                    for word in alternative.words:
                        word_entity = fresh_iri()
                        with resource(word_entity):
                            a(Vox.Word)
                            a(PROV.Entity)  # Each word is an entity
                            property(PROV.value, word.punctuated_word)
                            property(
                                Vox.confidence,
                                Literal(
                                    round(word.confidence, 2),
                                    datatype=XSD.decimal,
                                ),
                            )

                            # Create temporal interval for word
                            word_interval = fresh_iri()
                            with resource(word_interval):
                                a(TIME.ProperInterval)
                                property(
                                    TIME.hasBeginning,
                                    Literal(
                                        word.start, datatype=XSD.decimal
                                    ),
                                )
                                property(
                                    TIME.hasEnd,
                                    Literal(word.end, datatype=XSD.decimal),
                                )
                                property(
                                    TIME.intervalDuring, segment_interval
                                )
                                property(TIME.hasTRS, state.audio_timeline)

                            property(TIME.intervalEquals, word_interval)

                            # Add speaker information if diarization is enabled
                            if hasattr(word, "speaker"):
                                # Get or create speaker from map
                                speaker = state.speaker_map.get(
                                    word.speaker
                                )
                                if speaker is None:
                                    speaker = fresh_iri()
                                    state.speaker_map[word.speaker] = (
                                        speaker
                                    )
                                    # Initialize new speaker
                                    with resource(speaker):
                                        a(PROV.Person)
                                        property(
                                            Vox.speakerId,
                                            Literal(
                                                word.speaker,
                                                datatype=XSD.integer,
                                            ),
                                        )

                                # Link word to speaker
                                property(PROV.wasAttributedTo, speaker)

            return result
