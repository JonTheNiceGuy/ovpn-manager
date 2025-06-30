from flask import Blueprint
import os
from datetime import datetime, timezone, timedelta
from .extensions import db, limiter
from .models import DownloadToken

tasks_bp = Blueprint('tasks', __name__)

@tasks_bp.route('/cleanup-tokens', methods=['POST'])
@limiter.limit("5/hour")
def cleanup_tokens():
    """
    A dedicated endpoint for PERMANENTLY DELETING old token records.
    This should be called periodically by a scheduler like a Kubernetes CronJob.
    """
    token_lifetime_hours = int(os.getenv("TOKEN_LIFETIME_HOURS", "24"))
    cleanup_threshold = datetime.now(timezone.utc) - timedelta(hours=token_lifetime_hours)
    
    try:
        num_deleted = db.session.query(DownloadToken).filter(
            DownloadToken.created_at < cleanup_threshold
        ).delete()
        db.session.commit()
        return {"message": f"Cleanup successful. Deleted {num_deleted} records older than {token_lifetime_hours} hours."}, 200
    except Exception as e:
        db.session.rollback()
        return {"message": "An error occurred during cleanup.", "error": str(e)}, 500