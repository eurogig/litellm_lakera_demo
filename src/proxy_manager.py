"""Manages LiteLLM proxy server lifecycle."""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests

# Try to import psutil for better process management
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class ProxyManager:
    """Manages the LiteLLM proxy server process."""

    PROXY_URL = "http://localhost:4000"
    PROXY_HEALTH_ENDPOINT = f"{PROXY_URL}/health"
    PROXY_PORT = 4000

    def __init__(self, config_path: str = "config.yaml", litellm_path: Optional[str] = None):
        """Initialize the proxy manager.

        Args:
            config_path: Path to the LiteLLM config.yaml file
            litellm_path: Path to the litellm directory (if running from source)
        """
        self.config_path = Path(config_path).absolute()
        self.litellm_path = Path(litellm_path) if litellm_path else None
        self.process: Optional[subprocess.Popen] = None

    def is_running(self) -> bool:
        """Check if the proxy server is running.

        Returns:
            True if the proxy is running and healthy, False otherwise
        """
        try:
            response = requests.get(self.PROXY_HEALTH_ENDPOINT, timeout=2)
            return response.status_code == 200
        except (requests.exceptions.RequestException, requests.exceptions.Timeout):
            return False

    def start(self, wait_for_ready: bool = True, timeout: int = 30) -> bool:
        """Start the LiteLLM proxy server.

        Args:
            wait_for_ready: Whether to wait for the proxy to be ready
            timeout: Maximum time to wait for proxy to be ready (seconds)

        Returns:
            True if the proxy started successfully, False otherwise
        """
        if self.is_running():
            print("LiteLLM proxy is already running.")
            return True

        if not self.config_path.exists():
            print(f"Error: Config file not found: {self.config_path}")
            return False

        # Determine the command to run
        if self.litellm_path and self.litellm_path.exists():
            # Running from cloned source - need to ensure litellm is in Python path
            # The litellm package should be installed with pip install -e ./litellm
            # So we can use the module directly
            cmd = [sys.executable, "-m", "litellm.proxy.proxy_cli", "--config", str(self.config_path)]
        else:
            # Assume litellm is installed as a package
            cmd = ["litellm", "--config", str(self.config_path)]

        print(f"Starting LiteLLM proxy server with config: {self.config_path}")
        print(f"Command: {' '.join(cmd)}")

        # Start the process
        env = os.environ.copy()
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            bufsize=1,
        )

        if wait_for_ready:
            print("Waiting for proxy to be ready...")
            start_time = time.time()
            output_lines = []
            
            # Read output while waiting
            while time.time() - start_time < timeout:
                if self.process.poll() is not None:
                    # Process has exited, read remaining output
                    remaining = self.process.stdout.read()
                    if remaining:
                        output_lines.append(remaining)
                    break
                
                # Try to read a line (non-blocking)
                try:
                    line = self.process.stdout.readline()
                    if line:
                        line = line.strip()
                        output_lines.append(line)
                        # Print important messages
                        if any(keyword in line.lower() for keyword in ['error', 'exception', 'traceback', 'failed']):
                            print(f"  {line}")
                        elif 'running' in line.lower() or 'started' in line.lower() or 'uvicorn' in line.lower():
                            print(f"  {line}")
                except:
                    pass
                
                if self.is_running():
                    print(f"✓ LiteLLM proxy is running at {self.PROXY_URL}")
                    return True
                time.sleep(0.5)

            # If we got here, proxy didn't start
            print(f"✗ Proxy failed to start within {timeout} seconds")
            
            # Show error output
            if output_lines:
                print("\nProxy output:")
                for line in output_lines[-20:]:  # Show last 20 lines
                    if line:
                        print(f"  {line}")
            
            # Check if process exited with error
            if self.process.poll() is not None:
                exit_code = self.process.returncode
                print(f"\nProxy process exited with code: {exit_code}")
            
            self.stop()
            return False

        return True

    def stop(self) -> None:
        """Stop the LiteLLM proxy server."""
        print("Stopping LiteLLM proxy server...")
        stopped = False
        
        # Stop the process we started
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
                stopped = True
            except subprocess.TimeoutExpired:
                self.process.kill()
                stopped = True
            self.process = None
        
        # Find and stop all proxy processes
        if HAS_PSUTIL:
            try:
                current_pid = os.getpid()
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        if proc.info['pid'] == current_pid:
                            continue  # Don't kill ourselves
                        cmdline = proc.info.get('cmdline', [])
                        if not cmdline:
                            continue
                        cmdline_str = ' '.join(str(arg) for arg in cmdline)
                        # Check if this is a proxy_cli process
                        if 'proxy_cli' in cmdline_str or 'litellm.proxy.proxy_cli' in cmdline_str:
                            print(f"  Stopping proxy process {proc.info['pid']}...")
                            try:
                                proc_obj = psutil.Process(proc.info['pid'])
                                proc_obj.terminate()
                                try:
                                    proc_obj.wait(timeout=3)
                                    stopped = True
                                except psutil.TimeoutExpired:
                                    proc_obj.kill()
                                    stopped = True
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
            except Exception as e:
                print(f"  Warning: Could not stop processes with psutil: {e}")
        
        # Also use lsof to find and kill processes on port 4000 (more reliable)
        try:
            result = subprocess.run(
                ['lsof', '-ti', f':{self.PROXY_PORT}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid and pid.isdigit():
                        try:
                            print(f"  Stopping process {pid} on port {self.PROXY_PORT}...")
                            os.kill(int(pid), 15)  # SIGTERM
                            time.sleep(0.5)
                            # If still running, force kill
                            try:
                                os.kill(int(pid), 0)  # Check if still exists
                                os.kill(int(pid), 9)  # SIGKILL
                            except ProcessLookupError:
                                pass  # Already dead
                            stopped = True
                        except (ProcessLookupError, PermissionError):
                            pass
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Also try to find processes by name using pgrep/ps
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'proxy_cli'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid and pid.isdigit() and int(pid) != os.getpid():
                        try:
                            print(f"  Stopping proxy process {pid}...")
                            os.kill(int(pid), 15)  # SIGTERM
                            time.sleep(0.5)
                            try:
                                os.kill(int(pid), 0)  # Check if still exists
                                os.kill(int(pid), 9)  # SIGKILL
                            except ProcessLookupError:
                                pass
                            stopped = True
                        except (ProcessLookupError, PermissionError):
                            pass
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        if stopped:
            # Wait a moment for the port to be released
            time.sleep(1)
            print("✓ Proxy server stopped")
        elif self.is_running():
            print("✗ Warning: Proxy is still running. You may need to stop it manually.")
            print(f"  Try: lsof -ti :{self.PROXY_PORT} | xargs kill")

    def ensure_running(self) -> bool:
        """Ensure the proxy is running, starting it if necessary.

        Returns:
            True if the proxy is running, False otherwise
        """
        if not self.is_running():
            return self.start()
        return True

