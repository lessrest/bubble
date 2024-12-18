from typing import AsyncGenerator

import anthropic

from pydantic import SecretStr
from rich.console import Console
from anthropic.types import MessageParam

console = Console()


async def stream_sentences(
    stream: AsyncGenerator[str, None], initial_sentence=""
) -> AsyncGenerator[str, None]:
    """Stream sentences from an Anthropic response, yielding each complete sentence."""
    import re

    # Start with any initial sentence fragment passed in
    current_sentence = initial_sentence

    # Process each chunk from the stream
    async for chunk in stream:
        # Add the new text to our current sentence buffer
        current_sentence += chunk

        # Keep extracting complete sentences while we have them
        while match := re.search(
            r"^(.*?[.!?][ \n])(.*)$", current_sentence, re.DOTALL
        ):
            # Extract the complete sentence and yield it
            sentence_content = match.group(1)
            # Keep the remainder for next iteration
            current_sentence = match.group(2)
            yield sentence_content

    # Yield any remaining text as the final sentence
    if current_sentence:
        yield current_sentence


async def stream_normally(stream: AsyncGenerator[str, None]) -> str:
    """Stream text from an Anthropic response."""
    console.rule()
    text = ""
    async for chunk in stream:
        text += chunk
        console.print(chunk, end="")
    console.print()

    return text


def streaming_claude_request(
    credential: SecretStr,
    messages: list[MessageParam],
    **kwargs,
) -> anthropic.AsyncMessageStreamManager:
    """Stream a response from Anthropic."""
    client = anthropic.AsyncClient(api_key=credential.get_secret_value())
    return client.messages.stream(
        messages=messages,
        model="claude-3-5-sonnet-latest",
        max_tokens=1000,
        **kwargs,
    )


class Claude:
    def __init__(self, credential: SecretStr):
        self.credential = credential

    async def stream(
        self,
        messages: list[MessageParam],
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        async with streaming_claude_request(
            self.credential, messages, **kwargs
        ) as stream:
            async for chunk in stream:
                if chunk.type == "text":
                    yield chunk.text

    async def stream_events(
        self, messages: list[MessageParam], **kwargs
    ) -> AsyncGenerator[anthropic.MessageStreamEvent, None]:
        async with streaming_claude_request(
            self.credential, messages, **kwargs
        ) as stream:
            async for chunk in stream:
                yield chunk
