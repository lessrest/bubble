import re

import structlog

from pytest import fixture

from bubble.town.town2 import (
    send,
    this,
    spawn,
    receive,
    using_actor_system,
)


@fixture
def logger():
    return structlog.get_logger(name="test")


async def test_basic_actor_system(logger):
    async with using_actor_system("http://example.com/", logger):

        async def ping_actor():
            msg = await receive()
            assert msg["type"] == "ping"
            await send(msg["reply_to"], {"type": "pong"})

        ping_uri = spawn(ping_actor)

        assert re.match(r"http://example.com/\w+", str(this()))
        assert re.match(r"http://example.com/\w+", str(ping_uri))

        await send(ping_uri, {"type": "ping", "reply_to": this()})

        response = await receive()
        assert response["type"] == "pong"
