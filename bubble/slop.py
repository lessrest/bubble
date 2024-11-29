import anthropic
from anthropic.types import MessageParam
from rich.console import Console

console = Console()


async def stream_sentences(stream, initial_sentence=""):
    """Stream sentences from an Anthropic response, yielding each complete sentence."""
    import re

    # Start with any initial sentence fragment passed in
    current_sentence = initial_sentence

    # Process each chunk from the stream
    for chunk in stream:
        if isinstance(chunk, anthropic.TextEvent):
            # Add the new text to our current sentence buffer
            current_sentence += chunk.text

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


async def stream_normally(stream) -> str:
    """Stream text from an Anthropic response."""
    console.rule()
    text = ""
    for chunk in stream:
        if isinstance(chunk, anthropic.TextEvent):
            text += chunk.text
            console.print(chunk.text, end="")
    console.print()

    return text


def streaming_claude_request(
    credential: str,
    messages: list[MessageParam],
) -> anthropic.MessageStreamManager:
    """Stream a response from Anthropic."""
    client = anthropic.Client(api_key=credential)
    return client.messages.stream(
        messages=messages,
        model="claude-3-5-sonnet-latest",
        max_tokens=1000,
    )
