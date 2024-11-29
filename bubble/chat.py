from typing import NoReturn

import anthropic
import rich
import rich.panel
import rich.table
import rich.json
import rich.syntax
import rich.progress_bar
from bubble.repo import current_bubble
from bubble.vars import graph
from bubble.slop import Claude
from bubble.util import select_rows

from anthropic.types import (
    MessageParam,
    ToolResultBlockParam,
)
from anthropic.types.message import Message

from rdflib.query import ResultRow


def rows_to_text(rows: list[ResultRow]) -> str:
    return "\n".join(map(row_to_text, rows))


def row_to_text(row: ResultRow) -> str:
    return ", ".join([repr(x) for x in row])


def system_message() -> str:
    instructions = [
        "The prose should use short sentences.",
        "It should accurately convey the contents of the graph.",
        "The reader is the person whose user is described in the graph"
        " so use 'you' to refer to them.",
        "Prefer single-sentence paragraphs.",
        "Avoid using RDF identifiers; use the human-readable names",
    ]

    return join_sentences(
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
        while True:
            async for reply in self.claude.stream_events(
                self.history,
                tools=self.tool_specs(),
                system=system_message(),
            ):
                if not self.handle_reply(reply):
                    return

    def handle_reply(self, reply):
        match reply.type:
            case "text":
                self.console.print(reply.text, end="")

            case "message_stop":
                message = reply.message
                return self.handle_message_stop(message)

        return True

    def handle_message_stop(self, message):
        self.console.line()
        self.record_assistant_message(message)

        if message.stop_reason == "tool_use":
            self.handle_tool_use(message)
            return True
        else:
            return False

    def tool_specs(self) -> list[anthropic.types.ToolParam]:
        return [
            {
                "name": "runSparqlSelectQuery",
                "description": "Run a SPARQL SELECT query",
                "input_schema": {
                    "type": "object",
                    "properties": {"sparqlQuery": {"type": "string"}},
                },
            }
        ]

    def handle_tool_use(self, message):
        tool_use = self.extract_tool_use(message)
        tool_name = tool_use.name
        tool_input = tool_use.input
        if tool_name == "runSparqlSelectQuery":
            self.process_sparql_query(tool_use, tool_input)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def extract_tool_use(self, message):
        return next(
            block for block in message.content if block.type == "tool_use"
        )

    def process_sparql_query(self, tool_use, tool_input):
        assert isinstance(tool_input, dict)
        assert "sparqlQuery" in tool_input
        with graph.bind(current_bubble.get().dataset):
            self.console.print(
                rich.panel.Panel(
                    rich.syntax.Syntax(
                        tool_input["sparqlQuery"],
                        "sparql",
                        theme="zenburn",
                    ),
                    title="SPARQL Query",
                )
            )
            rows = select_rows(tool_input["sparqlQuery"])
            n_columns = len(rows[0])
            table = rich.table.Table(
                *[
                    rich.table.Column(header=f"Column {i}")
                    for i in range(n_columns)
                ],
            )
            for row in rows:
                table.add_row(*row)
            self.console.print(table)
            self.console.rule()

            self.append_tool_result(tool_use, rows)

    def append_tool_result(self, tool_use, rows):
        self.history.append(
            MessageParam(
                role="user",
                content=[self.tool_result_param(tool_use, rows)],
            )
        )

    def tool_result_param(self, tool_use, rows) -> ToolResultBlockParam:
        return ToolResultBlockParam(
            type="tool_result",
            tool_use_id=tool_use.id,
            content=rows_to_text(rows),
        )

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
