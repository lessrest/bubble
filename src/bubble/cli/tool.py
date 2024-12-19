import os

import rich
import trio
import trio_asyncio

from typer import Option

from swash.mint import fresh_id
from bubble.cli.app import RepoPath, app
from bubble.repo.git import Git
from bubble.repo.repo import Repository, context, from_env
from bubble.apis.replicate import make_image

console = rich.console.Console(width=80)


@app.command()
def tool(
    prompt: str,
    repo_path: str = RepoPath,
    base_url: str = Option(
        ..., "--base-url", help="Base URL for the repository"
    ),
) -> None:
    """Run a tool, for now just generate images."""
    trio_asyncio.run(_run_generate_images, prompt, repo_path, base_url)


async def _run_generate_images(
    prompt: str, repo_path: str, base_url: str
) -> None:
    async def generate_images(repo: Repository, prompt: str):
        """Generate and save images for the given prompt."""
        try:
            readables = await make_image(prompt)

            for i, readable in enumerate(readables):
                img_data = await readable.aread()
                name = f"{fresh_id()}.webp"

                # Save the image
                blob = await repo.get_file(
                    context.buffer.get().identifier, name, "image/webp"
                )
                await blob.write(img_data)
                await repo.save_all()

                console.print(f"[green]Image saved to:[/] {blob.path}")
                await trio.run_process(["open", str(blob.path)])

        except Exception as e:
            console.print(f"[red]Error generating image:[/] {str(e)}")

    # Ensure REPLICATE_API_TOKEN is set
    if "REPLICATE_API_TOKEN" not in os.environ:
        console.print(
            "[red]Error:[/] REPLICATE_API_TOKEN environment variable is not set"
        )
        return

    console.print(f"[green]Generating image for prompt:[/] {prompt}")

    # Try to use bubble environment if available
    if "BUBBLE" in os.environ:
        try:
            async with from_env() as repo:
                await generate_images(repo, prompt)
        except ValueError as e:
            console.print(f"[red]Error:[/] {str(e)}")
            return
    else:
        # Fall back to creating repo from path
        git = Git(trio.Path(repo_path))
        repo = await Repository.create(git, base_url_template=base_url)
        await repo.load_all()
        await generate_images(repo, prompt)
