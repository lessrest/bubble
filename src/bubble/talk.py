import os

from typing import List, Optional

import structlog

from pydantic import Field, BaseModel
from trio_websocket import open_websocket_url


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
