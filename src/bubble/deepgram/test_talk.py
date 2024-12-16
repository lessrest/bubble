import json
from datetime import UTC, datetime

import pytest
import structlog
import trio
from rdflib import Graph, Literal, URIRef, Namespace

from bubble.mesh import spawn, with_transient_graph
from bubble.deepgram.json import (
    Alternative,
    Channel,
    DeepgramMessage,
    Metadata,
    ModelInfo,
    Word,
)
from bubble.deepgram.talk import deepgram_transcription_receiver
from bubble.mesh import send
from bubble.town import Site
from bubble.data import Repository, Git
from swash.prfx import NT
from swash.util import add, get_single_object

EXPECTED_GRAPH = """
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix time: <http://www.w3.org/2006/time#> .
@prefix vox: <http://example.org/vox#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

[] a vox:Recognition ;
    prov:generatedAtTime "2024-03-14T12:00:00Z"^^xsd:dateTime ;
    prov:wasGeneratedBy _:process ;
    vox:hasConfidence "0.98"^^xsd:decimal ;
    vox:hasPunctuatedText "Hello world." ;
    vox:hasSubdivision _:subdivisions ;
    vox:hasTime _:interval .

_:subdivisions rdf:first [
    a vox:Recognition ;
    vox:hasConfidence "0.99"^^xsd:decimal ;
    vox:hasText "Hello" ;
    vox:hasTextWithoutPunctuation "Hello" ;
    time:hasBeginning _:start1 ;
    time:hasDuration _:duration1
] .

_:subdivisions rdf:rest [
    rdf:first [
        a vox:Recognition ;
        vox:hasConfidence "0.97"^^xsd:decimal ;
        vox:hasText "world." ;
        vox:hasTextWithoutPunctuation "world" ;
        time:hasBeginning _:start2 ;
        time:hasDuration _:duration2
    ] ;
    rdf:rest rdf:nil
] .

_:process a vox:TranscriptionProcess ;
    prov:wasAssociatedWith vox:Deepgram .

_:interval time:hasBeginning _:start ;
    time:hasDuration _:duration .

_:start time:inTimePosition [
    time:numericPosition "0.0"^^xsd:decimal ;
    time:unitType time:unitSecond
] .

_:duration time:numericDuration "1.0"^^xsd:decimal ;
    time:unitType time:unitSecond .

_:start1 time:inTimePosition [
    time:numericPosition "0.0"^^xsd:decimal ;
    time:unitType time:unitSecond
] .

_:duration1 time:numericDuration "0.5"^^xsd:decimal ;
    time:unitType time:unitSecond .

_:start2 time:inTimePosition [
    time:numericPosition "0.6"^^xsd:decimal ;
    time:unitType time:unitSecond
] .

_:duration2 time:numericDuration "0.4"^^xsd:decimal ;
    time:unitType time:unitSecond .
"""


@pytest.fixture
def sample_message():
    return DeepgramMessage(
        type="Results",
        channel=Channel(
            alternatives=[
                Alternative(
                    transcript="Hello world.",
                    confidence=0.98,
                    words=[
                        Word(
                            word="Hello",
                            start=0.0,
                            end=0.5,
                            confidence=0.99,
                            punctuated_word="Hello",
                            speaker=0,
                        ),
                        Word(
                            word="world",
                            start=0.6,
                            end=1.0,
                            confidence=0.97,
                            punctuated_word="world.",
                            speaker=0,
                        ),
                    ],
                )
            ]
        ),
        duration=1.0,
        start=0.0,
        is_final=True,
        channel_index=[0],
        speech_final=True,
        metadata=Metadata(
            request_id="test",
            model_info=ModelInfo(
                name="test",
                version="test",
                arch="test",
            ),
            model_uuid="test",
        ),
    )


async def test_transcription_receiver(
    monkeypatch, sample_message, tmp_path
):
    # Mock datetime.now to return a fixed time
    fixed_time = datetime(2024, 3, 14, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "bubble.deepgram.talk.datetime",
        type("MockDateTime", (), {"now": lambda tz: fixed_time}),
    )

    repo = await Repository.create(
        Git(tmp_path), namespace=Namespace("http://example.com/")
    )
    town = Site("http://example.com/", "localhost:8000", repo=repo)
    with town.install_context():
        async with trio.open_nursery() as nursery:
            process = URIRef("http://example.com/process")
            stream = URIRef("http://example.com/stream")
            receiver = await spawn(
                nursery,
                deepgram_transcription_receiver,
                process,
                stream,
                name="test_receiver",
            )
            logger = structlog.get_logger()

            # Create and send a message
            with with_transient_graph() as g:
                logger.info("g", g=g)
                message_json = json.dumps(sample_message.model_dump())
                add(
                    URIRef(g),
                    {
                        NT.json: Literal(message_json),
                    },
                )

                await send(receiver)

            # Allow some time for processing
            await trio.sleep(0.1)

            # Compare the resulting graph with expected
            expected = Graph()
            expected.parse(data=EXPECTED_GRAPH, format="turtle")

            gg = repo.dataset.graph(g, base=str(repo.namespace))
            structlog.get_logger().info("g", g=g, graph=gg)

            result = get_single_object(g, NT.resultedIn, gg)
            transcript_graph = repo.dataset.graph(
                result, base=str(repo.namespace)
            )
            structlog.get_logger().info(
                "transcript_graph", graph=transcript_graph
            )

            #            assert rdflib.compare.isomorphic(transcript_graph, expected)

            # XXX do the comparison

            nursery.cancel_scope.cancel()
