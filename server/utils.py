import os
import jinja2
from cryptography.fernet import Fernet
from flask import current_app
from typing import Union, Dict, Any, List
from .extensions import oauth

def get_fernet():
    """Gets the Fernet instance, creating it if it doesn't exist on the app context."""
    # Use a key on the app config to cache the object per-app-instance
    if 'fernet_instance' not in current_app.config:
        try:
            encryption_key = os.environ["ENCRYPTION_KEY"]
            current_app.config['fernet_instance'] = Fernet(encryption_key.encode('utf-8'))
        except KeyError:
            raise RuntimeError("ENCRYPTION_KEY must be set for data encryption.")
    return current_app.config['fernet_instance']

def get_oidc_client():
    """
    Gets the registered OIDC client from the oauth extension.
    """
    # getattr is used to safely access the attribute which is added dynamically
    # by the .register() call in the app factory.
    client = getattr(oauth, 'oidc', None)
    if client is None:
        raise RuntimeError("OIDC client not registered or initialized on the oauth object.")
    return client

def get_ca_certs():
    """Gets the CA certs, creating them if they don't exist on the app context."""
    if 'ca_certs' not in current_app.config:
        try:
            ca_cert_path = os.environ["CA_CERT_PATH"]
            ca_key_path = os.environ["CA_KEY_PATH"]
            # Local import to prevent circular dependencies at startup
            from .cert_utils import load_ca
            current_app.config['ca_certs'] = load_ca(ca_cert_path, ca_key_path)
        except (KeyError, FileNotFoundError):
            raise RuntimeError("CA_CERT_PATH and CA_KEY_PATH must be set and valid")
    return current_app.config['ca_certs']

def load_ovpn_templates(path):
    """Scans a directory for .ovpn template files and loads them in priority order."""
    if not os.path.isdir(path):
        print(f"WARNING: OVPN template path '{path}' not found or not a directory.")
        return []
    
    loaded_templates = []
    for filename in os.listdir(path):
        if not filename.endswith(".ovpn"):
            continue
        
        parts = filename.split('.', 2)
        if len(parts) == 3 and parts[0].isdigit():
            priority = int(parts[0])
            group_name = parts[1]
            with open(os.path.join(path, filename), 'r') as f:
                content = f.read()
            loaded_templates.append({
                "priority": priority,
                "group_name": group_name,
                "file_name": filename,
                "template": jinja2.Template(content)
            })
    
    return sorted(loaded_templates, key=lambda x: x['priority'])

def render_ovpn_template(user_groups, context):
    """Finds the best matching template from the app config and renders it."""
    templates = current_app.config.get("OVPNS_TEMPLATES", [])
    
    user_groups_lower = {group.lower() for group in (user_groups or [])}
    
    best_template_info = None
    for tpl in templates:
        if tpl['group_name'].lower() in user_groups_lower:
            best_template_info = tpl
            break
            
    if not best_template_info:
        default_templates = [tpl for tpl in templates if tpl['group_name'] == 'default']
        if not default_templates:
            raise RuntimeError("OVPN template configuration error: no 'default' template found.")
        best_template_info = default_templates[0]

    cn = context["common_name"]
    print(f'For cert: {cn} use {best_template_info["file_name"]}')
    return best_template_info['template'].render(context)

def normalize_userinfo(raw_userinfo: Union[object, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Takes a raw userinfo object (which supports .get()) and returns a
    clean, consistent dictionary containing only the claims we care about.
    """
    clean_data: Dict[str, Any] = {}
    
    # This list acts as a whitelist for the claims we will process.
    wanted_keys = [
        'sub', 'email', 'name', 'first_name', 
        'given_name', 'family_name', 'organisational_unit', 'groups'
    ]
    
    for key in wanted_keys:
        value = getattr(raw_userinfo, 'get', lambda k, d=None: d)(key)
        if value is not None:
            clean_data[key] = value

    # Ensure 'groups' key always exists and is a list.
    clean_data['groups'] = clean_data.get('groups') or []
        
    return clean_data
