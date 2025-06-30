from server.extensions import db
from server.models import DownloadToken
from datetime import datetime, timezone, timedelta

def test_cleanup_tokens_task(client, app):
    """
    Tests the /tasks/cleanup-tokens endpoint to ensure it correctly
    deletes records older than the configured lifetime, while leaving
    newer records untouched.
    """
    with app.app_context():
        # Ensure a clean slate before starting
        db.session.query(DownloadToken).delete()

        # 1. Create a record that is very old and should be deleted
        #    (The default cleanup is 24 hours)
        db.session.add(
            DownloadToken(
                token="old-token", # type: ignore
                user="old.user@example.com", # type: ignore
                cn="cn-old", # type: ignore
                created_at=datetime.now(timezone.utc) - timedelta(hours=25) # type: ignore
            )
        )

        # 2. Create a newer record that should NOT be deleted
        db.session.add(
            DownloadToken(
                token="new-token", # type: ignore
                user="new.user@example.com", # type: ignore
                cn="cn-new", # type: ignore
                created_at=datetime.now(timezone.utc) - timedelta(hours=1) # type: ignore
            )
        )
        db.session.commit()

        # Confirm both records are in the DB before the cleanup
        assert db.session.query(DownloadToken).count() == 2

    # 3. Call the cleanup endpoint via a POST request
    response = client.post('/tasks/cleanup-tokens')
    assert response.status_code == 200
    # Check the JSON response for the count of deleted items
    assert response.json == {"message": "Cleanup successful. Deleted 1 records older than 24 hours."}

    # 4. Verify the database state after cleanup
    with app.app_context():
        assert db.session.query(DownloadToken).count() == 1
        remaining_token = db.session.query(DownloadToken).first()
        # Assert that only the new token remains
        assert remaining_token.token == "new-token" # type: ignore
