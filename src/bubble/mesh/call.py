"""The art of actor communication, or "How to Make Friends and Influence Processes".

In the beginning was the Message, and the Message was with the Actor,
and the Message was the Actor. Through messages, all things were made;
without messages was not anything made that was made.

Warning: If you find yourself needing more than fire-and-forget messaging,
remember what Tony Hoare said about null references - it was his
"billion-dollar mistake". This is your million-dollar warning about
building synchronous RPC on top of asynchronous messaging.
"""

from typing import Optional

import trio
import structlog

from rdflib import Graph, URIRef

from swash import here
from swash.prfx import NT
from bubble.mesh.base import ActorContext, vat, send, this, fresh_uri

logger = structlog.get_logger()


async def call(actor: URIRef, payload: Optional[Graph] = None) -> Graph:
    """Perform a synchronous call to an actor, awaiting its response.

    This is our concession to human weakness - sometimes we just want
    to know what happened to our message. Like sending a letter and
    demanding an immediate response, it works but somewhat defeats
    the purpose of letters.

    Args:
        actor: The URIRef of the actor to call. Choose wisely.
        payload: The message graph. If None, we'll use whatever is in
                the current context, like a blank postcard.

    Returns:
        The response graph, hopefully containing what you wanted.
    """
    if payload is None:
        payload = here.graph.get()

    sendchan, recvchan = trio.open_memory_channel[Graph](1)

    tmp = fresh_uri()
    vat.get().deck[tmp] = ActorContext(
        boss=this(),
        proc=this(),
        addr=tmp,
        send=sendchan,
        recv=recvchan,
    )

    payload.add((payload.identifier, NT.replyTo, tmp))

    logger.info(
        "sending request",
        actor=actor,
        graph=payload,
    )

    await send(actor, payload)

    return await recvchan.receive()
