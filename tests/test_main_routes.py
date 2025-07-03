from urllib.parse import urlparse
from server.extensions import db
from server.models import DownloadToken
from datetime import datetime, timezone, timedelta

OIDC_CLIENT_PATH = 'server.extensions.oauth.oidc'

def test_index_redirects_unauthenticated_user(client, app):
    """
    Tests that an unauthenticated user hitting the root path (/)
    is correctly redirected to the login page.
    """
    response = client.get('/')
    assert response.status_code == 302
    # Assert that it redirects to the correct login URL
    assert response.location == '/login'

def test_index_page_loads_for_authenticated_user(client):
    """
    Tests that the public index page loads successfully FOR AN AUTHENTICATED USER.
    """
    with client.session_transaction() as sess:
        sess['user'] = {'sub': 'test|user', 'groups': []}
    response = client.get('/')
    assert response.status_code == 200
    assert b"<h1>OVPN Manager</h1>" in response.data
    assert b"Click here for advanced options" in response.data
    assert b'<input type="radio" id="option-default" name="optionset"' in response.data

def test_nav_bar_shows_admin_link_when_user_is_not_admin(client, mocker):
    """
    Tests that the 'Admin' link in the navigation bar only appears for users
    in the configured admin group.
    """
    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')
    admin_link = b'<a href="/admin/">Admin</a>'

    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|normal-user', 'groups': ['some-other-group']}
    }
    with client:
        client.get('/auth')
        response = client.get('/')
        assert response.status_code == 200
        assert admin_link not in response.data

def test_nav_bar_shows_admin_link_when_user_is_an_admin(client, mocker):
    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')
    admin_link = b'<a href="/admin/">Admin</a>'
    # Scenario 2: User IS in the admin group
    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|admin-user', 'groups': ['vpn-admins']}
    }
    with client:
        client.get('/auth')
        response = client.get('/')
        assert response.status_code == 200
        assert admin_link in response.data

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

def test_error_page_is_rendered_on_auth_exception(client, mocker):
    """
    Tests that a generic exception during the auth process correctly
    redirects to the user-facing error page.
    """
    OIDC_CLIENT_PATH = 'server.extensions.oauth.oidc'
    
    # Mock the OIDC client to raise a generic exception
    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')
    mock_authorize_access_token.side_effect = Exception("A generic error occurred")

    # Call the /auth endpoint, which should now fail and redirect
    response = client.get('/auth', follow_redirects=True)
    
    # Assert we landed on the error page with the correct content and status
    assert response.status_code == 400
    assert b"<h1>An Error Occurred</h1>" in response.data
    assert b"Authentication failed." in response.data # Check for the message we passed
