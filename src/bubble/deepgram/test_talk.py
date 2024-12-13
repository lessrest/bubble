import json
from datetime import UTC, datetime
from typing import Optional

import pytest
import trio
from rdflib import Graph, Literal, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import PROV, TIME, XSD

from bubble.Vat import with_transient_graph
from bubble.deepgram.json import Alternative, Channel, DeepgramMessage, Word
from bubble.deepgram.talk import deepgram_transcription_receiver
from bubble.town import send, spawn
from swash.prfx import NT, VOX
from swash.util import add

EXPECTED_GRAPH = """
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix time: <http://www.w3.org/2006/time#> .
@prefix vox: <http://example.org/vox#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

[] a vox:Recognition ;
    prov:generatedAtTime "2024-03-14T12:00:00Z"^^xsd:dateTime ;
    prov:wasGeneratedBy ?process ;
    vox:hasConfidence "0.98"^^xsd:decimal ;
    vox:hasPunctuatedText "Hello world." ;
    vox:hasSubdivision ?subdivisions ;
    vox:hasTime ?interval .

?subdivisions rdf:first [
    a vox:Recognition ;
    vox:hasConfidence "0.99"^^xsd:decimal ;
    vox:hasText "Hello" ;
    vox:hasTextWithoutPunctuation "Hello" ;
    time:hasBeginning ?start1 ;
    time:hasDuration ?duration1
] .

?subdivisions rdf:rest [
    rdf:first [
        a vox:Recognition ;
        vox:hasConfidence "0.97"^^xsd:decimal ;
        vox:hasText "world." ;
        vox:hasTextWithoutPunctuation "world" ;
        time:hasBeginning ?start2 ;
        time:hasDuration ?duration2
    ] ;
    rdf:rest rdf:nil
] .

?process a vox:TranscriptionProcess ;
    prov:wasAssociatedWith vox:Deepgram .

?interval time:hasBeginning ?start ;
    time:hasDuration ?duration .
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
        metadata={"request_id": "test"},
    )


async def test_transcription_receiver(monkeypatch, sample_message):
    # Mock datetime.now to return a fixed time
    fixed_time = datetime(2024, 3, 14, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "bubble.deepgram.talk.datetime",
        type("MockDateTime", (), {"now": lambda tz: fixed_time}),
    )

    async with trio.open_nursery() as nursery:
        receiver = await spawn(
            nursery, deepgram_transcription_receiver, name="test_receiver"
        )

        # Create and send a message
        with with_transient_graph() as g:
            message_json = json.dumps(sample_message.model_dump())
            add(
                URIRef(g.identifier),
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

        # Get the actual graph from the transaction
        # Note: You'll need to implement a way to access the resulting graph
        # This is a placeholder - you'll need to modify this based on how
        # your system stores and exposes the generated RDF

        # assert isomorphic(actual_graph, expected)

        nursery.cancel_scope.cancel()
