import anthropic

from rich.console import Console

console = Console()


async def stream_sentences(stream, initial_sentence="") -> str:
    """Stream sentences from an Anthropic response, printing each complete sentence."""
    sentences: list[str] = []
    current_sentence = initial_sentence
    for chunk in stream:
        if isinstance(chunk, anthropic.TextEvent):
            current_sentence += chunk.text

            # Look for complete sentences
            while "</sentence>" in current_sentence:
                # Split on first </sentence> tag
                parts = current_sentence.split("</sentence>", 1)
                sentence_content = parts[0].strip()

                # Extract just the sentence content, ignoring any tags
                if "<sentence>" in sentence_content:
                    _, sentence_content = sentence_content.split(
                        "<sentence>", 1
                    )

                # Only process if there's actual content
                if sentence_content.strip():
                    # Handle multiline content by joining with spaces
                    cleaned_sentence = " ".join(
                        line.strip()
                        for line in sentence_content.splitlines()
                    )

                    # Print the complete sentence
                    console.print(
                        cleaned_sentence,
                        width=72,
                        end="\n\n",
                    )
                    sentences.append(cleaned_sentence)

                # Keep remainder for next iteration
                current_sentence = parts[1]

    return "\n\n".join(sentences)


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


def get_anthropic_credential():
    return os.environ["ANTHROPIC_API_KEY"]


def claude(messages):
    client = anthropic.Client(api_key=get_anthropic_credential())
    return client.messages.stream(
        messages=messages,
        model="claude-3-5-sonnet-latest",
        max_tokens=1000,
    )
