import os
import pathlib

import trio
import typer
import anthropic
from anthropic.types import MessageParam

from typer import Option
from rich.console import Console

from bubble.id import Mint
from bubble.repo import Bubble
import logging

from rich.logging import RichHandler

FORMAT = "%(message)s"
logging.basicConfig(
    level=logging.INFO, format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

logger = logging.getLogger(__name__)
console = Console(width=80)

app = typer.Typer(add_completion=False)

home = pathlib.Path.home()


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
                        line.strip() for line in sentence_content.splitlines()
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


@app.command()
def show(
    input_path: str = Option(
        str(home / "bubble"), "--input", "-i", help="Input N3 file path"
    ),
) -> None:
    """Process N3 files with optional reasoning and skolemization."""

    async def run():
        mint = Mint()
        bubble = await Bubble.open(trio.Path(input_path), mint)
        await bubble.load_surfaces()
        await bubble.load_rules()

        n3_representation = bubble.graph.serialize(format="n3")
        message = initial_message(n3_representation)

        client = anthropic.Client(api_key=os.environ["ANTHROPIC_API_KEY"])

        history: list[MessageParam] = [
            {"role": "user", "content": message},
        ]

        while True:
            messages = history
            with client.messages.stream(
                messages=messages,
                model="claude-3-5-sonnet-latest",
                max_tokens=1000,
            ) as stream:
                reply = await stream_normally(stream)
                history.append({"role": "assistant", "content": reply})

                # prompt user for chat message
                user_message = console.input("> ")
                history.append({"role": "user", "content": user_message})

    def initial_message(n3_representation):
        return f"""
        <graph>
        {n3_representation}
        </graph>
        Your task is to describe this knowledge graph in prose.
        The prose should use short sentences. It should accurately convey the contents of the graph.
        The reader is the person whose user is described in the graph, so use "you" to refer to them.
        Prefer single-sentence paragraphs.
        Avoid using RDF identifiers; use the human-readable names, like good crisp technical prose.
        """

    trio.run(run)


if __name__ == "__main__":
    app()
