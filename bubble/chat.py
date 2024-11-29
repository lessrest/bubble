from typing import NoReturn

import rich
import rich.panel
import rich.json
import rich.progress_bar
from bubble.repo import current_bubble
from bubble.slop import Claude
from bubble.util import select_rows

from anthropic.types import MessageParam
from anthropic.types.message import Message

from rdflib.query import ResultRow


def rows_to_text(rows: list[ResultRow]) -> str:
    return "\n".join(map(row_to_text, rows))


def row_to_text(row: ResultRow) -> str:
    return ", ".join([repr(x) for x in row])


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
    def __init__(self, claude: Claude, console: rich.console.Console):
        self.claude = claude
        self.console = console
        self.history: list[MessageParam] = []

    async def run(self) -> None:
        await self.chat_loop()

    async def chat_loop(self) -> NoReturn:
        while True:
            user_message = self.prompt_for_message()
            await self.handle_user_input(user_message)
            await self.stream_assistant_reply()

    async def stream_assistant_reply(self) -> None:
        tools = [
            {
                "name": "runSparqlSelectQuery",
                "description": "Run a SPARQL SELECT query",
                "input_schema": {
                    "type": "object",
                    "properties": {"sparqlQuery": {"type": "string"}},
                },
            }
        ]
        while True:
            async for reply in self.claude.stream_events(
                self.history, tools=tools
            ):
                progressbar = None
                match reply.type:
                    case "text":
                        self.console.print(reply.text, end="")
                    # case "content_block_start":
                    #     if reply.content_block.type == "tool_use":
                    #         progressbar = rich.progress_bar.ProgressBar(
                    #             total=None
                    #         )
                    #         self.console.print(progressbar)
                    #         self.console.file.write("\r")
                    # case "input_json":
                    #     if progressbar is not None:
                    #         progressbar.update(0.5)
                    #         self.console.print(progressbar)
                    #         self.console.file.write("\r")

                    case "message_stop":
                        self.console.line()
                        message = reply.message
                        self.record_assistant_message(message)

                        if message.stop_reason == "tool_use":
                            tool_use = next(
                                block
                                for block in message.content
                                if block.type == "tool_use"
                            )
                            tool_name = tool_use.name
                            tool_input = tool_use.input
                            if tool_name == "runSparqlSelectQuery":
                                assert isinstance(tool_input, dict)
                                assert "sparqlQuery" in tool_input
                                rows = select_rows(
                                    tool_input["sparqlQuery"]
                                )
                                #                                self.console.print(rows)
                                self.history.append(
                                    MessageParam(
                                        role="user",
                                        content=[
                                            {
                                                "type": "tool_result",
                                                "tool_use_id": tool_use.id,
                                                "content": rows_to_text(
                                                    rows
                                                ),
                                            }
                                        ],
                                    )
                                )
                            else:
                                raise ValueError(
                                    f"Unknown tool: {tool_name}"
                                )
                        else:
                            return

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

    def record_assistant_message(self, message: Message) -> None:
        self.history.append(
            MessageParam(role="assistant", content=message.content)
        )

    def prompt_for_message(self) -> str:
        self.console.rule()
        user_message = self.console.input("> ")
        self.console.rule()
        return user_message
