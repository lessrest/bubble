import logging
import pathlib

import trio
import typer

from typer import Option
from rich.console import Console
from rich.logging import RichHandler
from anthropic.types import MessageParam

from bubble.repo import BubbleRepo
from bubble.slop import claude, stream_normally

FORMAT = "%(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=FORMAT,
    datefmt="[%X]",
    handlers=[RichHandler()],
)

logger = logging.getLogger(__name__)
console = Console(width=80)

app = typer.Typer(add_completion=False)

home = pathlib.Path.home()


@app.command()
def show(
    input_path: str = Option(
        str(home / "bubble"), "--input", "-i", help="Input N3 file path"
    ),
) -> None:
    """Process N3 files with optional reasoning and skolemization."""

    async def run():
        bubble = await BubbleRepo.open(trio.Path(input_path))
        await bubble.load_surfaces()
        await bubble.load_rules()
        await bubble.load_ontology()

        n3_representation = bubble.graph.serialize(format="n3")
        message = initial_message(n3_representation)

        history: list[MessageParam] = [
            {"role": "user", "content": message},
        ]

        while True:
            messages = history
            with claude(messages) as stream:
                reply = await stream_normally(stream)
                history.append({"role": "assistant", "content": reply})

                # prompt user for chat message
                console.rule()
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
                    history.append(
                        {"role": "user", "content": user_message}
                    )

    trio.run(run)


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


def main():
    app()


if __name__ == "__main__":
    main()
