import secrets
import base64
from rdflib import Namespace, URIRef
from xid import XID


class Mint:
    """Generator for secure random tokens and non-secure pseudorandomidentifiers."""

    def fresh_token(self) -> str:
        """Generate a secure 20-byte token encoded in base32."""
        raw_token = secrets.token_bytes(20)
        # Convert to base32 and remove padding
        encoded = (
            base64.b32encode(raw_token).decode("ascii").rstrip("=").lower()
        )
        return encoded

    def fresh_iri(self, namespace: Namespace) -> URIRef:
        """Create a new random IRI under the given namespace.

        Args:
            namespace: An rdflib Namespace to use as the base

        Returns:
            URIRef: A new random IRI combining the namespace and a token
        """
        return namespace[self.fresh_token()]

    def fresh_id(self) -> str:
        """Generate a non-secure pseudorandom identifier."""
        return XID().string()

    def machine_id(self) -> str:
        """Generate a consistent machine identifier encoded in base32."""
        from machineid import hashed_id
        # Get hex machine ID and convert to bytes
        hex_id = hashed_id("this should be a user secret")
        raw_bytes = bytes.fromhex(hex_id)
        # Convert to base32 and remove padding
        return base64.b32encode(raw_bytes).decode("ascii").rstrip("=").lower()
