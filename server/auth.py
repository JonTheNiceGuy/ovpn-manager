import uuid
import user_agents
from flask import Blueprint, session, redirect, url_for, request, abort, current_app
from .extensions import db, oauth, limiter
from .models import DownloadToken
from .cert_utils import create_device_certificate
from .utils import get_fernet, get_ca_certs, render_ovpn_template, normalize_userinfo, get_tlscrypt_key
from cryptography.hazmat.primitives import serialization

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login')
@limiter.limit("20/minute")
def login():
    chosen_optionset = request.args.get('optionset', 'default')
    session['optionset'] = chosen_optionset
    
    cli_port = request.args.get('cli_port')
    if cli_port:
        try:
            int(cli_port)
            session['cli_port'] = cli_port
        except (ValueError, TypeError):
            abort(400, "Invalid 'cli_port' provided.")
    
    redirect_uri = url_for('auth.auth', _external=True)
    return oauth.oidc.authorize_redirect(redirect_uri)

@auth_bp.route('/auth')
def auth():
    try:
        token = oauth.oidc.authorize_access_token()
        user_info = normalize_userinfo(token.get('userinfo'))
    except Exception as e:
        current_app.logger.error(f"Authentication error: {e}")
        return redirect(url_for('main.error_page', message="Authentication failed."))

    if not user_info or not user_info.get('sub'):
         return redirect(url_for('main.error_page', message="Could not retrieve user subject from token."))

    session['user'] = {'sub': user_info.get('sub'), 'groups': user_info.get('groups', [])}
    
    # Check if we need to redirect the user back to a protected admin page
    next_url = session.pop('next_url', None)
    if next_url:
        return redirect(next_url)

    # If no 'next_url', proceed with the standard OVPN generation flow
    try:
        fernet = get_fernet()
        ca_cert, ca_key = get_ca_certs()
        device_key_pem, device_cert_pem, common_name, cert_expiry = create_device_certificate(session['user']['sub'], ca_cert, ca_key)
        ca_cert_pem = ca_cert.public_bytes(encoding=serialization.Encoding.PEM)
        tlscrypt_type, tlscrypt_key = get_tlscrypt_key(device_cert_pem.decode('utf-8'))

        optionset_name = session.pop('optionset', 'default')
        optionsets = current_app.config.get("OVPNS_OPTIONSETS", {})
        optionset_content = optionsets.get(optionset_name, optionsets.get('default', ''))

        render_context = {
            "userinfo": user_info,
            "device_key_pem": device_key_pem.decode('utf-8'),
            "device_cert_pem": device_cert_pem.decode('utf-8'),
            "ca_cert_pem": ca_cert_pem.decode('utf-8'),
            "common_name": common_name,
            "optionset": optionset_content,
            "optionset_name": optionset_name,
            "tlscrypt_key": tlscrypt_key,
            "tlscrypt_type": tlscrypt_type
        }

        user_groups = user_info.get('groups', [])
        ovpn_content = render_ovpn_template(user_groups, render_context)

        encrypted_ovpn_content = fernet.encrypt(ovpn_content.encode('utf-8'))

        user_agent_string = request.headers.get('User-Agent', '')
        user_agent_parsed = user_agents.parse(user_agent_string)
        detected_os = user_agent_parsed.os.family

        download_token = str(uuid.uuid4())
        new_token = DownloadToken(
            token=download_token, # type: ignore
            ovpn_content=encrypted_ovpn_content, # type: ignore
            user=session['user']['sub'], # type: ignore
            cn=common_name, # type: ignore
            requester_ip=request.remote_addr, # type: ignore
            requester_user_agent=request.headers.get('User-Agent'), # type: ignore
            cert_expiry=cert_expiry, # type: ignore
            user_agent_string=user_agent_string, # type: ignore
            detected_os=detected_os, # type: ignore
            optionset_used=optionset_name, # type: ignore
            downloadable=True, # type: ignore
            collected=False # type: ignore
        )
        db.session.add(new_token)
        db.session.commit()

        cli_port = session.pop('cli_port', None)
        if cli_port:
            return redirect(f"http://localhost:{cli_port}/callback?token={download_token}")
        else:
            landing_url = url_for('main.download_landing', token=download_token)
            return redirect(landing_url)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Auth/Cert generation error: {e}")
        return redirect(url_for('main.error_page', message="Could not generate configuration file."))
