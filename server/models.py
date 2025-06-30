from datetime import datetime, timezone, timedelta
from .extensions import db

class DownloadToken(db.Model):
    __tablename__ = 'download_tokens'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user = db.Column(db.String(255), nullable=False, index=True)
    cn = db.Column(db.String(255), nullable=True, index=True)
    requester_ip = db.Column(db.String(45), nullable=True)
    requester_user_agent = db.Column(db.Text, nullable=True)
    cert_expiry = db.Column(db.DateTime(timezone=True), nullable=True)
    user_agent_string = db.Column(db.String(255), nullable=True)
    detected_os = db.Column(db.String(50), nullable=True)
    ovpn_content = db.Column(db.LargeBinary, nullable=True)
    downloadable = db.Column(db.Boolean, nullable=False, default=True)
    collected = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    def is_download_window_expired(self):
        created_at_utc = self.created_at
        if created_at_utc.tzinfo is None:
            created_at_utc = created_at_utc.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > created_at_utc + timedelta(minutes=5)
