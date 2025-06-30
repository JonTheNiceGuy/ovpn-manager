import os
from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import timedelta

from .extensions import db, migrate, oauth, limiter, talisman, sess
from .models import DownloadToken
from .main_routes import main_bp
from .auth import auth_bp
from .admin import admin_bp
from .tasks import tasks_bp
from .utils import load_ovpn_templates

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    
    # --- Load Configuration ---
    app.secret_key = os.getenv("FLASK_SECRET_KEY")
    db_url = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(app.instance_path, 'app.db')}")
    if "sqlite" in db_url:
        os.makedirs(app.instance_path, exist_ok=True)
        
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # --- Session Configuration ---
    app.config["SESSION_TYPE"] = "sqlalchemy"
    app.config["SESSION_SQLALCHEMY"] = db
    app.config["SESSION_PERMANENT"] = True
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

    # --- Load OVPN Templates ---
    template_path = os.getenv("OVPN_TEMPLATES_PATH", "server/templates/ovpn")
    app.config["OVPNS_TEMPLATES"] = load_ovpn_templates(template_path)
    if not app.config["OVPNS_TEMPLATES"]:
        raise RuntimeError(f"No OVPN templates found in '{template_path}'.")

    # --- Initialize Extensions (in the correct order) ---
    db.init_app(app)
    migrate.init_app(app, db)
    sess.init_app(app)
    oauth.init_app(app)
    talisman.init_app(app, force_https=False, content_security_policy=None)
    
    storage_url = os.getenv("RATELIMIT_STORAGE_URL", "memory://")
    app.config["RATELIMIT_STORAGE_URI"] = storage_url
    limiter.init_app(app)

    # --- Register OIDC Client ---
    oauth.register(
        name='oidc',
        server_metadata_url=os.getenv("OIDC_DISCOVERY_URL"),
        client_id=os.getenv("OIDC_CLIENT_ID"),
        client_secret=os.getenv("OIDC_CLIENT_SECRET"),
        client_kwargs={'scope': 'openid email profile groups'}
    )

    # --- Register Blueprints ---
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(tasks_bp, url_prefix='/tasks')

    # --- Register Custom Error Handlers ---
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('403.html'), 403

    return app