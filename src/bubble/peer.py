import base64

from datetime import UTC, datetime
from typing import Tuple

import structlog

from trio import open_nursery, open_memory_channel
from rdflib import RDF, XSD, PROV, Graph, Dataset, Literal, URIRef
from fastapi import WebSocket
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)

from swash.mint import fresh_uri
from swash.prfx import NT
from swash.util import S, add, new
from bubble.data import context
from bubble.keys import verify_signed_data
from bubble.mesh import Vat, ActorContext, with_transient_graph

logger = structlog.get_logger(__name__)


async def handle_anonymous_join(websocket: WebSocket, vat: Vat):
    """
    Handle an anonymous/transient actor joining a town via WebSocket.

    This involves:
    - Accepting the connection
    - Assigning a temporary identity
    - Performing a simple handshake to confirm protocol version
    - Setting up an actor context
    - Forwarding messages between the actor and town
    - Handling heartbeat messages

    Args:
        websocket: The WebSocket connection object
        vat: The Vat instance managing the town and its actors
    """
    await websocket.accept()

    try:
        # Generate a temporary identity for this anonymous actor
        remote_actor_uri = fresh_uri(vat.site)
        proc = fresh_uri(vat.site)

        # Send handshake with protocol version and actor URI
        handshake = Graph()
        handshake_id = fresh_uri(vat.site)
        handshake.add((handshake_id, RDF.type, NT.AnonymousHandshake))
        handshake.add((handshake_id, NT.protocol, NT.Protocol_1))
        handshake.add((handshake_id, NT.actor, remote_actor_uri))

        await websocket.send_text(handshake.serialize(format="turtle"))
        logger.info("sent handshake", handshake=handshake)

        # Wait for acknowledgment
        try:
            ack_msg = await websocket.receive_text()
            ack = Graph()
            ack.parse(data=ack_msg, format="turtle")
            logger.info("received handshake acknowledgment", ack=ack)

            if not any(
                ack.triples((handshake_id, NT.acknowledged, Literal(True)))
            ):
                raise ValueError("Invalid handshake acknowledgment")

        except Exception as e:
            logger.error("handshake acknowledgment failed", error=e)
            raise

        # Create send/receive channels for actor messages
        send, recv = open_memory_channel[Graph](8)

        # Create and register the actor context
        remote_actor_context = ActorContext(
            boss=vat.get_identity_uri(),
            addr=remote_actor_uri,
            proc=proc,
            send=send,
            recv=recv,
        )
        vat.deck[remote_actor_uri] = remote_actor_context

        # Record the anonymous actor session
        new(
            NT.AnonymousActor,
            {
                PROV.wasAssociatedWith: proc,
                NT.affordance: create_message_prompt(remote_actor_uri),
            },
            remote_actor_uri,
        )

        new(
            NT.AnonymousActorSession,
            {
                NT.remoteActor: remote_actor_uri,
                PROV.startedAtTime: context.clock.get()(),
            },
            proc,
        )

        # Add the remote actor to the current process
        add(vat.curr.get().proc, {NT.hasRemoteActor: remote_actor_uri})

        logger.info(
            "anonymous actor joined", addr=remote_actor_uri, proc=proc
        )

        # Launch message forwarding tasks
        await _run_message_forwarders(
            websocket, remote_actor_uri, proc, recv
        )

    except Exception as e:
        logger.error("anonymous websocket handler error", error=e)
        raise


async def handle_actor_join(
    websocket: WebSocket, key: Ed25519PublicKey, vat: Vat
):
    """
    Handle a remote actor (identified by their public key) joining a town via WebSocket.

    This involves:
    - Performing a handshake with a signed challenge-response mechanism.
    - Verifying the actor's public key signature.
    - Setting up a remote actor context and registering it with the vat.
    - Forwarding messages between the remote actor and the town.
    - Handling heartbeat messages.

    Args:
        websocket: The WebSocket connection object.
        key: The Ed25519 public key object of the remote actor.
        vat: The Vat instance managing the town and its actors.
    """
    await websocket.accept()

    try:
        # Perform the handshake and verify the actor's signature
        await _perform_handshake(websocket, vat, key)

        # Setup the remote actor context and register them with the vat
        remote_actor_uri, proc, recv = _setup_remote_actor_context(vat, key)

        # Launch message forwarding tasks
        await _run_message_forwarders(
            websocket, remote_actor_uri, proc, recv
        )

    except Exception as e:
        logger.error("websocket handler error", error=e)
        raise


