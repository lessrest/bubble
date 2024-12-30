import os
import sys

import trio
import structlog

from typer import Option
from rdflib import PROV, Literal

from swash.prfx import NT
from swash.util import make_list, new
from bubble.cli.app import RepoPath, app
from bubble.repo.git import Git
from bubble.repo.repo import Repository
from bubble.stat.stat import gather_system_info


@app.command()
def shell(
    repo_path: str = RepoPath,
    base_url: str = Option(
        "https://example.com/",
        "--base-url",
        help="Base URL for the repository",
    ),
) -> None:
    """Create a new repository and start a shell session."""
    trio.run(_bubble_shell, repo_path, base_url)


async def _bubble_shell(repo_path: str, base_url: str) -> None:
    logger = structlog.get_logger()
    git = Git(trio.Path(repo_path))
    await git.init()
    repo = await Repository.create(git, base_url_template=base_url)
    await repo.save_all()
    await repo.commit("new repository")

    system_info = await gather_system_info()
    user = system_info["user_info"]

    with repo.using_new_buffer():
        # XXX: should reuse an agent entity
        with repo.using_new_agent(
            NT.Account,
            {
                NT.owner: user.pw_gecos,
            },
        ) as agent:
            with repo.using_new_activity(
                NT.InteractiveShellSession,
                {
                    PROV.wasStartedBy: new(
                        NT.Command,
                        {
                            NT.programPath: Literal(sys.argv[0]),
                            NT.arguments: make_list(
                                [Literal(arg) for arg in sys.argv[1:]]
                            ),
                        },
                    )
                },
            ) as activity:
                # Create a derived graph for the shell session
                with repo.using_derived_buffer(
                    origin=repo.metadata_id
                ) as derived_id:
                    # Get the directory path for this graph
                    graph_dir = repo.graph_dir(derived_id)
                    await graph_dir.mkdir(parents=True, exist_ok=True)

                    await repo.save_all()
                    await repo.commit("new shell session")

                    logger.info(
                        "Starting shell session",
                        graph=derived_id,
                        activity=activity,
                        directory=str(graph_dir),
                    )

                    # Start bash with environment variables set and cwd set to graph directory
                    await trio.run_process(
                        ["bash", "-i"],
                        stdin=None,
                        check=False,
                        cwd=str(graph_dir),
                        env={
                            "BUBBLE_REPO": repo_path,
                            "BUBBLE_BASE": repo.get_base_url(),
                            "BUBBLE_GRAPH": str(derived_id),
                            "BUBBLE_GRAPH_DIR": str(graph_dir),
                            "BUBBLE_ACTIVITY": str(activity),
                            "BUBBLE_AGENT": str(agent),
                            "PS1": r"\n\[\e[1m\]\[\e[34m\]"
                            + derived_id.n3()
                            + " @ "
                            + system_info["hostname"]
                            + r" \[\e[0m\]\[\e[1m\]\[\e[0m\]\n $ ",
                            "BASH_SILENCE_DEPRECATION_WARNING": "1",
                            # Inherit parent environment
                            **os.environ,
                        },
                    )

                    # After shell exits, commit any changes
                    await repo.save_all()
                    await repo.commit("Update after shell session")
