import os
import subprocess
import logging

log = logging.getLogger(__name__)

class RunCommand:
    """
    This class handles running commands, and stores the results and/or raises exceptions.

    It is a class mainly so we can store the values for later recall without needing to return
    a tuple or dictionary.
    """
    command = ''
    cwd = ''
    running_env = {}
    stdout = []
    stderr = []
    exit_code = 999

    def __init__(self, command: list = [], cwd = None, env = None, raise_on_error: bool = False, logger = None):
        self.logger = logger or log
        self.RunCommand(command, cwd, env, raise_on_error)

    def __repr__(self) -> str:
        return f"Command: {self.command}\nDirectory: {self.cwd if not None else '{current directory}'}\nEnv: {self.running_env}\nExit Code: {self.exit_code}\nstdout: {self.stdout}\nstderr: {self.stderr}"

    def RunCommand(self, command: list = [], cwd = None, env = None, raise_on_error: bool = False):
        """
        Execute the actual command
        """
        self.command = command
        self.cwd = cwd

        self.running_env = os.environ.copy()

        if env is not None and len(env) > 0:
            for env_item in env.keys():
                self.running_env[env_item] = env[env_item]
        self.logger.debug(f'exec: {" ".join(command)}')
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
                env=self.running_env
            )
            # Store the result because it worked just fine!
            self.exit_code = 0
            self.stdout = (result.stdout or "").splitlines()
            self.stderr = (result.stderr or "").splitlines()
        except subprocess.CalledProcessError as e:
            # Or store the result from the exception(!)
            self.exit_code = e.returncode
            self.stdout = (e.stdout or "").splitlines()
            self.stderr = (e.stderr or "").splitlines()

        # If verbose mode is on, output the results and errors from the command execution
        if len(self.stdout) > 0:
            self.logger.debug(f'stdout: {"\n".join(self.stdout)}')
        if len(self.stderr) > 0:
            self.logger.debug(f'stderr: {"\n".join(self.stderr)}')

        # If it failed and we want to raise an exception on failure, record the command and args
        # then Raise Away!
        if raise_on_error and self.exit_code > 0:
            command_string = None
            args = []
            for element in command:
                if not command_string:
                    command_string = element
                else:
                    args.append(element)

            raise RuntimeError(
                f'Error ({self.exit_code}) running command {command_string} with arguments {args}\nstderr: {self.stderr}\nstdout: {self.stdout}')

