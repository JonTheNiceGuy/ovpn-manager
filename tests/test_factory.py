import pytest
import os
from flask import Flask
from server import create_app
from server.extensions import db # Import the shared db object

def test_app_factory_builds_successfully(mocker, tmp_path, test_ca):
    """
    A simple 'smoke test' to ensure the create_app factory can run
    without crashing due to import errors or misconfiguration.
    """
    # --- THIS IS THE FIX ---
    # Because other tests may have already run and populated the SQLAlchemy
    # metadata, we explicitly clear it here to guarantee a clean slate
    # for this specific test.
    db.metadata.clear()

    # 1. Set up the complete mock environment required by the factory
    templates_dir = tmp_path / "ovpn_templates"
    templates_dir.mkdir()
    (templates_dir / "999.default.ovpn").write_text("default-template")
    
    mocker.patch.dict(os.environ, {
        "OVPN_TEMPLATES_PATH": str(templates_dir),
        "FLASK_SECRET_KEY": "test-secret-key",
        "OIDC_CLIENT_ID": "test-client-id",
        "OIDC_CLIENT_SECRET": "test-client-secret",
        "OIDC_DISCOVERY_URL": "https://example.com/.well-known/openid-configuration",
        "CA_CERT_PATH": test_ca[0],
        "CA_KEY_PATH": test_ca[1],
        "ENCRYPTION_KEY": "YdqNBg_B6d2hzDGDUJXpAhtDq2rJ2t2xsg41i5p4m6o=",
        "OIDC_ADMIN_GROUP": "vpn-admins",
        "DATABASE_URL": "sqlite:///:memory:"
    })

    # 2. Attempt to create the application
    app = None
    try:
        app = create_app()
    except Exception as e:
        pytest.fail(f"create_app() crashed during basic initialization: {e}")

    # 3. Assert that the created app is a valid Flask instance
    assert app is not None
    assert isinstance(app, Flask)
