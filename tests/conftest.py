import pytest
import os
from pathlib import Path
from server import create_app
from server.extensions import db as _db, limiter
import datetime
from datetime import timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import tempfile

@pytest.fixture(scope='session')
def app(test_ca, tmp_path_factory):
    """
    Session-wide application fixture.
    This creates the Flask app and the database schema ONCE for the entire
    test session, which is much more efficient.
    """
    templates_dir = tmp_path_factory.mktemp("ovpn_templates")
    (templates_dir / "999.default.ovpn").write_text("default-template-for-{{ userinfo.sub }}")
    (templates_dir / "000.engineering.ovpn").write_text("engineering-template-for-{{ userinfo.sub }}")

    os.environ["OVPN_TEMPLATES_PATH"] = str(templates_dir)
    os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
    os.environ["OIDC_CLIENT_ID"] = "test-client-id"
    os.environ["OIDC_CLIENT_SECRET"] = "test-client-secret"
    os.environ["OIDC_DISCOVERY_URL"] = "https://example.com/.well-known/openid-configuration"
    os.environ["CA_CERT_PATH"] = test_ca[0]
    os.environ["CA_KEY_PATH"] = test_ca[1]
    os.environ["ENCRYPTION_KEY"] = "YdqNBg_B6d2hzDGDUJXpAhtDq2rJ2t2xsg41i5p4m6o="
    os.environ["OIDC_ADMIN_GROUP"] = "vpn-admins"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    app = create_app()
    app.config.update({"TESTING": True})

    with app.app_context():
        _db.create_all()

    yield app

    # No teardown needed here for schema, as it's for the whole session

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture(scope='function')
def db_session(app):
    """
    This fixture provides perfect database isolation for each test function.
    It starts a transaction before the test and rolls it back afterwards.
    """
    connection = _db.engine.connect()
    transaction = connection.begin()
    
    # Bind the session to this transaction
    session_factory = _db.sessionmaker(bind=connection)
    _db.session = session_factory()

    yield _db.session

    _db.session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="session")
def test_ca():
    """
    Creates a temporary self-signed CA and returns the file paths
    to the key and certificate. This CA is used across the test session.
    """
    ca_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"GB"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Test CA"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"test-ca.localhost"),
    ])
    ca_cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        ca_private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(timezone.utc)
    ).not_valid_after(
        datetime.datetime.now(timezone.utc) + datetime.timedelta(days=365)
    ).add_extension(
        x509.BasicConstraints(ca=True, path_length=None), critical=True,
    ).sign(ca_private_key, hashes.SHA256())

    with tempfile.NamedTemporaryFile(delete=False, suffix=".key") as key_file:
        key_file.write(
            ca_private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        ca_key_path = key_file.name

    with tempfile.NamedTemporaryFile(delete=False, suffix=".crt") as cert_file:
        cert_file.write(ca_cert.public_bytes(serialization.Encoding.PEM))
        ca_cert_path = cert_file.name

    yield ca_cert_path, ca_key_path

    os.remove(ca_key_path)
    os.remove(ca_cert_path)

@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """
    An autouse fixture to reset the rate limiter's storage before each test.
    This ensures that each test function gets a clean slate for its rate limit counts.
    """
    limiter.reset()