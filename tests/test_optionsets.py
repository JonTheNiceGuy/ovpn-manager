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

def test_auth_uses_default_optionset(client, app, mocker):
    """
    Tests that the default optionset is used when none is specified in the session.
    """
    mock_authorize_redirect = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_redirect')
    mock_authorize_redirect.return_value = redirect("/fake-oidc") # Needs to be a valid response
    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')
    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|default-user', 'groups': []}
    }

    with client:
        client.get('/login')
        auth_response = client.get('/auth')

        assert auth_response.status_code == 302
        redirect_url_path = urlparse(auth_response.location).path
        token_str = redirect_url_path.split('/')[-1]

        with app.app_context():
            from server.utils import get_fernet
            token_record = db.session.query(DownloadToken).filter_by(token=token_str).first()
            decrypted_content = get_fernet().decrypt(token_record.ovpn_content).decode('utf-8')
            
            assert "proto udp" in decrypted_content
            assert "proto tcp-client" not in decrypted_content
            assert token_record.optionset_used == 'default'

def test_auth_uses_specific_optionset_from_session(client, app, mocker):
    """
    Tests the full end-to-end optionset flow by calling /login to set the
    session, then calling /auth to verify the correct template is rendered.
    """
    # Mock the two external calls that our routes make
    mock_authorize_redirect = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_redirect')
    mock_authorize_redirect.return_value = redirect("/fake-oidc") # Needs to be a valid response
    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')

    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|tcp-user', 'groups': []}
    }

    with client:
        client.get('/login?optionset=UseTCP')
        auth_response = client.get('/auth')
        assert auth_response.status_code == 302
        redirect_url_path = urlparse(auth_response.location).path
        token_str = redirect_url_path.split('/')[-1]
        with app.app_context():
            from server.utils import get_fernet
            token_record = db.session.query(DownloadToken).filter_by(token=token_str).first()
            decrypted_content = get_fernet().decrypt(token_record.ovpn_content).decode('utf-8')
            
            assert "proto tcp-client" in decrypted_content
            assert "proto udp" not in decrypted_content
            assert token_record.optionset_used == 'UseTCP'
