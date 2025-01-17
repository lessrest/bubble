from base64 import b64encode
from typing import Tuple
from datetime import UTC, datetime

from rdflib import XSD, PROV, URIRef, Literal
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from swash.prfx import DID
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


def parse_public_key_hex(hex_string: str) -> ed25519.Ed25519PublicKey:
    """Parse a hex-encoded Ed25519 public key.

    Args:
        hex_string: Hex-encoded public key

    Returns:
        Ed25519PublicKey: The parsed public key

    Raises:
        ValueError: If the hex string is invalid
    """
    try:
        key_bytes = bytes.fromhex(hex_string)
        return ed25519.Ed25519PublicKey.from_public_bytes(key_bytes)
    except ValueError as e:
        raise ValueError(f"Invalid public key hex string: {e}")


def verify_signed_data(
    message: bytes, signature: bytes, public_key: ed25519.Ed25519PublicKey
) -> bool:
    """Verify a signed message using an Ed25519 public key.

    Args:
        message: The original message bytes
        signature: The signature bytes to verify
        public_key: The public key to verify with

    Returns:
        bool: True if signature is valid, False otherwise
    """
    try:
        public_key.verify(signature, message)
        return True
    except Exception:
        return False


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