async def _perform_handshake(
    websocket: WebSocket, vat: Vat, key: Ed25519PublicKey
):
    """
    Perform the handshake with the remote actor. The handshake is a challenge-response
    mechanism where the vat sends a signed nonce and the actor responds by signing the
    same nonce, proving possession of the corresponding private key.

    Args:
        websocket: The WebSocket connection.
        vat: The Vat instance managing the town.
        key: The Ed25519 public key object of the remote actor.

    Returns:
        public_key: The verified public key object.

    Raises:
        ValueError: If the signature verification fails or the response is invalid.
    """

    # Create a transient graph for the outgoing handshake
    with with_transient_graph() as outgoing_handshake:
        # Use the handshake URI as the nonce
        nonce = str(outgoing_handshake).encode()

        # Sign the nonce using the vat key and send it to the actor
        signed_question = vat.sign_data(nonce)
        new(
            NT.Handshake,
            {
                NT.signedQuestion: Literal(
                    base64.b64encode(signed_question),
                    datatype=XSD.base64Binary,
                )
            },
            outgoing_handshake,
        )

        handshake_msg = context.graph.get().serialize(format="turtle")
        logger.info("sending handshake", graph=handshake_msg)
        await websocket.send_text(handshake_msg)

    # Receive and parse the actor's response
    response_graph = await receive_graph(websocket)
    logger.info("received handshake response", graph=response_graph)

    # Extract the signed answer from the response
    signed_answer = response_graph.value(
        outgoing_handshake, NT.signedAnswer
    )
    if not signed_answer:
        raise ValueError("No signed answer in handshake response")

    signed_answer_bytes = signed_answer.toPython()
    assert isinstance(signed_answer_bytes, bytes)

    # Verify that the signed answer is correct by checking against the nonce
    if not verify_signed_data(nonce, signed_answer_bytes, key):
        raise ValueError("Invalid signature during handshake")

    logger.info("signature verified successfully", public_key=key)


async def receive_graph(websocket) -> Graph:
    response = await websocket.receive_text()
    response_graph = Graph()
    response_graph.parse(data=response, format="turtle")
    return response_graph


def _setup_remote_actor_context(vat: Vat, key: Ed25519PublicKey):
    """
    Set up the remote actor's context once their identity has been verified.
    This includes:
    - Deriving the remote actor URI from their public key.
    - Minting a new process URI for this session.
    - Creating a memory channel for communication.
    - Registering the actor in the vat's deck.

    Args:
        vat: The Vat instance.
        key: The verified public key of the remote actor.

    Returns:
        (remote_actor_uri, proc, recv):
            remote_actor_uri: The URI of the remote actor.
            proc: The process URI minted for this session.
            recv: The receive channel for messages intended for this actor.
    """

    # Derive the remote actor's URI from their public key
    remote_actor_uri = derive_actor_uri(vat, key)

    # Mint a new process URI
    proc = fresh_uri(vat.site)

    # Create send/receive channels for actor messages
    send, recv = open_memory_channel[Graph](8)

    # Create and register the actor context
    remote_actor_context = ActorContext(
        boss=vat.get_identity_uri(),
        addr=remote_actor_uri,
        proc=proc,
        send=send,
        recv=recv,
    )
    vat.deck[remote_actor_uri] = remote_actor_context

    # Annotate the actor with their key and a message prompt affordance
    new(
        NT.RemoteActor,
        {
            NT.publicKey: encode_public_key_to_literal(key),
            PROV.wasAssociatedWith: proc,
            NT.affordance: create_message_prompt(remote_actor_uri),
        },
        remote_actor_uri,
    )

    # Record the start of the remote actor session
    new(
        NT.RemoteActorSession,
        {
            NT.remoteActor: remote_actor_uri,
            PROV.startedAtTime: context.clock.get()(),
        },
        proc,
    )

    # Add the remote actor to the current process
    add(vat.curr.get().proc, {NT.hasRemoteActor: remote_actor_uri})

    logger.info("remote actor joined", addr=remote_actor_uri, proc=proc)
    return remote_actor_uri, proc, recv


