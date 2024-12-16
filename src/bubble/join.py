import base64
from datetime import UTC, datetime
import structlog
from rdflib import XSD, Graph, Literal, URIRef, RDF, PROV, Dataset
from swash.mint import fresh_uri
from swash.prfx import NT
from swash.util import new, add
from bubble.mesh import ActorContext, create_graph
from bubble.keys import parse_public_key_hex, verify_signed_data
from bubble import context

logger = structlog.get_logger(__name__)

async def handle_actor_join(websocket, key: str, site):
    """
    Handle a remote actor joining the town.
    
    Args:
        websocket: The WebSocket connection
        key: The hex-encoded Ed25519 public key of the actor
        site: The Site instance managing the town
    """
    await websocket.accept()
    try:
        with create_graph() as outgoing_handshake:
            # Use the handshake URI itself as the nonce
            nonce = str(outgoing_handshake).encode()
            new(
                NT.Handshake,
                {
                    NT.signedQuestion: Literal(
                        base64.b64encode(site.vat.sign_data(nonce)),
                        datatype=XSD.base64Binary,
                    )
                },
                outgoing_handshake,
            )
            msg = context.graph.get().serialize(format="turtle")
            logger.info("sending handshake", graph=msg)
            await websocket.send_text(msg)
            response = await websocket.receive_text()
            response_graph = Graph()
            response_graph.parse(data=response, format="turtle")
            logger.info("received response", graph=response_graph)

            # Extract and verify the signature from response
            signed_message = response_graph.value(
                outgoing_handshake, NT.signedAnswer
            )
            if not signed_message:
                raise ValueError("No signed message in response")

            # Convert key from hex to bytes
            try:
                public_key = parse_public_key_hex(key)
            except ValueError:
                raise ValueError("Invalid public key format")

            signed_message_bytes = signed_message.toPython()
            assert isinstance(signed_message_bytes, bytes)

            # Verify signature using provided public key
            # Use the handshake URI itself as the nonce
            nonce_bytes = str(outgoing_handshake).encode()

            if not verify_signed_data(
                nonce_bytes, signed_message_bytes, public_key
            ):
                raise ValueError("Invalid signature")

            logger.info("signature verified", public_key=public_key)

            # The URI of the actor is derived from its public key
            # by Base32 encoding the public key and prefixing it with
            # the site namespace.
            remote_actor_uri = site.site[
                base64.b32encode(public_key.public_bytes_raw())
                .decode("ascii")
                .rstrip("=")
                .upper()
            ]

            # We mint a new process URI for this session
            proc = fresh_uri(site.site)

            # We create a send and receive channel for the remote actor
            send, recv = site.vat.nursery.open_memory_channel[Graph](8)

            remote_actor_context = ActorContext(
                boss=site.vat.get_identity_uri(),
                addr=remote_actor_uri,
                proc=proc,
                send=send,
                recv=recv,
            )

            site.vat.deck[remote_actor_uri] = remote_actor_context

            new(
                NT.RemoteActor,
                {
                    NT.publicKey: Literal(
                        base64.b64encode(public_key.public_bytes_raw()),
                        datatype=XSD.base64Binary,
                    ),
                    PROV.wasAssociatedWith: proc,
                    NT.affordance: new(
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
                    ),
                },
                remote_actor_uri,
            )

            new(
                NT.RemoteActorSession,
                {
                    NT.remoteActor: remote_actor_uri,
                    PROV.startedAtTime: context.clock.get()(),
                },
                proc,
            )

            add(
                site.vat.curr.get().proc,
                {NT.hasRemoteActor: remote_actor_uri},
            )

            logger.info(
                "remote actor joined",
                addr=remote_actor_uri,
                proc=proc,
            )

            async def forward_messages_to_remote_actor():
                async for message in recv:
                    msg_json = message.serialize(format="trig")
                    await websocket.send_text(msg_json)

            async def forward_messages_to_town():
                while True:
                    try:
                        data = await websocket.receive_text()
                        msg_graph = Dataset()
                        msg_graph.parse(data=data, format="trig")
                        logger.info("received message", graph=msg_graph)
                        # check if the dataset has a heartbeat resource
                        if heartbeat := msg_graph.value(
                            None, RDF.type, NT.Heartbeat
                        ):
                            logger.info(
                                "heartbeat received",
                                heartbeat=heartbeat,
                            )
                            # respond with a heartbeat
                            msg_graph.add(
                                (
                                    heartbeat,
                                    NT.acknowledgedAtTime,
                                    Literal(datetime.now(UTC)),
                                )
                            )
                            await websocket.send_text(
                                msg_graph.serialize(format="trig")
                            )
                    except Exception as e:
                        logger.error("websocket receive error", error=e)
                        break

            try:
                async with site.vat.nursery.open_nursery() as nursery:
                    nursery.start_soon(forward_messages_to_remote_actor)
                    nursery.start_soon(forward_messages_to_town)
            except Exception as e:
                logger.error("websocket handler error", error=e)
                raise
            finally:
                add(proc, {PROV.endedAtTime: context.clock.get()()})
    except Exception as e:
        logger.error("websocket handler error", error=e)
        raise
