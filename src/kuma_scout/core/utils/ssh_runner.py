"""SSH command execution utility for remote command execution."""

import shlex
import subprocess
from typing import List, Optional, Tuple

from kuma_scout.core.logger import get_logger, log_security_event


class SSHConnectionError(Exception):
    """Exception raised when SSH connection fails (authentication, host unreachable, etc.)."""

    def __init__(self, message: str, stderr: str = ""):
        self.message = message
        self.stderr = stderr
        super().__init__(f"SSH connection failed: {message}")


class SSHRunner:
    """Execute commands via SSH using subprocess.

    This class provides a simple interface for running commands on remote
    hosts via SSH. It uses subprocess to invoke the system ssh command,
    which respects the user's SSH config (~/.ssh/config) and known_hosts.

    Example:
        runner = SSHRunner(host="backup-server", user="root")
        success, stdout, stderr = runner.run(["kopia", "snapshot", "list", "/data"])
    """

    def __init__(
        self,
        host: str,
        user: Optional[str] = None,
        port: int = 22,
        key_file: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
        strict_host_key_checking: bool = True,
    ):
        """Initialize SSH runner.

        Args:
            host: SSH hostname or IP address
            user: SSH username (default: current user)
            port: SSH port (default: 22)
            key_file: Path to SSH private key file
            password: SSH password (discouraged, use keys instead)
            timeout: Command timeout in seconds (default: 30)
            strict_host_key_checking: Verify host keys (default: True)
        """
        self.host = host
        self.user = user
        self.port = port
        self.key_file = key_file
        self.password = password
        self.timeout = timeout
        self.strict_host_key_checking = strict_host_key_checking

        # Log security event if host key checking is disabled
        if not self.strict_host_key_checking:
            logger = get_logger()
            log_security_event(
                logger,
                "ssh_host_key_checking_disabled",
                f"SSH host key checking disabled for host {self.host} - connections may be vulnerable to man-in-the-middle attacks",
                level="warning"
            )

    def build_ssh_command(self, remote_cmd: List[str]) -> List[str]:
        """Build the SSH command with options.

        Args:
            remote_cmd: Command to execute on remote host as list of arguments

        Returns:
            List of SSH command arguments
        """
        ssh_cmd = ["ssh"]

        # Host key checking
        if self.strict_host_key_checking:
            ssh_cmd.extend(["-o", "StrictHostKeyChecking=yes"])
        else:
            ssh_cmd.extend(["-o", "StrictHostKeyChecking=no"])
            ssh_cmd.extend(["-o", "UserKnownHostsFile=/dev/null"])

        # Disable pseudo-terminal allocation (not needed for monitoring)
        ssh_cmd.extend(["-T"])

        # Port
        ssh_cmd.extend(["-p", str(self.port)])

        # Key file
        if self.key_file:
            ssh_cmd.extend(["-i", self.key_file])

        # Target host
        target = f"{self.user}@{self.host}" if self.user else self.host
        ssh_cmd.append(target)

        # Remote command (properly escaped)
        ssh_cmd.append(shlex.join(remote_cmd))

        return ssh_cmd

    def _is_ssh_connection_error(self, stderr: str) -> bool:
        """Check if stderr contains SSH connection error messages.

        Args:
            stderr: Standard error output from SSH command

        Returns:
            True if stderr contains SSH connection error patterns
        """
        connection_error_patterns = [
            "connection closed by",
            "permission denied",
            "host key verification failed",
            "ssh: connect to host",
            "network is unreachable",
            "no route to host",
            "connection refused",
            "connection timed out",
            "authentication failed",
            "publickey,password",  # Common when both auth methods fail
            "tailnet policy does not permit",  # Tailscale specific
        ]

        stderr_lower = stderr.lower()
        return any(pattern in stderr_lower for pattern in connection_error_patterns)

    def _log_ssh_auth_failure(self, stderr: str) -> None:
        """Log security event for SSH authentication failures."""
        if "permission denied" in stderr.lower() or "authentication failed" in stderr.lower():
            logger = get_logger()
            log_security_event(
                logger,
                "ssh_authentication_failed",
                f"SSH authentication failed for user {self.user or 'current_user'}@{self.host}",
                level="warning"
            )

    def run(
        self, cmd: List[str], timeout: Optional[int] = None
    ) -> Tuple[bool, str, str, int]:
        """Run command via SSH.

        Args:
            cmd: Command to execute on remote host as list of arguments
            timeout: Optional timeout override in seconds

        Returns:
            Tuple of (success: bool, stdout: str, stderr: str, exit_code: int)
        """
        ssh_cmd = self.build_ssh_command(cmd)

        timeout = timeout or self.timeout

        # If password is provided, use sshpass (if available)
        if self.password:
            # SECURITY: Use environment variable instead of command line argument
            # to prevent password exposure in process lists (ps/top)
            import os

            logger = get_logger()
            log_security_event(
                logger,
                "ssh_password_authentication_used",
                f"SSH password authentication used for host {self.host} - consider using SSH key authentication instead",
                level="warning"
            )

            # Try to use sshpass with environment variable (more secure than -p flag)
            # Set password in environment variable for sshpass
            env = os.environ.copy()
            env["SSHPASS"] = self.password

            ssh_cmd = ["sshpass", "-e"] + ssh_cmd

            try:
                result = subprocess.run(
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env=env,  # Pass modified environment
                )
                # Check for SSH connection errors
                if result.returncode != 0 and self._is_ssh_connection_error(
                    result.stderr
                ):
                    self._log_ssh_auth_failure(result.stderr)
                    raise SSHConnectionError(
                        result.stderr or "Connection failed", result.stderr
                    )
                return (
                    result.returncode == 0,
                    result.stdout,
                    result.stderr,
                    result.returncode,
                )
            except subprocess.TimeoutExpired:
                return False, "", f"Command timed out after {timeout}s", -1
            except SSHConnectionError:
                raise  # Re-raise SSH connection errors
            except Exception as e:
                return False, "", str(e), -1

        # No password - use standard SSH
        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            # Check for SSH connection errors
            if result.returncode != 0 and self._is_ssh_connection_error(result.stderr):
                self._log_ssh_auth_failure(result.stderr)
                raise SSHConnectionError(
                    result.stderr or "Connection failed", result.stderr
                )
            return (
                result.returncode == 0,
                result.stdout,
                result.stderr,
                result.returncode,
            )
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout}s", -1
        except SSHConnectionError:
            raise  # Re-raise SSH connection errors
        except Exception as e:
            return False, "", str(e), -1


