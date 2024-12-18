import ssl
import tempfile

from datetime import datetime, timedelta

import structlog

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

logger = structlog.get_logger()


def generate_self_signed_cert(hostname: str):
    """Generate a self-signed certificate for HTTPS.

    Returns:
        tuple[str, str]: Paths to the certificate and key files
    """
    # Generate a private key
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(
                NameOID.STATE_OR_PROVINCE_NAME, "California"
            ),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(
                NameOID.ORGANIZATION_NAME, "My Organization"
            ),
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(hostname)]),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    # Write to temp files
    cert_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
    key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")

    cert_file.write(cert.public_bytes(serialization.Encoding.PEM))
    cert_file.flush()

    key_file.write(
        key.private_bytes(
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
    """Create an SSL context from certificate files."""
    ssl_context = ssl.SSLContext()
    ssl_context.load_cert_chain(cert_path, key_path)
    return ssl_context
