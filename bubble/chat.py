from typing import NoReturn

import rich
from bubble.repo import current_bubble
from bubble.slop import streaming_claude_request, stream_normally
from bubble.util import select_one_row

from anthropic.types import MessageParam


class MissingCredentialError(LookupError):
    pass


def initial_message(n3_representation) -> str:
    instructions = [
        "Your task is to describe this knowledge graph in prose.",
        "The prose should use short sentences.",
        "It should accurately convey the contents of the graph.",
        "The reader is the person whose user is described in the graph"
        " so use 'you' to refer to them.",
        "Prefer single-sentence paragraphs.",
        "Avoid using RDF identifiers; use the human-readable names",
    ]

    return join_sentences(
        wrap_with_tag("graph", n3_representation),
        *instructions,
    )


def join_sentences(*sentences) -> str:
    return "\n\n".join(sentences)


def wrap_with_tag(tag, content) -> str:
    return "".join([f"<{tag}>", content, f"</{tag}>"])


class BubbleChat:
    def __init__(self, console: rich.console.Console):
        self.console = console
        self.history: list[MessageParam] = []

    async def get_anthropic_credential(self) -> str:
        query = """
            SELECT ?value
            WHERE {
                ?account a nt:ServiceAccount ;
                    nt:forService ai:AnthropicService ;
                    nt:hasPart [ a nt:BearerToken ;
                                nt:hasValue ?value ] .
            }
        """
        try:
            return select_one_row(query)[0]
        except ValueError:
            raise MissingCredentialError()

    async def run(self) -> None:
        n3_representation = current_bubble.get().graph.serialize(
            format="n3"
        )
        message = initial_message(n3_representation)
        self.history = [
            {"role": "user", "content": message},
        ]

        await self.chat_loop()

    async def chat_loop(self) -> NoReturn:
        while True:
            await self.stream_assistant_reply()
            user_message = self.prompt_for_message()
            await self.handle_user_input(user_message)

    async def stream_assistant_reply(self) -> None:
        with streaming_claude_request(
            credential=await self.get_anthropic_credential(),
            messages=self.history,
        ) as stream:
            reply = await stream_normally(stream)
        self.record_assistant_message(reply)

    async def handle_user_input(self, user_message: str) -> None:
        if user_message == "/reason":
            await self.discuss_reasoning_output()
        else:
            self.record_user_message(user_message)

    async def discuss_reasoning_output(self) -> None:
        conclusion = await current_bubble.get().reason()
        serialized = conclusion.serialize(format="n3")
        self.record_user_message(
            "Reasoning produced the following triples:",
            "",
            serialized,
        )

    def record_user_message(self, *text: str) -> None:
        self.history.append({"role": "user", "content": "\n".join(text)})

    def record_assistant_message(self, reply: str) -> None:
        self.history.append({"role": "assistant", "content": reply})

    def prompt_for_message(self) -> str:
        self.console.rule()
        user_message = self.console.input("> ")
        return user_message
