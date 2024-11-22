import datetime
import hashlib
import tempfile
from rdflib import RDF, BNode, Graph, Literal, URIRef, Namespace
import sys

from rich import pretty, print
from rich.syntax import Syntax
from rich.panel import Panel
from rich.progress import Progress

import trio

from rich.console import Console

console = Console()

pretty.install()

SWA = Namespace("https://swa.sh/")
NT = Namespace("https://node.town/2024/")


class N3Processor:
    def __init__(self, base="https://swa.sh/2024/11/22/step/1"):
        self.base = base
        self.graph = Graph(base=base)

    def print_n3(self):
        n3 = self.graph.serialize(format="n3")
        n3 = n3.replace(
            "    ", "  "
        )  # Replace 4 spaces with 2 spaces globally
        print(Panel(Syntax(n3, "turtle"), title="N3"))

    def get_single_object(self, subject, predicate, error_msg):
        objects = list(self.graph.objects(subject, predicate))
        if len(objects) != 1:
            print(error_msg)
            return None
        return objects[0]

    def get_next_step(self, step):
        next_step = self.get_single_object(
            step, SWA.precedes, "Expected one successor step"
        )
        return next_step

    def get_supposition(self, step):
        supposition = self.get_single_object(
            step, SWA.supposes, "Expected one supposition for the next step"
        )

        return supposition

    def get_invocation_details(self, invocation):
        target = self.get_single_object(
            invocation, NT.target, "Expected one target for the invocation"
        )
        target_type = self.get_single_object(
            target, RDF.type, "Expected one type for the target"
        )
        parameter = self.get_single_object(
            invocation,
            NT.parameter,
            "Expected one parameter for the invocation",
        )
        return parameter, target_type

    async def process_invocations(self, step):
        invocations = list(self.graph.objects(step, SWA.invokes))
        if not invocations:
            return

        console.print(f"processing {len(invocations)} invocations")

        with Progress() as progress:
            async with trio.open_nursery() as nursery:
                for invocation in invocations:
                    parameter, target_type = self.get_invocation_details(
                        invocation
                    )
                    if target_type == NT.ShellCapability:
                        task = progress.add_task(f"{parameter}", total=None)
                        nursery.start_soon(
                            self.run_shell_command,
                            parameter,
                            progress,
                            task,
                            invocation,
                        )

    async def run_shell_command(
        self, command, progress: Progress, task: any, invocation: URIRef
    ):
        # make a new random directory
        temp_dir = tempfile.mkdtemp()
        # set $out to $temp_dir/out
        # run the command as a subprocess
        result = await trio.run_process(
            command,
            shell=True,
            cwd=temp_dir,
            env={"out": f"{temp_dir}/out"},
            capture_stderr=True,
        )
        if result.returncode != 0:
            print(f"Command failed: {result.returncode}")
            raise Exception(f"Command failed: {result.returncode}")

        # Check if output file exists and print its size
        output_file = f"{temp_dir}/out"
        try:
            size = (await trio.Path(output_file).stat()).st_size
            creation_date_epoch = (
                await trio.Path(output_file).stat()
            ).st_ctime
            creation_date = datetime.datetime.fromtimestamp(
                creation_date_epoch, tz=datetime.timezone.utc
            )

            contenthash = hashlib.sha256(
                await trio.Path(output_file).read_bytes()
            ).hexdigest()

            result_node = BNode()
            self.graph.add((result_node, RDF.type, NT.LocalFile))
            self.graph.add(
                (result_node, NT.creationDate, Literal(creation_date))
            )
            self.graph.add((result_node, NT.size, Literal(size)))
            self.graph.add((result_node, NT.path, Literal(output_file)))
            self.graph.add(
                (result_node, NT.contentHash, Literal(contenthash))
            )
            self.graph.add((invocation, SWA.result, result_node))
        except FileNotFoundError:
            pass

        progress.update(
            task,
            total=100,
            completed=100,
            description=f"{command} ({size} bytes)",
        )

    async def process(self):
        self.graph.parse(sys.stdin, format="n3")
        # self.print_n3()

        # We know the current step is <#>
        step = URIRef(f"{self.base}#")

        next_step = self.get_next_step(step)
        if not next_step:
            raise Exception("No next step found")

        supposition = self.get_supposition(next_step)
        if not supposition:
            raise Exception("No supposition found")

        await self.process_invocations(step)
        self.print_n3()


def main():
    processor = N3Processor()
    trio.run(processor.process)


if __name__ == "__main__":
    main()
