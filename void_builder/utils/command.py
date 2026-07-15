import subprocess
import os
import sys
from typing import Optional, List, Dict, Tuple

class CommandRunner:
    @staticmethod
    def run(
        command: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        check: bool = True,
        capture_output: bool = True,
        stream: bool = False,
        silent_errors: bool = False
    ) -> Tuple[int, str, str]:
        """
        Runs a shell command and returns (returncode, stdout, stderr).
        
        Args:
            command: Command and arguments as a list
            cwd: Working directory
            env: Environment variables
            check: Raise exception on non-zero exit code
            capture_output: Capture stdout/stderr
            stream: Stream output in real-time
            silent_errors: Do not print [ERROR] if return code is non-zero
            
        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        cmd_str = ' '.join(command)
        if not silent_errors:
            print(f"\033[1m[CMD]\033[0m {cmd_str}")
        
        try:
            if stream:
                # Stream output in real-time
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=subprocess.PIPE if capture_output else None,
                    stderr=subprocess.PIPE if capture_output else None,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                stdout_lines = []
                stderr_lines = []
                
                if capture_output:
                    # Read stdout and stderr in real-time
                    for line in process.stdout:
                        print(line, end='')
                        stdout_lines.append(line)
                    for line in process.stderr:
                        print(line, end='', file=sys.stderr)
                        stderr_lines.append(line)
                
                process.wait()
                returncode = process.returncode
                stdout = ''.join(stdout_lines)
                stderr = ''.join(stderr_lines)
            else:
                # Capture all output at once
                result = subprocess.run(
                    command,
                    cwd=cwd,
                    env=env,
                    check=False,  # We'll handle check ourselves
                    text=True,
                    capture_output=capture_output
                )
                returncode = result.returncode
                stdout = result.stdout if capture_output else ''
                stderr = result.stderr if capture_output else ''
            
            if returncode != 0:
                if not silent_errors:
                    print(f"\033[91m[ERROR]\033[0m Command failed with exit code {returncode}")
                    if stderr:
                        print(f"\033[91m[STDERR]\033[0m {stderr}")
                if check:
                    raise subprocess.CalledProcessError(
                        returncode, cmd_str, stdout, stderr
                    )
            
            return (returncode, stdout, stderr)
            
        except FileNotFoundError as e:
            print(f"\033[91m[ERROR]\033[0m Command not found: {command[0]}")
            if check:
                raise
            return (127, '', str(e))
        except Exception as e:
            print(f"\033[91m[ERROR]\033[0m Unexpected error: {e}")
            if check:
                raise
            return (1, '', str(e))
    
    @staticmethod
    def run_shell(
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        check: bool = True
    ) -> Tuple[int, str, str]:
        """Runs a shell command string (not a list)."""
        print(f"\033[1m[SHELL]\033[0m {command}")
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                env=env,
                check=False,
                text=True,
                capture_output=True
            )
            
            if result.returncode != 0 and check:
                print(f"\033[91m[ERROR]\033[0m Command failed with exit code {result.returncode}")
                if result.stderr:
                    print(f"\033[91m[STDERR]\033[0m {result.stderr}")
                raise subprocess.CalledProcessError(
                    result.returncode, command, result.stdout, result.stderr
                )
            
            return (result.returncode, result.stdout, result.stderr)
            
        except Exception as e:
            print(f"\033[91m[ERROR]\033[0m Unexpected error: {e}")
            if check:
                raise
            return (1, '', str(e))

