import os
from server.cert_utils import load_ca, create_device_certificate
from cryptography import x509
from cryptography.hazmat.primitives import serialization

def test_load_ca(test_ca):
    """
    Tests that the CA loading function correctly reads the key and cert files.
    """
    ca_cert_path, ca_key_path = test_ca
    ca_cert, ca_key = load_ca(ca_cert_path, ca_key_path)
    
    assert isinstance(ca_cert, x509.Certificate)
    assert ca_key is not None
    assert ca_cert.issuer == ca_cert.subject # Self-signed

def test_create_device_certificate_with_defaults(test_ca):
    """Tests cert generation with default X.509 attributes."""
    ca_cert_path, ca_key_path = test_ca
    ca_cert, ca_key = load_ca(ca_cert_path, ca_key_path)
    username = "default.user@example.org"

    # Now unpack all 4 return values
    device_key_pem, device_cert_pem, cn, expiry = create_device_certificate(username, ca_cert, ca_key)
    
    assert device_key_pem is not None
    device_cert = x509.load_pem_x509_certificate(device_cert_pem)
    org = device_cert.subject.get_attributes_for_oid(x509.NameOID.ORGANIZATION_NAME)[0].value
    assert org == "OVPN Manager" # Check your new default
    assert username in cn
    
def test_create_device_certificate_with_env_vars(test_ca, mocker):
    """Tests that the function correctly overrides defaults with environment variables."""
    mocker.patch.dict(os.environ, {"X509_O": "Test Company Inc."})
    ca_cert_path, ca_key_path = test_ca
    ca_cert, ca_key = load_ca(ca_cert_path, ca_key_path)
    username = "test.user@example.org"

    # Unpack all four return values
    device_key_pem, device_cert_pem, _, _ = create_device_certificate(username, ca_cert, ca_key)
    
    # Check the mocked organization name
    device_cert = x509.load_pem_x509_certificate(device_cert_pem)
    org = device_cert.subject.get_attributes_for_oid(x509.NameOID.ORGANIZATION_NAME)[0].value
    assert org == "Test Company Inc."
    
    # --- THIS IS THE FIX ---
    # Correctly use the 'device_key_pem' variable that was defined above
    device_key = serialization.load_pem_private_key(device_key_pem, password=None)
    assert device_key.key_size == 4096