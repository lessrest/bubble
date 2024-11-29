from typing import AsyncGenerator
import anthropic
from anthropic.types import MessageParam
from rich.console import Console

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
            r"^(.*?[.!?])[ \n](.*)$", current_sentence, re.DOTALL
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
    credential: str,
    messages: list[MessageParam],
) -> anthropic.AsyncMessageStreamManager:
    """Stream a response from Anthropic."""
    client = anthropic.AsyncClient(api_key=credential)
    return client.messages.stream(
        messages=messages,
        model="claude-3-5-sonnet-latest",
        max_tokens=1000,
    )


class Claude:
    def __init__(self, credential: str):
        self.credential = credential

    async def stream(
        self, messages: list[MessageParam]
    ) -> AsyncGenerator[str, None]:
        async with streaming_claude_request(
            self.credential, messages
        ) as stream:
            async for chunk in stream.text_stream:
                yield chunk
