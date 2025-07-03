import os
import jinja2
from pathlib import Path
from tempfile import TemporaryDirectory
from cryptography.fernet import Fernet
from flask import Flask, current_app
from typing import Union, Dict, Any, List
from .extensions import oauth
from authlib.oidc.core.claims import UserInfo
from .runcommand import RunCommand

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

def get_tlscrypt_key(device_cert: str) -> tuple[int | None, str | None]:
    """
    Reads a tls-crypt key file and returns the key type and content.
    For V2 keys, it generates the client-specific key.
    """
    tlscrypt_key_path = os.environ.get("TLSCRYPT_KEY_PATH")
    if not tlscrypt_key_path:
        return None, None

    try:
        with open(tlscrypt_key_path, "r") as f:
            key_content = f.read()
    except FileNotFoundError:
        raise RuntimeError(f"TLSCRYPT_KEY_PATH '{tlscrypt_key_path}' does not exist")

    if key_content.startswith('-----BEGIN OpenVPN Static key V1-----'):
        return 1, key_content
    elif key_content.startswith('-----BEGIN OpenVPN tls-crypt-v2 server key-----'):
        from .runcommand import RunCommand # Local import
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as d:
            temp_filename = Path(d) / 'cert.pem'
            
            # Pass the logger from the current app context to RunCommand
            RunCommand(
                [
                    "openvpn",
                    "--tls-crypt-v2", tlscrypt_key_path,
                    "--genkey", "tls-crypt-v2-client",
                    str(temp_filename)
                ],
                raise_on_error=True,
                logger=current_app.logger
            )
            with open(temp_filename, 'r') as f:
                client_key = f.read()
            return 2, client_key.strip()
    else:
        raise RuntimeError('TLSCRYPT_KEY is not valid')

# def get_tlscrypt_key(device_cert):
#     tlscrypt_key_path = os.environ.get("TLSCRYPT_KEY_PATH", None)
#     this_tlscrypt_key = None
#     if tlscrypt_key_path:
#         if 'tlscrypt_key' in current_app.config: # This stores the V1 key which is the same between client and server
#             this_tlscrypt_key = current_app.config.get('tlscrypt_key')
#         else:
#             if 'tlscrypt_server_key' in current_app.config: # This stores the V2 Server key
#                 tlscrypt_key = current_app.config.get('tlscrypt_server_key')
#             else:
#                 try:
#                     tlscrypt_key_path = os.environ["TLSCRYPT_KEY_PATH"]
#                     with open(tlscrypt_key_path, "r") as f:
#                         tlscrypt_key = f.read()
#                 except (FileNotFoundError):
#                     raise RuntimeError("TLSCRYPT_KEY_PATH must exist")

#             # The file we loaded is either a V1 or V2 key, or something else
#             if str(tlscrypt_key).startswith('-----BEGIN OpenVPN Static key V1-----'):
#                 current_app.config['tlscrypt_type']=1
#                 current_app.config['tlscrypt_key'] = tlscrypt_key
#                 this_tlscrypt_key = tlscrypt_key

#             elif str(tlscrypt_key).startswith('-----BEGIN OpenVPN tls-crypt-v2 server key-----'):
#                 # We now need to generate the V2 Client key
#                 current_app.config['tlscrypt_type']=2
#                 with TemporaryDirectory() as d:
#                     temp_filename = Path(d) / 'cert'
#                     with open(temp_filename, 'w') as f:
#                         f.write(device_cert)
#                     get_client_key = RunCommand(
#                         [
#                             "openvpn",
#                             "--genkey", "tls-crypt-v2-client",
#                             os.environ["TLSCRYPT_KEY_PATH"], # Server Certificate
#                             temp_filename                    # Client Certificate
#                         ]
#                     )
#                 this_tlscrypt_key = "\n".join(get_client_key.stdout)

#             else:
#                 raise RuntimeError('TLSCRYPT_KEY is not valid')

#     return current_app.config.get('tlscrypt_type', None), this_tlscrypt_key

def load_ovpn_templates(app: Flask):
    """Scans a directory for .ovpn template files and loads them in priority order."""
    path = app.config.get("OVPN_TEMPLATES_PATH", "server/templates/ovpn")
    app.logger.info(f"Loading OVPN templates from {path}")
    if not os.path.isdir(path):
        app.logger.error(f"WARNING: OVPN template path '{path}' not found or not a directory.")
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
                "content": content
            })
    result = sorted(loaded_templates, key=lambda x: x['priority'])
    app.logger.debug(f'Loaded templates: {result}')
    return result

def render_ovpn_template(user_groups: List[str], context: Dict[str, Any]) -> str:
    """Finds the best matching template and renders it with the given context."""
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

    main_template_content = best_template_info['content']
    current_app.logger.debug(f'Loaded template pre-render is:')
    current_app.logger.debug(main_template_content)

    # We will now use this content to build the final template.
    optionset_name = context.get("optionset_name", "default")
    optionsets = current_app.config.get("OVPNS_OPTIONSETS", {})
    optionset_content = optionsets.get(optionset_name, optionsets.get('default', ''))

    current_app.logger.info(f"For cert: {context['common_name']} use {best_template_info['file_name']} with optionset {optionset_name}.opts")

    current_app.logger.debug(f'Loaded optionset pre-render is:')
    current_app.logger.debug(optionset_content)

    final_template_string = optionset_content + "\n" + main_template_content

    current_app.logger.debug(f'Combined pre-render template is:')
    current_app.logger.debug(final_template_string)

    final_template = jinja2.Template(final_template_string)
    rendered_template = final_template.render(context)

    current_app.logger.debug(f'Rendered Output is:')
    current_app.logger.debug(rendered_template)    
    
    return rendered_template

def normalize_userinfo(raw_userinfo: Union[UserInfo, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Takes a raw userinfo object (which supports .get()) and returns a
    clean, consistent dictionary containing only the claims we care about.
    """
    # for key, value in raw_userinfo.items():
    current_app.logger.debug(f'userinfo: {raw_userinfo}')

    clean_data: Dict[str, Any] = dict(raw_userinfo)
    clean_data['groups'] = clean_data.get('groups') or []
        
    return clean_data

def load_ovpn_optionsets(app: Flask) -> Dict[str, str]:
    """Scans a directory for .opts files and loads their content."""
    path = app.config.get("OVPNS_OPTIONSETS_PATH", "server/optionsets")
    app.logger.info(f"Loading OVPN optionsets from {path}")
    optionsets = {}
    if not os.path.isdir(path):
        app.logger.error(f"WARNING: OVPN optionsets path '{path}' not found or not a directory.")
        return optionsets
    
    for filename in os.listdir(path):
        if not filename.endswith(".opts"):
            continue
        
        # Key is the filename without extension, e.g., "UseTCP"
        key = os.path.splitext(filename)[0]
        with open(os.path.join(path, filename), 'r') as f:
            optionsets[key] = f.read()
            
    if 'default' not in optionsets:
        raise RuntimeError(f"OVPN optionset configuration error: no 'default.opts' file found in '{path}'.")
    
    app.logger.debug(f"Loaded optionsets: {list(optionsets.keys())}")
        
    return optionsets
