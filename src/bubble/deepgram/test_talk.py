import json

from datetime import UTC, datetime

import trio
import pytest
import structlog

from rdflib import URIRef, Literal, Namespace

from swash.prfx import NT
from swash.util import add
from bubble.logs import configure_logging
from bubble.http.town import Site
from bubble.mesh.mesh import send, spawn, with_transient_graph
from bubble.repo.repo import Git, Repository
from bubble.deepgram.json import (
    Word,
    Channel,
    Metadata,
    ModelInfo,
    Alternative,
    DeepgramMessage,
)
from bubble.deepgram.talk import deepgram_transcription_receiver

configure_logging()

VOX = Namespace("https://swa.sh/2024/vox#")

VALIDATION_QUERY = """
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX time: <http://www.w3.org/2006/time#>
PREFIX talk: <https://swa.sh/2024/vox#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ex: <http://example.com/>

ASK {
    ?transcript a talk:Transcript ;
        prov:wasGeneratedBy ex:process ;
        talk:hasConfidence 0.98 ;
        talk:hasText "Hello world." ;
        talk:hasSubdivision (
            [ a talk:WordTranscript ;
              talk:hasConfidence 0.99 ;
              talk:hasText "Hello" ;
              talk:hasBareWord "Hello" ;
              time:numericPosition 0.0 ;
              time:numericDuration 0.5 ;
              time:hasTRS ex:stream ;
              prov:wasAttributedTo ?p0
            ]
            [ a talk:WordTranscript ;
              talk:hasConfidence 0.97 ;
              talk:hasText "world." ;
              talk:hasBareWord "world" ;
              time:numericPosition 0.6 ;
              time:numericDuration 0.4 ;
              time:hasTRS ex:stream ;
              prov:wasAttributedTo ?p0
            ]
        ) .
    ?p0 a prov:Person .
}
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

            # Run SPARQL validation on the entire dataset
            logger.info("dataset", dataset=repo.dataset)
            validation_result = repo.dataset.query(VALIDATION_QUERY)
            assert (
                validation_result.askAnswer
            ), "Graph structure does not match expected pattern"

            nursery.cancel_scope.cancel()