def parse_ssh_connection_string(
    conn_str: str,
) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """Parse various SSH connection string formats.

    Supported formats:
    - ssh://user@host:port
    - user@host:port
    - user@host
    - host:port
    - host

    Args:
        conn_str: SSH connection string

    Returns:
        Tuple of (host, user, port) where any may be None
    """
    if not conn_str:
        return None, None, None

    # Handle ssh:// URL format
    if conn_str.startswith("ssh://"):
        conn_str = conn_str[6:]  # Remove ssh:// prefix

    # Handle user@host:port format
    if ":" in conn_str and "@" in conn_str:
        # Split on last colon to handle IPv6 addresses correctly
        user_host, port_str = conn_str.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            # Not a valid port, treat the whole thing as host
            return conn_str, None, None

        if "@" in user_host:
            user, host = user_host.rsplit("@", 1)
            return host, user, port
        else:
            # host:port format
            return user_host, None, port

    # Handle user@host format
    elif "@" in conn_str:
        user, host = conn_str.rsplit("@", 1)
        return host, user, None

    # Handle host:port format
    elif ":" in conn_str:
        host, port_str = conn_str.rsplit(":", 1)
        try:
            port = int(port_str)
            return host, None, port
        except ValueError:
            # Not a valid port, treat as just host
            return conn_str, None, None

    # Handle just host
    else:
        return conn_str, None, None