def encode_public_key_to_literal(key: Ed25519PublicKey) -> Literal:
    """
    Encode a public key to a base64-encoded literal.
    """
    return Literal(
        base64.b64encode(key.public_bytes_raw()).decode("ascii"),
        datatype=XSD.base64Binary,
    )


def create_message_prompt(remote_actor_uri: URIRef):
    return new(
        NT.Prompt,
        {
            NT.label: Literal("Send", "en"),
            NT.message: NT.TextMessage,
            NT.target: remote_actor_uri,
            NT.placeholder: Literal(
                "Enter a message to send to the remote actor...",
                "en",
            ),
        },
    )


def derive_actor_uri(vat: Vat, key: Ed25519PublicKey) -> URIRef:
    """
    Derive the remote actor's URI from their public key.

    Args:
        vat: The Vat instance.
        key: The Ed25519 public key object of the remote actor.

    Returns:
        The URI of the remote actor.
    """
    key_raw = key.public_bytes_raw()
    actor_id = base64.b32encode(key_raw).decode("ascii").rstrip("=").upper()
    return vat.site[actor_id]


async def _run_message_forwarders(websocket, remote_actor_uri, proc, recv):
    """
    Run two concurrent tasks:
    - Forward messages from the town to the remote actor.
    - Forward messages from the remote actor to the town (including handling heartbeats).

    Args:
        websocket: The WebSocket connection.
        remote_actor_uri: The URI of the remote actor.
        proc: The process URI associated with this session.
        recv: The receive channel for messages destined for the remote actor.
    """

    async def forward_messages_to_remote_actor():
        """
        Forward messages from the town (received on `recv` channel) to the remote actor via WebSocket.
        """
        async for message in recv:
            msg_trig = message.serialize(format="trig")
            await websocket.send_text(msg_trig)

    async def forward_messages_to_town():
        """
        Forward messages from the remote actor (received via WebSocket) to the town.
        Also handles heartbeat messages, acknowledging them when received.
        """
        while True:
            try:
                msg = await receive_dataset()
                logger.info("received message from remote actor", graph=msg)

                # Check if the dataset includes a heartbeat
                if heartbeat := msg.value(None, RDF.type, NT.Heartbeat):
                    await acknowledge_heartbeat(msg, heartbeat)
            except Exception as e:
                logger.error("websocket receive error", error=e)
                break

    async def receive_dataset() -> Dataset:
        """
        Receive a dataset from the WebSocket.
        """
        data = await websocket.receive_text()
        msg = Dataset(default_union=True)
        msg.parse(data=data, format="trig")
        return msg

    async def acknowledge_heartbeat(msg: Dataset, heartbeat: S):
        """
        Acknowledge a heartbeat message by adding an acknowledgment timestamp.
        """
        logger.info("heartbeat received", heartbeat=heartbeat)
        # Add an acknowledgment timestamp
        t0 = msg.value(heartbeat, PROV.generatedAtTime)
        if not t0:
            raise ValueError("No generatedAtTime found in heartbeat")
        t0 = t0.toPython()
        assert isinstance(t0, datetime)
        t1 = datetime.now(UTC)
        msg.add(
            (
                heartbeat,
                NT.acknowledgedAtTime,
                Literal(t1),
            )
        )
        latency = t1 - t0
        logger.info("heartbeat acknowledged", latency=latency)
        await send_dataset(msg)

    async def send_dataset(msg: Dataset):
        await websocket.send_text(msg.serialize(format="trig"))

    # Run both forwarding coroutines concurrently
    try:
        async with open_nursery() as nursery:
            nursery.start_soon(forward_messages_to_remote_actor)
            nursery.start_soon(forward_messages_to_town)
    except Exception as e:
        logger.error("websocket handler error (forwarders)", error=e)
        raise
    finally:
        # When the connection is closed, record the ending time of the session
        add(proc, {PROV.endedAtTime: context.clock.get()()})
