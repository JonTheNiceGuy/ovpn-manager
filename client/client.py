#!/usr/bin/env python3
import os
import click
import requests
import webbrowser
import socket
import yaml
import time
import threading
from pathlib import Path
from platformdirs import user_downloads_path
from http.server import BaseHTTPRequestHandler, HTTPServer

# A simple list to act as a message queue between the server thread
# and the main thread.
RECEIVED_TOKEN = []

class Config:
    """
    Resolves client configuration from multiple sources in a defined order
    of precedence: CLI > Environment > User Config > System Config > Default.
    """

    def __init__(self, server_url_flag, output_flag, overwrite_flag, _user_config_path=None, _system_config_path=None):
        # Allow paths to be injected for testing, otherwise use real paths
        self.user_config_path = _user_config_path or (Path.home() / ".config" / "ovpn-manager" / "config.yaml")
        self.system_config_path = _system_config_path or Path("/etc/ovpn-manager/config.yaml")
        
        self.user_config = self._load_config_file(self.user_config_path)
        self.system_config = self._load_config_file(self.system_config_path)

        self.server_url = self._resolve_server_url(server_url_flag)
        self.output_path = self._resolve_output_path(output_flag)
        self.overwrite = self._resolve_overwrite_flag(overwrite_flag)

    def _load_config_file(self, path: Path):
        """Safely loads and parses a YAML file."""
        if path.is_file():
            try:
                with path.open('r') as f:
                    return yaml.safe_load(f) or {}
            except (yaml.YAMLError, IOError) as e:
                click.echo(f"Warning: Could not read or parse config file at {path}. Error: {e}", err=True)
        return {}

    def _resolve(self, cli_arg, env_var, config_key):
        """Generic resolver that checks CLI > ENV > User > System."""
        # 1. Command-line flag
        if cli_arg is not None:
            return cli_arg
        # 2. Environment variable
        if os.getenv(env_var):
            return os.getenv(env_var)
        # 3. User config file
        if self.user_config.get(config_key):
            return self.user_config.get(config_key)
        # 4. System config file
        if self.system_config.get(config_key):
            return self.system_config.get(config_key)
        return None

    def _resolve_server_url(self, cli_arg):
        url = self._resolve(cli_arg, 'OVPN_MANAGER_URL', 'server')
        if url:
            return url.rstrip('/')
        return None

    def _resolve_output_path(self, cli_arg):
        path_str = self._resolve(cli_arg, 'OVPN_MANAGER_OUTPUT', 'output')
        
        if path_str:
            # This is the standard, robust way to expand paths like ~/ or $HOME
            return Path(os.path.expanduser(path_str))
        else:
            # 5. Default value
            try:
                downloads_dir = user_downloads_path()
                if not downloads_dir:
                    # Fallback if platformdirs can't find it
                    downloads_dir = Path.home() / "Downloads"
                downloads_dir.mkdir(parents=True, exist_ok=True)
                return downloads_dir / "config.ovpn"
            except Exception:
                # Fallback for headless systems or strange environments
                return Path.home() / "config.ovpn"
                
    def _resolve_overwrite_flag(self, cli_arg):
        # The CLI flag is a boolean, so check if it's explicitly True
        if cli_arg:
            return True
        
        overwrite_str = self._resolve(None, 'OVPN_MANAGER_OVERWRITE', 'overwrite')
        if overwrite_str is not None:
            # Handle 'true', 'yes', '1' as True from env/config
            return str(overwrite_str).lower() in ['true', '1', 't', 'y', 'yes']
            
        return False

class CallbackHandler(BaseHTTPRequestHandler):
    """
    A simple HTTP request handler that captures the 'token' query parameter,
    sends a success page to the browser, and allows the server to shut down.
    """
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"""
            <html>
            <head><title>Authentication Success</title></head>
            <body onload="window.close()">
                <h1>Authentication successful!</h1>
                <p>You can close this browser tab now.</p>
                <script>window.close();</script>
            </body>
            </html>
        """)

        # Extract the token from the request path and store it globally.
        if 'token=' in self.path:
            token = self.path.split('token=')[1].split('&')[0]
            RECEIVED_TOKEN.append(token)

    def log_message(self, format, *args):
        return

def find_free_port():
    """Finds and returns an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        return s.getsockname()[1]

@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('-s', '--server-url', help='The base URL of the configuration server.')
@click.option('-o', '--output', help='Path to save the OVPN configuration file.')
@click.option('-f', '--force', '--overwrite', 'overwrite', is_flag=True, default=False, help='Overwrite the output file if it already exists.')
def get_config(server_url, output, overwrite):
    try:
        config = Config(server_url, output, overwrite)
    except Exception as e:
        raise click.ClickException(f"Failed to initialize configuration: {e}")

    if not config.server_url:
        raise click.ClickException("Server URL is not configured. Please provide it via the --server-url flag, OVPN_MANAGER_URL environment variable, or a config file.")

    if config.output_path.exists() and not config.overwrite:
        raise click.ClickException(f"Output file '{config.output_path}' already exists. Use --force to overwrite.")

    try:
        port = find_free_port()
    except OSError:
        raise click.ClickException("Could not find a free port for the local callback server.")

    click.echo(f"Starting temporary server on http://localhost:{port}...")
    httpd = HTTPServer(('localhost', port), CallbackHandler)
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    login_url = f"{server_url}/login?cli_port={port}"
    click.echo("Your browser has been opened to complete authentication.")
    webbrowser.open(login_url)

    click.echo("Waiting for authentication in browser... (will time out in 2 minutes)")
    timeout_seconds = 120
    start_time = time.time()
    while not RECEIVED_TOKEN:
        time.sleep(1)
        if time.time() - start_time > timeout_seconds:
            httpd.shutdown()
            raise click.ClickException("Authentication timed out.")

    httpd.shutdown()
    token = RECEIVED_TOKEN[0]
    click.echo("Authentication successful. Token received.")

    download_url = f"{config.server_url}/download?token={token}"
    click.echo(f"Downloading configuration from {config.server_url}...")
    try:
        response = requests.get(download_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        raise click.ClickException(f"Failed to download file: {e}")

    try:
        with open(config.output_path, 'wb') as f:
            f.write(response.content)
        click.secho(f"Successfully saved configuration to {config.output_path}", fg="green")
    except IOError as e:
        raise click.ClickException(f"Failed to write to file {config.output_path}: {e}")

if __name__ == '__main__':
    get_config()