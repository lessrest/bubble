"""Certificate handling: Where mathematics meets trust.

In the physical world, we trust documents based on seals, signatures,
and watermarks. In the digital realm, we use mathematics to create
trust - asymmetric cryptography that turns abstract algebra into
practical security.

Historical note: The X.509 standard dates back to 1988, though our
relationship with digital certificates is somewhat younger. We've been
trying to explain certificate validation errors to users ever since.
"""

import ssl
import tempfile

from datetime import datetime, timedelta

import structlog

from cryptography.x509 import (
    Name,
    DNSName,
    NameAttribute,
    ExtendedKeyUsage,
    CertificateBuilder,
    SubjectAlternativeName,
    random_serial_number,
)
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.rsa import (
    generate_private_key,
)

logger = structlog.get_logger()


def generate_self_signed_cert(hostname: str):
    """Generate a self-signed certificate for HTTPS.

    Like writing yourself a letter of recommendation, a self-signed
    certificate is a curious thing - mathematically sound but socially
    suspect. Still, for development and testing, it's better than
    nothing. Just don't try to use it in production unless you enjoy
    explaining security warnings to users.

    Returns:
        tuple[str, str]: Paths to the certificate and key files,
                        like a digital passport and its secret key.
    """
    # Generate a private key - the mathematical secret that makes it all work
    private_key = generate_private_key(
        public_exponent=65537,  # Fermat's F4 prime, a time-honored choice
        key_size=2048,  # Big enough for now, but Moore's Law is watching
    )

    # Create the certificate's identity - a distinguished name that's
    # anything but distinguished in our case
    subject = issuer = Name(
        [
            NameAttribute(NameOID.COUNTRY_NAME, "US"),
            NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            NameAttribute(NameOID.ORGANIZATION_NAME, "My Organization"),
            NameAttribute(NameOID.COMMON_NAME, hostname),
        ]
    )

    # Build the certificate - a dance of extensions and attributes
    # that would make a bureaucrat proud
    cert = (
        CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)  # In self-signed certs, these are the same
        .public_key(private_key.public_key())
        .serial_number(random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(
            datetime.utcnow() + timedelta(days=30)
        )  # Short-lived, like all good things
        .add_extension(
            SubjectAlternativeName([DNSName(hostname)]),
            critical=False,
        )
        .add_extension(
            ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(
            private_key, hashes.SHA256()
        )  # The final flourish - cryptographic proof
    )

    # Write to temp files - our certificates need a physical form
    cert_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
    key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")

    # PEM format - because ASN.1 DER encoding wasn't arcane enough
    cert_file.write(cert.public_bytes(serialization.Encoding.PEM))
    cert_file.flush()

    key_file.write(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_file.flush()

    logger.info(
        "generated self-signed certificate",
        cert=cert.fingerprint(hashes.SHA256()).hex(),
    )

    return cert_file.name, key_file.name


def create_ssl_context(cert_path: str, key_path: str) -> ssl.SSLContext:
    """Create an SSL context from certificate files.

    The SSL context is like a digital handshake protocol - a carefully
    choreographed dance of cryptographic operations that turns
    mathematical trust into secure communications.
    """
    ssl_context = ssl.SSLContext()
    ssl_context.load_cert_chain(cert_path, key_path)
    return ssl_context
