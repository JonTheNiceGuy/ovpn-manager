import datetime
import os
from datetime import datetime, timezone, timedelta
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

print("Generating a new self-signed CA for local development...")

# Ensure the output directory exists
output_dir = "dev/certs"
os.makedirs(output_dir, exist_ok=True)
key_path = os.path.join(output_dir, "ca.key")
cert_path = os.path.join(output_dir, "ca.crt")

# Generate our private key
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)

# Define the certificate's subject and issuer (they are the same for a self-signed cert)
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, u"GB"),
    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"England"),
    x509.NameAttribute(NameOID.LOCALITY_NAME, u"Glossop"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"OVPN Manager Dev CA"),
    x509.NameAttribute(NameOID.COMMON_NAME, u"dev-ca.localhost"),
])

# Build the certificate
cert = x509.CertificateBuilder().subject_name(
    subject
).issuer_name(
    issuer
).public_key(
    private_key.public_key()
).serial_number(
    x509.random_serial_number()
).not_valid_before(
    datetime.now(timezone.utc)
).not_valid_after(
    # Set a long expiry for the dev CA
    datetime.now(timezone.utc) + timedelta(days=365*5)
).add_extension(
    x509.BasicConstraints(ca=True, path_length=None), critical=True,
).sign(private_key, hashes.SHA256())

# Write our private key to a file
with open(key_path, "wb") as f:
    f.write(private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
print(f"Private key saved to: {key_path}")

# Write our certificate to a file
with open(cert_path, "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))
print(f"Certificate saved to: {cert_path}")
