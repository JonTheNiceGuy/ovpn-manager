from flask import Blueprint, session, request, render_template, abort, url_for, redirect, current_app
from functools import wraps
import os
from .extensions import db, limiter
from .models import DownloadToken
from datetime import datetime, timedelta, timezone

admin_bp = Blueprint('admin', __name__, template_folder='templates')


def admin_required(f):
    """Decorator to ensure user is logged in and is a member of the OVPN admin group."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_group = os.getenv('OIDC_ADMIN_GROUP')
        if not admin_group:
            current_app.logger.warning("Admin access denied: OIDC_ADMIN_GROUP is not configured.")
            abort(403)
        
        if 'user' not in session:
            session['next_url'] = request.path
            return redirect(url_for('auth.login'))
        
        user_groups = session.get('user', {}).get('groups', [])
        if admin_group not in user_groups:
            # --- THIS IS THE NEW LOGGING ---
            user_sub = session.get('user', {}).get('sub')
            current_app.logger.warning(
                f"Admin access denied for user '{user_sub}'. "
                f"Required group: '{admin_group}'. User groups: {user_groups}"
            )
            abort(403)
            
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/')
@admin_required
def index():
    """Renders the admin index page."""
    # The template path is relative to the blueprint's 'template_folder'
    return render_template('admin/index.html')

@admin_bp.route('/status')
@limiter.limit("60/minute")
@admin_required
def status():
    query = DownloadToken.query
    filter_by = request.args.get('filter_by', 'all_records')
    time_limit = request.args.get('time_limit', '1d')

    if filter_by == 'downloadable':
        query = query.filter(DownloadToken.downloadable == True, DownloadToken.collected == False)
    elif filter_by == 'collected':
        query = query.filter(DownloadToken.collected == True)

    now = datetime.now(timezone.utc)
    time_filter_map = {
        '1h': timedelta(hours=1), '12h': timedelta(hours=12),
        '1d': timedelta(days=1), '1w': timedelta(days=7),
        '1m': timedelta(days=30), '6m': timedelta(days=180)
    }

    if time_limit in time_filter_map:
        query = query.filter(DownloadToken.created_at >= now - time_filter_map[time_limit])
    elif time_limit == 'expiring':
        query = query.filter(DownloadToken.cert_expiry.between(now, now + timedelta(days=30)))
    
    tokens = query.order_by(DownloadToken.created_at.desc()).limit(500).all()
    active_filters = {'filter_by': filter_by, 'time_limit': time_limit}
    
    return render_template('admin/admin_status.html', tokens=tokens, current_filters=active_filters)
