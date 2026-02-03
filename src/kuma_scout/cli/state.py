"""Global CLI state for Kuma Scout."""

# Global state for callback options
state = {
    "log_level": "INFO",
    "log_file": None,
    "uptime_kuma_url": None,
    "uptime_kuma_token": None,
    "heartbeat_token": None,
    "timeout": 300,
    "ssh_host": None,
    "ssh_key_file": None,
    "ssh_password": None,
    "ssh_strict_host_key_checking": True,
    "ignore_file_permissions": False,
}
