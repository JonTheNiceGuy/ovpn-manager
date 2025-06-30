from urllib.parse import urlparse
from server.extensions import db
from server.models import DownloadToken

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
        assert token_record.collected is True
        assert token_record.ovpn_content is None

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