from urllib.parse import urlparse
from server.models import DownloadToken
from server.extensions import db
from flask import redirect

OIDC_CLIENT_PATH = 'server.extensions.oauth.oidc'

def test_login_redirect(client, mocker):
    """Tests that the /login endpoint correctly calls the OIDC library."""
    mock_authorize_redirect = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_redirect')
    mock_authorize_redirect.return_value = "Redirected"
    response = client.get('/login')
    mock_authorize_redirect.assert_called_once()
    assert response.data == b"Redirected"

def test_auth_browser_flow_redirects_to_landing_page(client, mocker):
    """Tests a browser login redirects to the download landing page."""
    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')
    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|browser-user', 'groups': []}
    }
    response = client.get('/auth')
    assert response.status_code == 302
    assert response.location.startswith("/download-landing/")

def test_auth_cli_flow_redirects_to_localhost(client, mocker):
    """Tests a CLI login redirects to the correct localhost port."""
    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')
    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|cli-user', 'groups': []}
    }
    with client.session_transaction() as sess:
        sess['cli_port'] = '12345'
    response = client.get('/auth')
    assert response.status_code == 302
    assert response.location.startswith("http://localhost:12345/callback?token=")

def test_auth_group_selects_correct_template(client, app, mocker):
    """Tests that a user's group membership selects the correct OVPN template."""
    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')
    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|eng-user', 'groups': ['engineering']}
    }
    auth_response = client.get('/auth')
    assert auth_response.status_code == 302

    redirect_url_path = urlparse(auth_response.location).path
    token_str = redirect_url_path.split('/')[-1]
    
    with app.app_context():
        from server.utils import get_fernet
        fernet = get_fernet()
        token_record = db.session.query(DownloadToken).filter_by(token=token_str).first()
        decrypted_content = fernet.decrypt(token_record.ovpn_content).decode('utf-8') # type: ignore
    
    assert "engineering-template-for-auth|eng-user" in decrypted_content
    
def test_rate_limiter_blocks_excessive_requests(client, mocker):
    """
    Tests that the rate limiter returns a 429 Too Many Requests error.
    Note: we use a separate app context to have a persistent limiter for the test.
    """
    mock_authorize_redirect = mocker.patch('server.extensions.oauth.oidc.authorize_redirect')
    mock_authorize_redirect.return_value = redirect("http://fake-oidc-provider.com/auth")
    
    # The test client resets state, so we need to call within one context
    with client:
        for i in range(20):
            response = client.get('/login')
            # The redirects are fine
            assert response.status_code == 302

        # The 21st request should be rejected
        response = client.get('/login')
        assert response.status_code == 429
        assert b"Too Many Requests" in response.data
