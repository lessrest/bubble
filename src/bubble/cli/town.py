from urllib.parse import urlparse

from fastapi import FastAPI
import trio
import hypercorn
import structlog
import hypercorn.trio

from rdflib import PROV, SKOS, Literal, Namespace

import swash.here as here

from swash.prfx import NT, RDF
from swash.util import add
from bubble.http.tool import SheetEditor
from bubble.http.town import Site
from bubble.mesh.mesh import this, spawn
from bubble.repo.repo import Git, Repository

logger = structlog.get_logger()


async def serve_fastapi_app(config: hypercorn.Config, app: FastAPI):
    await hypercorn.trio.serve(
        app,  # type: ignore
        config,
        mode="asgi",
    )


async def bubble_town(
    bind: str, base_url: str, repo_path: str, shell: bool
):
    async def start_bash_shell():
        await trio.run_process(
            ["bash", "-i"],
            stdin=None,
            check=False,
            env={
                # "CURL_CA_BUNDLE": cert_path,
                "PS1": get_bash_prompt(),
                "BASH_SILENCE_DEPRECATION_WARNING": "1",
            },
        )

    def get_bash_prompt():
        return r"\[\e[1m\][\[\e[34m\]town\[\e[0m\]\[\e[1m\]]\[\e[0m\] $ "

    config = hypercorn.Config()
    config.bind = [bind]
    config.log.error_logger = logger.bind(name="hypercorn.error")  # type: ignore

    assert base_url.startswith("https://")
    hostname = urlparse(base_url).hostname
    assert hostname

    # cert_path, key_path = generate_self_signed_cert(hostname)

    config.certfile = "./priv/localhost.pem"
    config.keyfile = "./priv/localhost-key.pem"
    async with trio.open_nursery() as nursery:
        logger.info(
            "starting Node.Town",
            repo_path=repo_path,
            base_url=base_url,
        )
        here.site.set(Namespace(base_url))
        repo = await Repository.create(
            Git(trio.Path(repo_path)),
            namespace=Namespace(base_url),
        )

        await repo.load_all()

        town = Site(base_url, bind, repo)
        with town.install_context():
            with repo.new_graph():
                town.vat.create_identity_graph()

                add(
                    this(),
                    {
                        RDF.type: NT.TownProcess,
                        PROV.generated: town.vat.get_identity_uri(),
                        SKOS.prefLabel: Literal(
                            "root town process", lang="en"
                        ),
                    },
                )

                editor = await spawn(
                    nursery,
                    SheetEditor(this()),
                    name="sheet editor",
                )

                # Link supervisor to the town's identity
                town.vat.link_actor_to_identity(editor)

                nursery.start_soon(
                    serve_fastapi_app, config, town.get_fastapi_app()
                )

                if shell:
                    await start_bash_shell()
                else:
                    while True:
                        await trio.sleep(1)
