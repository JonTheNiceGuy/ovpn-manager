import pytest
import os
from unittest.mock import MagicMock
from server.utils import get_tlscrypt_key
import subprocess
import shutil

openvpn_is_available = pytest.mark.skipif(
    not shutil.which("openvpn"), reason="openvpn binary not found in PATH"
)

@pytest.fixture
def clean_env():
    """A fixture to ensure a clean environment for each test."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)

V1_KEY_CONTENT = "-----BEGIN OpenVPN Static key V1-----\nkey-data\n-----END OpenVPN Static key V1-----"
V2_SERVER_KEY_CONTENT = "-----BEGIN OpenVPN tls-crypt-v2 server key-----\nkey-data\n-----END OpenVPN tls-crypt-v2 server key-----"

def test_get_tlscrypt_key_no_path(clean_env):
    """Tests that the function returns None when no key path is configured."""
    assert get_tlscrypt_key("dummy_cert_data") == (None, None)

def test_get_tlscrypt_v1_key(fs, clean_env):
    """Tests that the function correctly reads and returns a V1 key."""
    key_path = "/etc/openvpn/tls.key"
    fs.create_file(key_path, contents=V1_KEY_CONTENT)
    os.environ["TLSCRYPT_KEY_PATH"] = key_path
    
    key_type, key_content = get_tlscrypt_key("dummy_cert_data")
    assert key_type == 1
    assert key_content == V1_KEY_CONTENT

@openvpn_is_available
def test_get_tlscrypt_v2_key_integration(app, tmp_path, clean_env):
    """
    Tests that a valid v2 client key is generated from a valid v2 server key.
    This is an integration test that calls the real 'openvpn' binary.
    """
    server_key_path = tmp_path / "tls-v2-server.key"
    dummy_cert_pem = "-----BEGIN CERTIFICATE-----\ndummy-cert-data\n-----END CERTIFICATE-----"

    # 1. Generate a real, valid v2 server key using the openvpn command
    result = subprocess.run(
        ["openvpn", "--genkey", "tls-crypt-v2-server", str(server_key_path)],
        capture_output=True, text=True, check=True
    )
    assert server_key_path.exists()

    # 2. Set the environment variable to point to our valid key
    os.environ["TLSCRYPT_KEY_PATH"] = str(server_key_path)

    # 3. Call our function within the app context
    with app.app_context():
        key_type, key_content = get_tlscrypt_key(dummy_cert_pem)

    # 4. Assert the results
    assert key_type == 2
    assert key_content is not None
    assert key_content.startswith("-----BEGIN OpenVPN tls-crypt-v2 client key-----")
    assert key_content.endswith("-----END OpenVPN tls-crypt-v2 client key-----")

def test_get_tlscrypt_invalid_key(fs, clean_env):
    """Tests that an invalid key format raises a RuntimeError."""
    key_path = "/etc/openvpn/invalid.key"
    fs.create_file(key_path, contents="this is not a valid key")
    os.environ["TLSCRYPT_KEY_PATH"] = key_path
    
    with pytest.raises(RuntimeError, match="TLSCRYPT_KEY is not valid"):
        get_tlscrypt_key("dummy_cert_data")