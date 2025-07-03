import pytest
import os
import yaml
from pathlib import Path
from click.testing import CliRunner
from client.client import get_config, Config, RECEIVED_TOKEN
import requests

def create_mock_config(fs, path: Path, content: dict):
    """A helper function to safely create mock config files in the fake filesystem."""
    fs.create_file(path, contents=yaml.dump(content))

def test_config_resolution_hierarchy(fs):
    """
    Tests the full precedence order for all configuration options
    using an isolated filesystem and constructor injection.
    """
    # 1. Setup the fake filesystem and paths.
    home_dir = Path.home()
    mock_user_config_path = home_dir / ".config" / "ovpn-manager" / "config.yaml"
    mock_system_config_path = Path("/etc/ovpn-manager/config.yaml")

    create_mock_config(fs, mock_user_config_path, {'server': 'http://user.config', 'overwrite': False})
    create_mock_config(fs, mock_system_config_path, {'server': 'http://system.config', 'overwrite': True})

    # 2. Run assertions by creating Config instances with injected test paths
    
    # Test Case: System config is used when no user config is provided
    cfg = Config(None, None, False, None, _user_config_path=Path('/nonexistent'), _system_config_path=mock_system_config_path)
    assert cfg.server_url == "http://system.config"
    assert cfg.overwrite is True

    # Test Case: User config overrides System config
    cfg = Config(None, None, False, None, _user_config_path=mock_user_config_path, _system_config_path=mock_system_config_path)
    assert cfg.server_url == "http://user.config"
    assert cfg.overwrite is False

    # Test Case: CLI flag overrides everything
    cfg = Config("http://cli.flag", None, True, None, _user_config_path=mock_user_config_path, _system_config_path=mock_system_config_path)
    assert cfg.server_url == "http://cli.flag"
    assert cfg.overwrite is True

def test_config_default_output_path(mocker):
    """Tests that the default output path is correctly determined."""
    fake_downloads = Path.home() / "My Downloads"
    mocker.patch('client.client.user_downloads_path', return_value=fake_downloads)
    
    cfg = Config(None, None, False, None)
    
    assert cfg.output_path == fake_downloads / "config.ovpn"

def test_config_bad_yaml_file(fs, capsys):
    """Tests that a corrupt YAML file is handled gracefully."""
    user_config_path = Path.home() / ".config/ovpn-manager/config.yaml"
    fs.create_file(user_config_path, contents="server: http://valid.url\n  bad: indent")
    
    cfg = Config(None, None, False, None, _user_config_path=user_config_path)
    
    captured = capsys.readouterr()
    assert "Warning: Could not read or parse config file" in captured.err
    assert cfg.server_url is None

def test_pre_flight_overwrite_logic(mocker):
    """Tests the file overwrite check directly."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("my.ovpn").touch()
        result = runner.invoke(get_config, ['-o', 'my.ovpn', '-s', 'http://dummy.url'])
        assert result.exit_code != 0
        assert "already exists. Use --force to overwrite." in result.output

def test_get_config_timeout_fails(mocker):
    """Tests that the main function exits if the browser auth times out."""
    RECEIVED_TOKEN.clear()
    runner = CliRunner()
    # Mock just enough to get to the timeout loop
    mocker.patch('client.client.Config', return_value=mocker.Mock(
        server_url='http://example.com',
        output_path=Path("test.ovpn"),
        overwrite=True
    ))
    mocker.patch('client.client.find_free_port', return_value=12345)
    mocker.patch('webbrowser.open')
    mocker.patch('time.time', side_effect=[0, 1, 130]) # t0, t1, t2 > timeout
    
    result = runner.invoke(get_config)
    assert result.exit_code != 0
    assert "Authentication timed out." in result.output

def test_get_config_download_request_fails(mocker):
    """Tests that a failure to download the file is handled."""
    RECEIVED_TOKEN.clear()
    runner = CliRunner()
    # Mock everything to get to the download step
    mocker.patch('client.client.Config', return_value=mocker.Mock(
        server_url='http://example.com',
        output_path=Path("test.ovpn"),
        overwrite=True,
        optionset='default' # provide the new required attribute
    ))
    mocker.patch('client.client.find_free_port', return_value=12345)
    mocker.patch('webbrowser.open', side_effect=lambda *a, **kw: RECEIVED_TOKEN.append("fake-token"))
    mocker.patch('requests.get', side_effect=requests.RequestException("Connection failed"))
    
    result = runner.invoke(get_config)
    assert result.exit_code != 0
    assert "Failed to download file: Connection failed" in result.output