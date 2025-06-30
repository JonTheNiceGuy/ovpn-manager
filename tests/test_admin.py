from server.models import DownloadToken
from server.extensions import db
from datetime import datetime, timezone, timedelta

OIDC_CLIENT_PATH = 'server.extensions.oauth.oidc'

def test_admin_page_is_forbidden_for_normal_user(client, mocker):
    """Tests that a user NOT in the admin group receives a 403 Forbidden."""
    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')
    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|normal-user', 'groups': ['some-other-group']}
    }
    with client:
        client.get('/auth')
        response = client.get('/admin/status')
        assert response.status_code == 403
        assert b"Access Forbidden" in response.data

def test_admin_page_is_accessible_for_admin_user(client, mocker):
    """Tests that a user who IS in the admin group receives a 200 OK."""
    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')
    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|admin-user', 'groups': ['vpn-admins']}
    }
    with client:
        client.get('/auth')
        response = client.get('/admin/status')
        assert response.status_code == 200
        assert b"Token Issuance Status" in response.data

def test_admin_page_filtering(client, app, mocker):
    """
    Tests that the filtering and time limit options on the admin status page work correctly.
    """
    mock_authorize_access_token = mocker.patch(f'{OIDC_CLIENT_PATH}.authorize_access_token')
    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|admin-user', 'groups': ['vpn-admins']}
    }
    with client:
        # Log in as an admin user to get a valid session
        client.get('/auth')

        # Create a varied set of test data in a clean database state
        with app.app_context():
            db.session.query(DownloadToken).delete()
            db.session.add(
                DownloadToken(
                    token="token-collected", # type: ignore
                    user="user1", # type: ignore
                    cn="cn-collected", # type: ignore
                    collected=True, # type: ignore
                    downloadable=False # type: ignore
                )
            )
            db.session.add(
                DownloadToken(
                    token="token-downloadable", # type: ignore
                    user="user2", # type: ignore
                    cn="cn-downloadable", # type: ignore
                    collected=False, # type: ignore
                    downloadable=True # type: ignore
                )
            )
            db.session.add(
                DownloadToken(
                    token="token-2-days-old", # type: ignore
                    user="user3", # type: ignore
                    cn="cn-2-days-old", # type: ignore
                    created_at=datetime.now(timezone.utc) - timedelta(days=2), # type: ignore
                    collected=False, # type: ignore
                    downloadable=True # type: ignore
                )
            )
            db.session.commit()

        # Scenario 1: Filter for 'collected' tokens from all time
        response = client.get('/admin/status?filter_by=collected&time_limit=all')
        assert response.status_code == 200
        response_data = response.data.decode('utf-8')
        assert "cn-collected" in response_data
        assert "cn-downloadable" not in response_data
        assert "cn-2-days-old" not in response_data

        # Scenario 2: Filter for 'downloadable' tokens from all time
        # --- THIS IS THE FIX ---
        # We explicitly ask for 'all' time to prevent the '1d' default from interfering.
        response = client.get('/admin/status?filter_by=downloadable&time_limit=all')
        assert response.status_code == 200
        response_data = response.data.decode('utf-8')
        assert "cn-collected" not in response_data
        assert "cn-downloadable" in response_data
        assert "cn-2-days-old" in response_data

        # Scenario 3: Filter for 'downloadable' tokens within the last 12 hours
        response = client.get('/admin/status?filter_by=downloadable&time_limit=12h')
        assert response.status_code == 200
        response_data = response.data.decode('utf-8')
        assert "cn-collected" not in response_data
        assert "cn-downloadable" in response_data
        assert "cn-2-days-old" not in response_data

def test_unauthenticated_admin_redirect_flow(client, mocker):
    """
    Tests that a non-logged-in user visiting an admin page is redirected
    to login, and then back to the admin page after success.
    """
    # 1. Try to access the admin page without being logged in
    response = client.get('/admin/status')
    assert response.status_code == 302
    assert response.location == '/login'

    # 2. Now, simulate the OIDC login, as if the user was sent there
    mock_authorize_access_token = mocker.patch('server.extensions.oauth.oidc.authorize_access_token')
    mock_authorize_access_token.return_value = {
        'userinfo': {'sub': 'auth|admin-user', 'groups': ['vpn-admins']}
    }
    
    # The 'with client' block ensures we are using the same session that
    # now contains the 'next_url' from the first request.
    with client:
        # Call the /auth callback
        auth_response = client.get('/auth')
        
        # 3. Assert that the FINAL redirect goes back to the original destination
        assert auth_response.status_code == 302
        assert auth_response.location == '/admin/status'
