from flask import Blueprint, request, abort, Response, render_template_string, render_template, url_for, session, current_app, redirect
from .extensions import db
from .models import DownloadToken
from .utils import get_fernet
from cryptography.fernet import InvalidToken

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Renders the public home page."""
    if 'user' not in session:
        session['next_url'] = request.path
        return redirect(url_for('auth.login'))
    return render_template('index.html', session=session, config=current_app.config)

@main_bp.route('/download-landing/<token>')
def download_landing(token):
    download_url = url_for('main.download', token=token)
    return render_template('download_landing.html', download_url=download_url)

@main_bp.route('/download')
def download():
    fernet = get_fernet()
    token_str = request.args.get('token')
    if not token_str:
        abort(401, "Missing download token.")

    token_record = db.session.query(DownloadToken).filter_by(token=token_str).first()
    if token_record is None:
        abort(403, "Invalid download token.")

    if token_record.is_download_window_expired():
        token_record.downloadable = False
        token_record.ovpn_content = None
        db.session.commit()
        abort(403, "Download token has expired.")

    if token_record.collected:
        abort(403, "This download token has already been used.")
    if not token_record.downloadable:
        abort(403, "This token is not available for download.")

    try:
        decrypted_ovpn_content = fernet.decrypt(token_record.ovpn_content)
    except (InvalidToken, TypeError):
        abort(500, "Failed to decrypt configuration data.")

    token_record.collected = True
    token_record.downloadable = False
    token_record.ovpn_content = None
    db.session.commit()

    return Response(
        decrypted_ovpn_content,
        mimetype="application/x-openvpn-profile",
        headers={"Content-disposition": "attachment; filename=config.ovpn"}
    )

@main_bp.route('/error')
def error_page():
    # We will need the HTML_TEMPLATE here or define a proper template file
    message = request.args.get('message', 'An unknown error occurred.')
    return f"<h1>Error</h1><p>{message}</p>", 400

@main_bp.route('/healthz')
def healthz():
    return {"status": "ok"}, 200