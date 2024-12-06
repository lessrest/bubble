from typing import NoReturn

import anthropic
import rich
import rich.console
import rich.json
import rich.panel
import rich.progress_bar
import rich.syntax
import rich.table
from anthropic.types import MessageParam, ToolResultBlockParam
from anthropic.types.message import Message
from anthropic.types.tool_use_block import ToolUseBlock
from rdflib.query import ResultRow

from bubble.bash import get_shell_tool_spec, handle_shell_tool
from bubble.repo import current_bubble
from bubble.slop import Claude
from swash.util import select_rows
from swash.vars import graph


def join_sentences(*sentences) -> str:
    """Join multiple sentences with double newlines."""
    return "\n\n".join(sentences)


def wrap_with_tag(tag: str, content: str) -> str:
    """Wrap content with XML-style tags."""
    return f"<{tag}>{content}</{tag}>"


def row_to_text(row: ResultRow) -> str:
    """Convert a single result row to text format."""
    return ", ".join([repr(x) for x in row])


def rows_to_text(rows: list[ResultRow]) -> str:
    """Convert multiple result rows to text format."""
    return "\n".join(map(row_to_text, rows))


def system_message() -> str:
    """Generate the system message with formatting instructions."""
    instructions = [
        "The prose should use short sentences.",
        "It should accurately convey the contents of the graph.",
        "The reader is the person whose user is described in the graph"
        " so use 'you' to refer to them.",
        "Prefer single-sentence paragraphs.",
        "Avoid using RDF identifiers; use the human-readable names",
    ]
    return join_sentences(*instructions)


class BubbleChat:
    """Main chat interface for interacting with Claude."""

    def __init__(self, claude: Claude, console: rich.console.Console):
        self.claude = claude
        self.console = console
        self.history: list[MessageParam] = []

    async def run(self) -> None:
        """Start the chat loop."""
        await self.chat_loop()

    async def chat_loop(self) -> NoReturn:
        """Main chat interaction loop."""
        while True:
            user_message = self.prompt_for_message()
            await self.handle_user_input(user_message)
            await self.stream_assistant_reply()

    def prompt_for_message(self) -> str:
        """Get input from the user."""
        self.console.rule()
        user_message = self.console.input("> ")
        self.console.rule()
        return user_message

    def tool_specs(self) -> list[anthropic.types.ToolParam]:
        """Define available tools for Claude."""
        return [
            {
                "name": "runSparqlSelectQuery",
                "description": "Run a SPARQL SELECT query",
                "input_schema": {
                    "type": "object",
                    "properties": {"sparqlQuery": {"type": "string"}},
                },
            },
            get_shell_tool_spec(),
        ]

    async def stream_assistant_reply(self) -> None:
        """Stream and process Claude's response."""
        while True:
            async for reply in self.claude.stream_events(
                self.history,
                tools=self.tool_specs(),
                system=system_message(),
            ):
                if not await self.handle_reply(reply):
                    return

    async def handle_reply(
        self, reply: anthropic.MessageStreamEvent
    ) -> bool:
        """Process different types of replies from Claude."""
        match reply.type:
            case "text":
                self.console.print(reply.text, end="")
            case "message_stop":
                message = reply.message
                return await self.handle_message_stop(message)
        return True

    async def handle_message_stop(self, message: Message) -> bool:
        """Process the end of a message from Claude."""
        self.record_assistant_message(message)
        self.console.line()

        if message.stop_reason == "tool_use":
            await self.handle_tool_use(message)
            return True
        return False

    async def handle_tool_use(self, message: Message) -> None:
        """Process tool use requests from Claude."""
        tool_use = self.extract_tool_use(message)
        tool_name = tool_use.name
        param = tool_use.input

        # We expect the tool input to be a dict of parameters.
        assert isinstance(param, dict)

        self.console.rule()

        result = await self.process_tool(tool_name, param)
        self.append_tool_result(tool_use, result)

    async def process_tool(self, tool_name: str, param: dict) -> str:
        """Route tool requests to appropriate handlers."""
        if tool_name == "runSparqlSelectQuery":
            return await self.process_sparql_query(param)
        elif tool_name == "runShellCommand":
            return await self.process_shell_command(param)
        raise ValueError(f"Unknown tool: {tool_name}")

    def extract_tool_use(self, message: Message) -> ToolUseBlock:
        """Extract tool use block from message."""
        return next(
            block for block in message.content if block.type == "tool_use"
        )

    async def process_sparql_query(self, tool_input: dict) -> str:
        """Execute and format results of a SPARQL query."""
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
            table = self.create_results_table(rows)
            self.console.print(table)
            self.console.rule()

            return rows_to_text(rows)

    def create_results_table(
        self, rows: list[ResultRow]
    ) -> rich.table.Table:
        """Create a formatted table for query results."""
        n_columns = len(rows[0])
        table = rich.table.Table(
            *[
                rich.table.Column(header=f"Column {i}")
                for i in range(n_columns)
            ],
        )
        for row in rows:
            table.add_row(*row)
        return table

    async def process_shell_command(self, tool_input: dict) -> str:
        """Execute a shell command."""
        assert isinstance(tool_input, dict)
        return await handle_shell_tool(tool_input)

    def append_tool_result(
        self, tool_use: ToolUseBlock, result: str
    ) -> None:
        """Add tool results to message history."""
        self.history.append(
            MessageParam(
                role="user",
                content=[self.tool_result_param(tool_use, result)],
            )
        )

    def tool_result_param(
        self, tool_use: ToolUseBlock, result: str
    ) -> ToolResultBlockParam:
        """Create a tool result parameter block."""
        return ToolResultBlockParam(
            type="tool_result",
            tool_use_id=tool_use.id,
            content=result,
        )

    async def handle_user_input(self, user_message: str) -> None:
        """Process user input and special commands."""
        if user_message == "/reason":
            await self.discuss_reasoning_output()
        else:
            self.record_user_message(user_message)

    async def discuss_reasoning_output(self) -> None:
        """Handle the /reason command."""
        conclusion = await current_bubble.get().reason()
        serialized = conclusion.serialize(format="n3")
        self.record_user_message(
            "Reasoning produced the following triples:",
            "",
            serialized,
        )

    def record_user_message(self, *text: str) -> None:
        """Add a user message to the history."""
        self.history.append({"role": "user", "content": "\n".join(text)})

    def record_assistant_message(self, message: Message) -> None:
        """Add an assistant message to the history."""
        self.history.append(
            MessageParam(role="assistant", content=message.content)
        )
