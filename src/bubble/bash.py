from anthropic import types
import trio
import json
from typing import Optional
from pydantic import BaseModel


class BashResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


async def bash(
    command: str,
    stdin: Optional[str] = None,
) -> BashResult:
    """Run a shell command and return the result"""

    # Run the command
    process = await trio.run_process(
        command,
        shell=True,
        capture_stdout=True,
        capture_stderr=True,
        stdin=stdin.encode() if stdin else None,
    )

    return BashResult(
        stdout=process.stdout.decode(),
        stderr=process.stderr.decode(),
        exit_code=process.returncode,
    )


class ShellCommandInput(BaseModel):
    command: str
    stdin: Optional[str] = None


def get_shell_tool_spec() -> types.ToolParam:
    """Return the tool specification for the shell command"""
    return {
        "name": "runShellCommand",
        "description": "Run a shell command on the local system",
        "input_schema": ShellCommandInput.model_json_schema(),
    }


async def handle_shell_tool(tool_input: dict) -> str:
    """Handle the shell tool invocation and return results as string"""
    validated_input = ShellCommandInput.model_validate(tool_input)
    result = await bash(
        validated_input.command,
        validated_input.stdin,
    )

    return json.dumps(result.model_dump())
