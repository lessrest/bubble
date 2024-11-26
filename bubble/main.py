import os
import logging
import pathlib

import trio
import typer
import anthropic

from typer import Option
from rich.console import Console
from rich.logging import RichHandler
from anthropic.types import MessageParam

from bubble.id import Mint
from bubble.repo import Bubbler
from bubble.n3_utils import print_n3

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
        bubble = await Bubbler.open(trio.Path(input_path), mint)
        await bubble.load_surfaces()
        await bubble.load_rules()
        await bubble.load_ontology()
        conclusion = await bubble.reason()
        print_n3(conclusion)

        n3_representation = bubble.graph.serialize(format="n3")
        message = initial_message(n3_representation)

        history: list[MessageParam] = [
            {"role": "user", "content": message},
        ]

        while False:
            messages = history
            with claude(messages) as stream:
                reply = await stream_normally(stream)
                history.append({"role": "assistant", "content": reply})

                # prompt user for chat message
                user_message = console.input("> ")
                if user_message == "/reason":
                    conclusion = await bubble.reason()
                    serialized = conclusion.serialize(format="n3")
                    history.append(
                        {
                            "role": "user",
                            "content": f"Reasoning over the graph has produced the following triples:\n\n{serialized}",
                        }
                    )
                else:
                    history.append({"role": "user", "content": user_message})

    trio.run(run)


def claude(messages):
    client = anthropic.Client(api_key=get_anthropic_credential())
    return client.messages.stream(
        messages=messages,
        model="claude-3-5-sonnet-latest",
        max_tokens=1000,
    )


def get_anthropic_credential():
    return os.environ["ANTHROPIC_API_KEY"]


def initial_message(n3_representation):
    instructions = [
        "Your task is to describe this knowledge graph in prose.",
        "The prose should use short sentences.",
        "It should accurately convey the contents of the graph.",
        "The reader is the person whose user is described in the graph, so use 'you' to refer to them.",
        "Prefer single-sentence paragraphs.",
        "Avoid using RDF identifiers; use the human-readable names, like good crisp technical prose.",
    ]

    return join_sentences(
        wrap_with_tag("graph", n3_representation),
        *instructions,
    )


def join_sentences(*sentences):
    return "\n\n".join(sentences)


def wrap_with_tag(tag, content):
    return "".join([f"<{tag}>", content, f"</{tag}>"])


if __name__ == "__main__":
    app()
