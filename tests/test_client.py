import pytest
import os
import yaml
from pathlib import Path
from click.testing import CliRunner
from client.client import get_config, RECEIVED_TOKEN, Config

# --- Helper to create mock config files within a given base directory ---
def create_mock_config(base_path: Path, content: dict):
    base_path.parent.mkdir(parents=True, exist_ok=True)
    with base_path.open('w') as f:
        yaml.dump(content, f)

def test_config_server_url_hierarchy(mocker):
    """Tests the full precedence for resolving the server URL step-by-step."""
    with CliRunner().isolated_filesystem() as fs:
        fs_root = Path(fs)
        
        # 1. Define mock paths inside our isolated filesystem
        home_dir = fs_root / "home" / "testuser"
        mock_user_config_path = home_dir / ".config/ovpn-manager/config.yaml"
        mock_system_config_path = fs_root / "etc/ovpn-manager/config.yaml"
        
        # Mock Path.home() so our class can find the user config
        mocker.patch('pathlib.Path.home', return_value=home_dir)

        # === Test 1: No configuration exists ===
        cfg = Config(None, None, False, mock_user_config_path, mock_system_config_path)
        assert cfg.server_url is None

        # === Test 2: Only system config exists ===
        create_mock_config(mock_system_config_path, {"server": "http://system.config"})
        cfg = Config(None, None, False, mock_user_config_path, mock_system_config_path)
        assert cfg.server_url == "http://system.config"

        # === Test 3: User config overrides system config ===
        create_mock_config(mock_user_config_path, {"server": "http://user.config"})
        cfg = Config(None, None, False, mock_user_config_path, mock_system_config_path)
        assert cfg.server_url == "http://user.config"

        # === Test 4: Environment variable overrides user config ===
        mocker.patch.dict(os.environ, {"OVPN_MANAGER_URL": "http://env.var"})
        cfg = Config(None, None, False, mock_user_config_path, mock_system_config_path)
        assert cfg.server_url == "http://env.var"

        # === Test 5: CLI flag overrides everything ===
        cfg = Config("http://cli.flag", None, False, mock_user_config_path, mock_system_config_path)
        assert cfg.server_url == "http://cli.flag"

def test_config_output_path_home_expansion(mocker):
    """Tests that home-dir shortcuts in config files are correctly expanded."""
    with CliRunner().isolated_filesystem() as fs:
        # Define a fake home directory for the test
        home_dir = Path(fs) / "home" / "testuser"
        home_dir.mkdir(parents=True, exist_ok=True)
        
        # Tell the test environment where our fake home is
        mocker.patch('os.path.expanduser', lambda p: str(p).replace('~', str(home_dir)))
        
        # Now, initialize the Config class. It will use the real code, but
        # our mock will intercept the expanduser call.
        cfg = Config(None, "~/some/path/config.ovpn", False)
        
        assert cfg.output_path == home_dir / "some" / "path" / "config.ovpn"

def test_pre_flight_overwrite_logic(mocker):
    """Tests the file overwrite check directly."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Create a file that should block the script
        Path("my.ovpn").touch()

        # --- Part 1: Run without the overwrite flag (should fail) ---
        result_fail = runner.invoke(get_config, ['-o', 'my.ovpn', '-s', 'http://dummy.url'])
        assert result_fail.exit_code != 0
        assert "already exists. Use --force to overwrite." in result_fail.output

        # --- Part 2: Run WITH the overwrite flag (should pass the check) ---
        # Mock the next function in the sequence to halt execution gracefully
        # after our check has passed.
        mock_find_port = mocker.patch('client.client.find_free_port')

        runner.invoke(get_config, ['-o', 'my.ovpn', '-s', 'http://dummy.url', '--force'])

        # Assert that the script got past the overwrite check and called our mock.
        # This proves the check was successful.
        mock_find_port.assert_called_once()
