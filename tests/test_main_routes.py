from urllib.parse import urlparse
from server.extensions import db
from server.models import DownloadToken
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

OIDC_CLIENT_PATH = 'server.extensions.oauth.oidc'

def test_download_flow(client, app, mocker):
    """Tests the full successful download flow and state change."""
    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')
    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|dl-user', 'groups': []}
    }
    auth_response = client.get('/auth')
    assert auth_response.status_code == 302
    
    redirect_url_path = urlparse(auth_response.location).path
    token_str = redirect_url_path.split('/')[-1]

    download_response = client.get(f'/download?token={token_str}')
    assert download_response.status_code == 200
    assert "default-template-for-auth|dl-user" in download_response.data.decode('utf-8')

    with app.app_context():
        token_record = db.session.query(DownloadToken).filter_by(token=token_str).first()
        assert token_record.collected is True # type: ignore
        assert token_record.ovpn_content is None # type: ignore

    second_download_response = client.get(f'/download?token={token_str}')
    assert second_download_response.status_code == 403

def test_security_headers_are_present(client):
    """
    Tests that Flask-Talisman is adding security headers to responses.
    """
    response = client.get('/healthz', base_url='https://localhost')
    
    assert response.status_code == 200
    # Check for HSTS (Strict-Transport-Security)
    assert 'Strict-Transport-Security' in response.headers
    # Check for clickjacking protection
    assert response.headers['X-Frame-Options'] == 'SAMEORIGIN'
    # Check for MIME-type sniffing protection
    assert response.headers['X-Content-Type-Options'] == 'nosniff'

def test_index_page(client):
    """Tests that the public index page loads."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"<h1>OVPN Manager</h1>" in response.data
    assert b"Please use the client or an authorized link to download your configuration." in response.data
    assert b"<a href=\"/login\">Login to get a new OVPN profile</a></p>" in response.data

def test_download_landing_page(client, mocker):
    """Tests that the download landing page renders correctly."""
    # We don't need a real token, just need to build the URL
    response = client.get('/download-landing/fake-token')
    assert response.status_code == 200
    # Check for the key elements: the meta refresh tag and the link
    assert b'<meta http-equiv="refresh" content="3;url=/download?token=fake-token" />' in response.data
    assert b'<a href="/download?token=fake-token">' in response.data

def test_download_with_invalid_token(client):
    """Tests that a non-existent token is rejected."""
    response = client.get('/download?token=this-is-not-a-real-uuid')
    assert response.status_code == 403
    assert b"Access Forbidden" in response.data

def test_download_expired_token(client, app, mocker):
    """Tests that an expired token is rejected."""
    # We need to create an expired token manually
    with app.app_context():
        expired_token = DownloadToken(
            token="expired-token",  # type: ignore
            user="user",  # type: ignore
            cn="cn", # type: ignore
            created_at=datetime.now(timezone.utc) - timedelta(minutes=10) # type: ignore
        )
        db.session.add(expired_token)
        db.session.commit()
    
    response = client.get('/download?token=expired-token')
    assert response.status_code == 403
    assert b"Access Forbidden" in response.data
