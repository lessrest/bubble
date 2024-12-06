import hashlib
import datetime
import tempfile

from typing import Optional
from contextvars import ContextVar
from dataclasses import dataclass

import trio

from rdflib import Literal
from rdflib.graph import _SubjectType
from rdflib.query import ResultRow
from rich.console import Console

from swash.prfx import NT
from bubble.json import json_from_rdf
from swash.util import add, new, select_one_row

console = Console()


capability_map = {}


@dataclass
class InvocationContext:
    invocation: _SubjectType

    def select_one_row(self, query: str, bindings: dict = {}) -> ResultRow:
        bindings = bindings.copy()
        bindings["invocation"] = self.invocation

        return select_one_row(query, bindings)


def capability(capability_type: _SubjectType):
    def decorator(func):
        capability_map[capability_type] = func
        return func

    return decorator


@dataclass
class FileResult:
    """Represents the result of a file operation"""

    path: str
    size: Optional[int] = None
    creation_date: Optional[datetime.datetime] = None
    content_hash: Optional[str] = None


async def create_result_node(
    file_result: FileResult,
    invocation: Optional[_SubjectType] = None,
) -> _SubjectType:
    node = new(
        NT.LocalFile,
        {
            NT.path: Literal(file_result.path),
            NT.creationDate: Literal(file_result.creation_date),
            NT.size: Literal(file_result.size),
            NT.contentHash: Literal(file_result.content_hash),
        },
    )
    if invocation is not None:
        add(subject=invocation, properties={NT.result: node})
    return node


async def get_file_metadata(path: str) -> FileResult:
    stat = await trio.Path(path).stat()
    content = await trio.Path(path).read_bytes()

    return FileResult(
        path=path,
        size=stat.st_size,
        creation_date=datetime.datetime.fromtimestamp(
            stat.st_ctime, tz=datetime.timezone.utc
        ),
        content_hash=hashlib.sha256(content).hexdigest(),
    )


@capability(NT.ShellCapability)
async def do_shell(ctx: InvocationContext) -> None:
    temp_dir = tempfile.mkdtemp()
    output_file = f"{temp_dir}/out"

    command, stdin = ctx.select_one_row(
        """
        SELECT ?command ?stdin
        WHERE {
            ?invocation nt:provides ?cmd .
            ?cmd a nt:ShellCommand ;
                    nt:value ?command .
            OPTIONAL { ?invocation nt:provides ?x .
                    ?x a nt:StandardInput ;
                            nt:value ?stdin }
            }
        """
    )

    await trio.run_process(
        command,
        shell=True,
        cwd=temp_dir,
        env={"out": f"{temp_dir}/out"},
        capture_stderr=True,
        stdin=stdin.encode() if stdin else None,
    )

    try:
        # Get metadata about output file and create result node in graph
        file_result = await get_file_metadata(output_file)
        await create_result_node(file_result, ctx.invocation)

    except FileNotFoundError:
        # Command may not have created output file - that's ok
        pass


http_client = ContextVar("http_client")


@capability(NT.POSTCapability)
async def do_post(ctx: InvocationContext) -> None:
    url, post, bearer = ctx.select_one_row(
        """
        SELECT ?url ?post ?bearer
        WHERE {
            ?invocation nt:provides ?request .
            ?request nt:hasURL ?url .
            OPTIONAL { ?request nt:posts ?post }
            OPTIONAL { ?request nt:hasAuthorizationHeader ?bearer }
        }
        """,
    )

    headers = {}
    if bearer:
        headers["Authorization"] = bearer

    json = json_from_rdf(post)

    await http_client.get().request(
        method="POST",
        url=url,
        json=json,
        headers=headers,
    )
