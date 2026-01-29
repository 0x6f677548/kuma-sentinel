"""SSH command execution utility for remote command execution."""

import shlex
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple

from kuma_scout.core.logger import get_logger


@dataclass
class SSHConfig:
    """SSH configuration with parsing capabilities."""

    host: Optional[str] = None
    user: Optional[str] = None
    port: Optional[int] = None
    key_file: Optional[str] = None
    password: Optional[str] = None
    strict_host_key_checking: bool = True

    @classmethod
    def from_connection_string(cls, connection_string: str) -> "SSHConfig":
        """Create SSHConfig from connection string.

        Args:
            connection_string: SSH connection string in supported formats

        Returns:
            SSHConfig instance with parsed values
        """
        host, user, port = parse_ssh_connection_string(connection_string)
        return cls(host=host, user=user, port=port)

    def update_from_connection_string(self, connection_string: str) -> None:
        """Update this config from a connection string.

        Only sets values that are not already set (None).
        """
        host, user, port = parse_ssh_connection_string(connection_string)
        if host and self.host is None:
            self.host = host
        if user and self.user is None:
            self.user = user
        if port and self.port is None:
            self.port = port

    def is_complete(self) -> bool:
        """Check if config has minimum required fields for SSH connection."""
        return self.host is not None


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

    def run(self, cmd: List[str]) -> Tuple[bool, str, str]:
        """Run command via SSH.

        Args:
            cmd: Command to execute on remote host as list of arguments

        Returns:
            Tuple of (success: bool, stdout: str, stderr: str)
        """
        ssh_cmd = self.build_ssh_command(cmd)

        # If password is provided, use sshpass (if available)
        if self.password:
            # SECURITY: Use environment variable instead of command line argument
            # to prevent password exposure in process lists (ps/top)
            import os
            
            logger = get_logger()
            logger.warning(
                "⚠️  SECURITY WARNING: Using SSH password authentication. "
                "Password may be exposed in process list (ps/top) even with environment variable method. "
                "Please use SSH key authentication instead."
            )
            
            # Try to use sshpass with environment variable (more secure than -p flag)
            # Set password in environment variable for sshpass
            env = os.environ.copy()
            env['SSHPASS'] = self.password
            
            ssh_cmd = ["sshpass", "-e"] + ssh_cmd
            
            try:
                result = subprocess.run(
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env=env,  # Pass modified environment
                )
                return result.returncode == 0, result.stdout, result.stderr
            except subprocess.TimeoutExpired:
                return False, "", f"Command timed out after {self.timeout}s"
            except Exception as e:
                return False, "", str(e)
        
        # No password - use standard SSH
        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {self.timeout}s"
        except Exception as e:
            return False, "", str(e)


def parse_ssh_shorthand(ssh: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Parse SSH shorthand format (user@host or just host).

    Args:
        ssh: SSH shorthand string (e.g., "root@server" or "server")

    Returns:
        Tuple of (host, user) where either may be None
    """
    if not ssh:
        return None, None
    if "@" in ssh:
        user, host = ssh.rsplit("@", 1)
        return host, user
    return ssh, None


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
