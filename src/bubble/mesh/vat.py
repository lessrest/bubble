"""VAT-to-VAT connection handling for mesh networking.

This module implements the protocol for VATs to discover and connect to each other,
enabling actor messages to be routed between different VAT instances.
"""

from typing import Set
from datetime import UTC, datetime

import trio
import structlog
from fastapi import WebSocket
from rdflib import RDF, XSD, PROV, Graph, URIRef, Literal

from swash.mint import fresh_uri
from swash.prfx import NT
from swash.util import new
from bubble.keys import verify_signed_data
from bubble.mesh.base import Vat, with_transient_graph

logger = structlog.get_logger(__name__)

async def handle_vat_join(
    websocket: WebSocket,
    vat: Vat,
    remote_public_key: bytes
):
    """Handle a remote VAT joining via WebSocket connection."""
    await websocket.accept()
    
    try:
        # Perform handshake and verify remote VAT identity
        remote_vat_uri = await _perform_vat_handshake(
            websocket, vat, remote_public_key
        )
        
        # Create message channels
        send, recv = trio.open_memory_channel[Graph](32)
        
        # Exchange actor directories
        local_actors = set(vat.deck.keys())
        remote_actors = await _exchange_actor_directory(
            websocket, local_actors
        )
        
        # Register the remote VAT
        vat.register_remote_vat(remote_vat_uri, send, remote_actors)
        
        try:
            async with trio.open_nursery() as nursery:
                # Forward messages to remote VAT
                nursery.start_soon(
                    _forward_to_remote_vat, websocket, recv
                )
                # Handle messages from remote VAT
                nursery.start_soon(
                    _forward_from_remote_vat, websocket, vat
                )
                
        finally:
            vat.unregister_remote_vat(remote_vat_uri)
            
    except Exception as e:
        logger.error("VAT connection error", error=e)
        raise

async def _perform_vat_handshake(
    websocket: WebSocket,
    vat: Vat,
    remote_public_key: bytes,
) -> URIRef:
    """Perform cryptographic handshake with remote VAT."""
    # Create and send handshake challenge
    with with_transient_graph() as handshake_id:
        nonce = str(handshake_id).encode()
        signed_challenge = vat.sign_data(nonce)
        
        new(
            NT.VatHandshake,
            {
                NT.signedChallenge: Literal(
                    signed_challenge.hex(),
                    datatype=XSD.hexBinary
                ),
                NT.protocol: NT.Protocol_1
            },
            handshake_id
        )
        
        await websocket.send_text(
            here.graph.get().serialize(format="turtle")
        )
    
    # Verify remote VAT's response
    response = Graph()
    response.parse(
        data=await websocket.receive_text(),
        format="turtle"
    )
    
    if not verify_signed_data(
        nonce,
        bytes.fromhex(
            str(response.value(handshake_id, NT.signedResponse))
        ),
        remote_public_key
    ):
        raise ValueError("Invalid VAT handshake signature")
    
    # Generate and return remote VAT's URI
    return vat.site[remote_public_key.hex()]

async def _exchange_actor_directory(
    websocket: WebSocket,
    local_actors: Set[URIRef]
) -> Set[URIRef]:
    """Exchange actor directories with remote VAT."""
    # Send local actor directory
    directory = Graph()
    directory_id = fresh_uri()
    
    for actor in local_actors:
        directory.add((directory_id, NT.hostsActor, actor))
    
    await websocket.send_text(directory.serialize(format="turtle"))
    
    # Receive remote actor directory
    remote_directory = Graph()
    remote_directory.parse(
        data=await websocket.receive_text(),
        format="turtle"
    )
    
    return {
        actor for actor in remote_directory.objects(None, NT.hostsActor)
    }

async def _forward_to_remote_vat(
    websocket: WebSocket,
    recv: trio.MemoryReceiveChannel
):
    """Forward messages from local VAT to remote VAT."""
    async for message in recv:
        try:
            await websocket.send_text(
                message.serialize(format="turtle")
            )
        except Exception as e:
            logger.error("Error forwarding to remote VAT", error=e)
            break

async def _forward_from_remote_vat(
    websocket: WebSocket,
    vat: Vat
):
    """Handle messages received from remote VAT."""
    while True:
        try:
            message = Graph()
            message.parse(
                data=await websocket.receive_text(),
                format="turtle"
            )
            
            # Extract target actor and forward locally
            target = message.value(None, NT.target)
            if target in vat.deck:
                await vat.deck[target].send.send(message)
            else:
                logger.warning(
                    "Received message for unknown actor",
                    target=target
                )
                
        except Exception as e:
            logger.error("Error handling remote VAT message", error=e)
            break
