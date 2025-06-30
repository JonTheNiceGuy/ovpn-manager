import pytest
import requests
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

def test_config_resolution_hierarchy(fs):
    """
    Tests the full precedence order for all configuration options.
    """
    # 1. Setup the fake filesystem. pyfakefs automatically mocks Path.home().
    home_dir = Path.home()
    user_config_path = home_dir / ".config" / "ovpn-manager" / "config.yaml"
    system_config_path = Path("/etc/ovpn-manager/config.yaml")

    # Use a helper to create the fake files
    user_config_path.parent.mkdir(parents=True, exist_ok=True)
    with user_config_path.open('w') as f:
        yaml.dump({'server': 'http://user.config', 'output': 'user.ovpn', 'overwrite': False}, f)

    system_config_path.parent.mkdir(parents=True, exist_ok=True)
    with system_config_path.open('w') as f:
        yaml.dump({'server': 'http://system.config', 'output': 'system.ovpn', 'overwrite': True}, f)
    
    # 2. Run assertions by creating Config instances with injected test paths
    
    # Test Case: System config is used when no user config is provided
    cfg = Config(None, None, False, _user_config_path=Path('/nonexistent'), _system_config_path=system_config_path)
    assert cfg.server_url == "http://system.config"
    assert cfg.overwrite is True

    # Test Case: User config overrides System config
    cfg = Config(None, None, False, _user_config_path=user_config_path, _system_config_path=system_config_path)
    assert cfg.server_url == "http://user.config"
    assert cfg.overwrite is False

    # Test Case: Env var overrides User config
    os.environ['OVPN_MANAGER_URL'] = 'http://env.var'
    cfg = Config(None, None, False, _user_config_path=user_config_path, _system_config_path=system_config_path)
    assert cfg.server_url == 'http://env.var'
    del os.environ['OVPN_MANAGER_URL'] # Clean up env

    # Test Case: CLI flag overrides everything
    cfg = Config("http://cli.flag", "cli.ovpn", True, _user_config_path=user_config_path, _system_config_path=system_config_path)
    assert cfg.server_url == "http://cli.flag"
    assert cfg.output_path == Path("cli.ovpn").expanduser()
    assert cfg.overwrite is True

def test_config_default_output_path(mocker, fs):
    """Tests that the default output path is correctly determined."""
    fake_downloads = Path.home() / "My Downloads"
    mocker.patch('client.client.user_downloads_path', return_value=fake_downloads)

    cfg = Config(None, None, False)
    
    assert cfg.output_path == fake_downloads / "config.ovpn"
    # The Config class should have created the directory
    assert fake_downloads.is_dir()

def test_config_bad_yaml_file(fs, capsys):
    """Tests that a corrupt YAML file is handled gracefully."""
    user_config_path = Path.home() / ".config" / "ovpn-manager" / "config.yaml"
    user_config_path.parent.mkdir(parents=True, exist_ok=True)
    # Write invalid YAML
    user_config_path.write_text("server: http://valid.url\n  bad: indent")
    
    cfg = Config(None, None, False, _user_config_path=user_config_path)
    
    # Assert that a warning was printed to stderr
    captured = capsys.readouterr()
    assert "Warning: Could not read or parse config file" in captured.err
    # Assert that it fell back to defaults
    assert cfg.server_url is None

def test_get_config_timeout_fails(mocker):
    """Tests that the main function exits if the browser auth times out."""
    runner = CliRunner()
    # Mock everything needed to get to the timeout loop
    mocker.patch('client.client.Config', **{
        'return_value.server_url': 'http://example.com',
        'return_value.output_path': Path("test.ovpn"),
        'return_value.overwrite': True,
    })
    mocker.patch('client.client.find_free_port', return_value=12345)
    mocker.patch('webbrowser.open')
    mocker.patch('time.time', side_effect=[0, 1, 130]) # First call is 0, second is 1, third is 130
    
    result = runner.invoke(get_config)

    assert result.exit_code != 0
    assert "Authentication timed out." in result.output

def test_get_config_download_request_fails(mocker):
    """Tests that a failure to download the file is handled."""
    runner = CliRunner()
    # Mock everything to get to the download step
    mocker.patch('client.client.Config', **{
        'return_value.server_url': 'http://example.com',
        'return_value.output_path': Path("test.ovpn"),
        'return_value.overwrite': True,
    })
    mocker.patch('client.client.find_free_port', return_value=12345)
    mocker.patch('webbrowser.open', side_effect=lambda *a, **kw: RECEIVED_TOKEN.append("fake-token"))
    # Mock requests.get to fail
    mocker.patch('requests.get', side_effect=requests.RequestException("Connection failed"))
    
    result = runner.invoke(get_config)
    
    assert result.exit_code != 0
    assert "Failed to download file: Connection failed" in result.output