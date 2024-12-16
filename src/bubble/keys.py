from base64 import b64encode
from typing import Tuple
from datetime import UTC, datetime

from rdflib import XSD, URIRef, Literal, PROV
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from swash.prfx import NT, DID
from swash.util import new


def generate_keypair() -> (
    Tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]
):
    """Generate a new Ed25519 keypair."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def get_public_key_bytes(public_key: ed25519.Ed25519PublicKey) -> bytes:
    """Get the raw bytes of a public key."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def get_public_key_hex(public_key: ed25519.Ed25519PublicKey) -> str:
    """Get the hex representation of a public key."""
    return get_public_key_bytes(public_key).hex()


def generate_identity_uri(public_key: ed25519.Ed25519PublicKey) -> URIRef:
    """Generate a DID URI from a public key."""
    return URIRef(f"did:key:{get_public_key_hex(public_key)}")


# define functions to parse a public key from a hex string
# and to verify a signed bytes object using a public key
# AI!


def create_identity_graph(
    public_key: ed25519.Ed25519PublicKey, subject: URIRef
):
    """Create a graph representing a cryptographic identity."""
    new(
        DID.Ed25519VerificationKey2020,
        {
            DID.publicKeyBase64: Literal(
                b64encode(get_public_key_bytes(public_key)).decode()
            ),
            PROV.generatedAtTime: Literal(
                datetime.now(UTC).isoformat(), datatype=XSD.dateTime
            ),
        },
        subject,
    )


def build_did_document(
    did_uri: URIRef, doc_uri: URIRef, public_key: ed25519.Ed25519PublicKey
):
    """Build a DID document using the provided keypair."""
    verification_key = new(
        DID.Ed25519VerificationKey2020,
        {
            DID.controller: did_uri,
            DID.publicKeyBase64: Literal(
                b64encode(get_public_key_bytes(public_key)).decode()
            ),
        },
        generate_identity_uri(public_key),
    )

    new(
        DID.DIDDocument,
        {
            DID.id: did_uri,
            DID.controller: did_uri,
            PROV.generatedAtTime: Literal(
                datetime.now(UTC).isoformat(), datatype=XSD.dateTime
            ),
            DID.verificationMethod: [verification_key],
            DID.authentication: [verification_key],
            DID.assertionMethod: [verification_key],
        },
        subject=doc_uri,
    )
