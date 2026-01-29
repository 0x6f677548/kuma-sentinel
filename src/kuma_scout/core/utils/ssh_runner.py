"""SSH command execution utility for remote command execution."""

import shlex
import subprocess
from typing import List, Optional, Tuple


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
            # Try to use sshpass for password authentication
            # This is discouraged but supported for legacy systems
            ssh_cmd = ["sshpass", "-p", self.password] + ssh_cmd

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
