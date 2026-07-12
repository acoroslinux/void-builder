import subprocess
import os

class CommandRunner:
    @staticmethod
    def run(command, cwd=None, env=None, check=True):
        """Runs a shell command and returns the output."""
        print(f"Running: {' '.join(command)}")
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                check=check,
                text=True,
                capture_output=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"Command failed with exit code {e.returncode}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            raise
