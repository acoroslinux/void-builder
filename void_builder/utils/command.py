import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple, Union


class CommandRunner:
    @staticmethod
    def run(
        command: List[Union[str, Any]],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        check: bool = True,
        capture_output: bool = True,
        stream: bool = False,
        silent_errors: bool = False
    ) -> Tuple[int, str, str]:
        """
        Runs a command and returns (returncode, stdout, stderr).
        
        Args:
            command: Command and arguments as a list of strings/Paths
            cwd: Working directory
            env: Environment variables
            check: Raise exception on non-zero exit code
            capture_output: Capture stdout/stderr
            stream: Stream output in real-time
            silent_errors: Do not print [ERROR] if return code is non-zero
            
        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        command_str_list = [str(c) for c in command]
        cmd_str = ' '.join(command_str_list)
        if not silent_errors:
            print(f"\033[1m[CMD]\033[0m {cmd_str}")
        
        try:
            if stream:
                import threading
                # Stream output in real-time concurrently using threads to avoid pipe buffer deadlock
                process = subprocess.Popen(
                    command_str_list,
                    cwd=cwd,
                    env=env,
                    stdout=subprocess.PIPE if capture_output else None,
                    stderr=subprocess.PIPE if capture_output else None,
                    text=True,
                    errors="replace",
                    bufsize=1
                )
                
                stdout_lines: List[str] = []
                stderr_lines: List[str] = []
                
                def _stream_reader(pipe, out_stream, lines_acc):
                    if not pipe:
                        return
                    for line in iter(pipe.readline, ''):
                        if out_stream:
                            print(line, end='', file=out_stream)
                        lines_acc.append(line)
                    pipe.close()

                t_out = threading.Thread(target=_stream_reader, args=(process.stdout, sys.stdout if capture_output else None, stdout_lines))
                t_err = threading.Thread(target=_stream_reader, args=(process.stderr, sys.stderr if capture_output else None, stderr_lines))
                
                t_out.start()
                t_err.start()
                t_out.join()
                t_err.join()
                
                process.wait()
                returncode = process.returncode
                stdout = ''.join(stdout_lines)
                stderr = ''.join(stderr_lines)
            else:
                # Capture all output at once
                result = subprocess.run(
                    command_str_list,
                    cwd=cwd,
                    env=env,
                    check=False,
                    text=True,
                    errors="replace",
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
            cmd_name = command_str_list[0] if command_str_list else '<empty>'
            print(f"\033[91m[ERROR]\033[0m Command not found: {cmd_name}")
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
                errors="replace",
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
