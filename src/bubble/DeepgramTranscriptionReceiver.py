from typing import Dict, Optional
from datetime import UTC, datetime
from dataclasses import field, dataclass

import trio

from rdflib import XSD, Graph, URIRef, Literal
from rdflib.namespace import PROV, TIME

from swash.desc import has_type, has, resource
from swash.mint import fresh_iri
from swash.prfx import NT, RDF
from swash.util import S, add, get_single_object, new
from bubble.talk import VOX, DeepgramMessage
from bubble.town import ServerActor, txgraph


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

    async def handle(self, nursery: trio.Nursery, graph: Graph) -> Graph:
        """Handle incoming Deepgram messages and convert to RDF"""
        message = DeepgramMessage.model_validate_json(
            get_single_object(graph.identifier, NT.json, graph)
        )

        async with txgraph(graph) as result:
            result.add(
                (result.identifier, NT.isResponseTo, graph.identifier)
            )

            self._initialize_state_if_needed()
            segment_interval = self._create_segment_interval(
                result, message
            )
            audio_segment = self._create_audio_segment(
                result, segment_interval
            )
            self._process_transcription(result, message, segment_interval)

            return result

    def _initialize_state_if_needed(self):
        """Initialize audio timeline and transcription process if not already set"""
        if self.state.audio_timeline is None:
            self.state.audio_timeline = fresh_iri()
            with resource(self.state.audio_timeline, a=VOX.AudioTimeline):
                has(VOX.timeUnit, TIME.unitSecond)

        if self.state.transcription_process is None:
            self.state.transcription_process = fresh_iri()

    def _create_segment_interval(
        self, graph: Graph, message: DeepgramMessage
    ) -> URIRef:
        """Create and return a temporal interval for the audio segment"""
        segment_interval = fresh_iri()
        with resource(segment_interval):
            add(
                segment_interval,
                {
                    TIME.hasTRS: self.state.audio_timeline,
                    TIME.hasBeginning: Literal(
                        message.start, datatype=XSD.decimal
                    ),
                    TIME.hasEnd: Literal(
                        message.start + message.duration,
                        datatype=XSD.decimal,
                    ),
                },
            )
            has_type(TIME.ProperInterval)

            if message.start > self.state.last_end_time:
                has(TIME.after, self.state.last_end_time)

            self.state.last_end_time = message.start + message.duration

        return segment_interval

    def _create_audio_segment(
        self, graph: Graph, segment_interval: URIRef
    ) -> S:
        """Create and return an audio segment entity"""
        audio_segment = fresh_iri()

        # Add properties to the audio segment
        add(
            audio_segment,
            {
                PROV.wasGeneratedBy: self.state.transcription_process,
                TIME.hasTime: segment_interval,
            },
        )

        add(audio_segment, {RDF.type: VOX.AudioSegment})

        # Handle temporal relationship with previous segment
        if self.state.last_audio_segment is not None:
            add(
                audio_segment,
                {TIME.intervalMetBy: self.state.last_audio_segment},
            )
            # Add the inverse relationship to the interval
            add(
                segment_interval,
                {TIME.intervalMetBy: self.state.last_audio_segment},
            )

        # Update the state
        self.state.last_audio_segment = audio_segment

        return audio_segment

    def _process_transcription(
        self,
        graph: Graph,
        message: DeepgramMessage,
        segment_interval: URIRef,
    ):
        """Process transcription hypothesis and words"""
        alternative = message.channel.alternatives[0]

        with resource(
            self.state.transcription_process
        ) as transcription_process:
            # Create hypothesis
            with resource(a=VOX.TranscriptionHypothesis) as hypothesis:
                add(
                    transcription_process.node, {PROV.generated: hypothesis}
                )
                add(
                    hypothesis.node,
                    {
                        TIME.intervalEquals: segment_interval,
                        PROV.generatedAtTime: datetime.now(UTC),
                        PROV.value: alternative.transcript,
                        VOX.confidence: Literal(
                            round(alternative.confidence, 2),
                            datatype=XSD.decimal,
                        ),
                    },
                )

                if message.is_final:
                    has_type(VOX.FinalHypothesis)
                else:
                    has_type(VOX.InterimHypothesis)

                # Process words
                for word in alternative.words:
                    # Create word segment
                    new(
                        VOX.WordSegment,
                        {
                            PROV.value: word.word,
                            VOX.confidence: Literal(
                                round(word.confidence, 2),
                                datatype=XSD.decimal,
                            ),
                            TIME.hasBeginning: Literal(
                                word.start, datatype=XSD.decimal
                            ),
                            TIME.hasEnd: Literal(
                                word.end, datatype=XSD.decimal
                            ),
                            TIME.intervalDuring: segment_interval,
                            TIME.hasTRS: self.state.audio_timeline,
                        },
                    )

                    # Handle speaker attribution
                    if hasattr(word, "speaker"):
                        speaker = self._get_or_create_speaker(word.speaker)
                        has(PROV.wasAttributedTo, speaker)

    def _get_or_create_speaker(self, speaker_id: int) -> URIRef:
        """Get existing speaker or create a new one"""
        speaker = self.state.speaker_map.get(speaker_id)
        if speaker is None:
            speaker = fresh_iri()
            self.state.speaker_map[speaker_id] = speaker
            with resource(speaker):
                add(
                    speaker,
                    {
                        VOX.speakerId: Literal(
                            speaker_id, datatype=XSD.integer
                        ),
                    },
                )
                has_type(PROV.Person)
        return speaker
