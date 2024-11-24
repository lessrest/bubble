import secrets
import base64
from rdflib import Namespace, URIRef
from xid import XID


class Mint:
    """Generator for secure random tokens and non-secure pseudorandomidentifiers."""

    def fresh_token(self) -> str:
        """Generate a secure token encoded in base32."""
        raw_token = secrets.token_bytes(20)
        # Convert to base32 and remove padding
        encoded = (
            base64.b32encode(raw_token).decode("ascii").rstrip("=").upper()
        )
        return encoded

    def fresh_secure_iri(self, namespace: Namespace) -> URIRef:
        """Create a new secure random IRI under the given namespace.

        Args:
            namespace: An rdflib Namespace to use as the base

        Returns:
            URIRef: A new random IRI combining the namespace and a secure token
        """
        return namespace[self.fresh_token()]

    def fresh_casual_iri(self, namespace: Namespace) -> URIRef:
        """Create a new casual IRI under the given namespace using XID.

        Args:
            namespace: An rdflib Namespace to use as the base

        Returns:
            URIRef: A new random IRI combining the namespace and an XID
        """
        return namespace[self.fresh_id()]

    def fresh_id(self) -> str:
        """Generate a non-secure pseudorandom identifier."""
        return XID().string().upper()

    def machine_id(self) -> str:
        """Generate a consistent machine identifier encoded in base32."""
        from machineid import hashed_id

        # Get hex machine ID and convert to bytes
        hex_id = hashed_id("this should be a user secret")
        # Take first 20 bytes (40 hex chars)
        raw_bytes = bytes.fromhex(hex_id[:40])
        # Convert to base32 and remove padding
        return base64.b32encode(raw_bytes).decode("ascii").rstrip("=").upper()
