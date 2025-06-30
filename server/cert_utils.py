from datetime import datetime, timedelta
import os
from datetime import timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def load_ca(ca_cert_path, ca_key_path, password=None):
    """Loads the CA certificate and private key from file."""
    with open(ca_cert_path, "rb") as f:
        ca_cert = x509.load_pem_x509_certificate(f.read())
    with open(ca_key_path, "rb") as f:
        ca_key = serialization.load_pem_private_key(
            f.read(),
            password=password
        )
    return ca_cert, ca_key

def create_device_certificate(username, ca_cert, ca_key):
    """
    Generates a new private key and a device certificate signed by the CA.

    Args:
        username (str): The username to embed in the certificate's Common Name.
        ca_cert (x509.Certificate): The CA's certificate object.
        ca_key (rsa.RSAPrivateKey): The CA's private key object.

    Returns:
        tuple: A tuple containing the PEM-encoded private key and the
               PEM-encoded signed certificate.
    """
    not_valid_before = datetime.now(timezone.utc)

    # 1. Generate a new private key for the device
    device_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    # 2. Create a subject for the new certificate
    common_name = f"{username}-{not_valid_before.timestamp()}"
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, os.getenv("X509_C", "GB")),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, os.getenv("X509_ST", "England")),
        x509.NameAttribute(NameOID.LOCALITY_NAME, os.getenv("X509_L", "London")),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, os.getenv("X509_O", "OVPN Manager")),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])

    # 3. Build the Certificate Signing Request (CSR)
    not_valid_after = not_valid_before + timedelta(days=365) # Certificate valid for 1 year
    
    builder = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        ca_cert.subject
    ).public_key(
        device_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        not_valid_before
    ).not_valid_after(
        not_valid_after # Use the variable here
    ).add_extension(
        x509.BasicConstraints(ca=False, path_length=None), critical=True,
    )

    # 4. Sign the certificate with the CA's private key
    device_cert = builder.sign(ca_key, hashes.SHA256())

    # 5. Serialize key and cert to PEM format
    pem_device_key = device_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    pem_device_cert = device_cert.public_bytes(serialization.Encoding.PEM)

    return pem_device_key, pem_device_cert, common_name, not_valid_after