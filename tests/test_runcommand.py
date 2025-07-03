import pytest
import subprocess
from unittest.mock import MagicMock
from server.runcommand import RunCommand

def test_runcommand_success(mocker):
    """
    Tests that RunCommand correctly captures output from a successful command.
    """
    # 1. Mock the subprocess.run call
    mock_result = MagicMock()
    mock_result.stdout = "line 1\nline 2"
    mock_result.stderr = "error line"
    mock_result.returncode = 0
    mocker.patch('subprocess.run', return_value=mock_result)

    # 2. Execute the command via our class
    cmd = ["ls", "-l"]
    runner = RunCommand(cmd)

    # 3. Assert the results were stored correctly
    assert runner.exit_code == 0
    assert runner.stdout == ["line 1", "line 2"]
    assert runner.stderr == ["error line"]
    assert runner.command == cmd

def test_runcommand_failure_no_raise(mocker):
    """
    Tests that RunCommand correctly captures output from a failed command
    when 'raise_on_error' is False.
    """
    # 1. Mock subprocess.run to raise a CalledProcessError
    error = subprocess.CalledProcessError(
        returncode=1,
        cmd=["git", "status"],
        output="fatal: not a git repository\n",
        stderr="error details"
    )
    mocker.patch('subprocess.run', side_effect=error)

    # 2. Execute the command
    runner = RunCommand(["git", "status"], raise_on_error=False)

    # 3. Assert the error details were stored correctly
    assert runner.exit_code == 1
    assert runner.stdout == ["fatal: not a git repository"]
    assert runner.stderr == ["error details"]

def test_runcommand_failure_with_raise(mocker):
    """
    Tests that RunCommand correctly raises a RuntimeError on failure
    when 'raise_on_error' is True.
    """
    # 1. Mock the failure
    error = subprocess.CalledProcessError(returncode=127, cmd=["badcommand"])
    mocker.patch('subprocess.run', side_effect=error)

    # 2. Assert that a RuntimeError is raised when the class is instantiated
    with pytest.raises(RuntimeError, match=r"Error \(127\) running command badcommand.*"):
        RunCommand(["badcommand"], raise_on_error=True)