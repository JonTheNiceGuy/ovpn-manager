import os
from pathlib import Path
from urllib.parse import urlparse
from flask import redirect
from server.extensions import db
from server.models import DownloadToken

OIDC_CLIENT_PATH = 'server.extensions.oauth.oidc'

def setup_test_files(app, mocker):
    """Helper function to create mock template/optionset files for tests."""
    templates_dir = Path(app.config["OVPN_TEMPLATES_PATH"])
    optionsets_dir = templates_dir.parent / "ovpn_optionsets"
    optionsets_dir.mkdir(exist_ok=True)
    (optionsets_dir / "default.opts").write_text("proto udp")
    (optionsets_dir / "UseTCP.opts").write_text("proto tcp-client")
    
    # We must patch the environment variable so the app factory reloads the new path
    mocker.patch.dict(os.environ, {"OVPN_OPTIONSETS_PATH": str(optionsets_dir)})

    # Also update the main template to use the new variable
    default_template = templates_dir / "999.default.ovpn"
    default_template.write_text("{{ optionset }}")


def test_login_route_stores_optionset_in_session(client, mocker):
    """
    Tests that the /login route correctly captures the 'optionset'
    query parameter and stores it in the user's session.
    """
    # Mock the final redirect to prevent network calls
    mock_redirect = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_redirect')
    mock_redirect.return_value = redirect("/fake-oidc")

    with client:
        # Call login with a specific optionset
        client.get('/login?optionset=UseTCP')
        # Check that the session variable was set correctly
        with client.session_transaction() as session:
            assert session['optionset'] == 'UseTCP'

        # Call login without one, check it defaults correctly
        client.get('/login')
        with client.session_transaction() as session:
            assert session['optionset'] == 'default'

def test_auth_route_uses_correct_optionset(client, app, mocker):
    """
    Tests that the /auth route uses the optionset from the session
    to render the correct ovpn file content.
    """
    setup_test_files(app, mocker)

    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')
    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|optionset-user', 'groups': []}
    }

    # --- Scenario 1: Use the default optionset from the session ---
    with client.session_transaction() as session:
        session['optionset'] = 'default'
    
    auth_response = client.get('/auth')
    redirect_url_path = urlparse(auth_response.location).path
    token_str = redirect_url_path.split('/')[-1]

    with app.app_context():
        from server.utils import get_fernet
        token_record = db.session.query(DownloadToken).filter_by(token=token_str).first()
        decrypted_content = get_fernet().decrypt(token_record.ovpn_content).decode('utf-8')
        assert "proto udp" in decrypted_content
        assert token_record.optionset_used == 'default'

    # --- Scenario 2: Use a specific optionset from the session ---
    with client.session_transaction() as session:
        session['optionset'] = 'UseTCP'

    auth_response_tcp = client.get('/auth')
    redirect_url_path_tcp = urlparse(auth_response_tcp.location).path
    token_str_tcp = redirect_url_path_tcp.split('/')[-1]

    with app.app_context():
        from server.utils import get_fernet
        token_record_tcp = db.session.query(DownloadToken).filter_by(token=token_str_tcp).first()
        decrypted_content_tcp = get_fernet().decrypt(token_record_tcp.ovpn_content).decode('utf-8')
        assert "proto tcp-client" in decrypted_content_tcp
        assert token_record_tcp.optionset_used == 'UseTCP'