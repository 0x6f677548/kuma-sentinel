"""
Shared Pydantic models for Kuma-Scout configuration.

These models define the structure for global configuration and shared components
used across all plugins.
"""

from typing import Optional

from pydantic import BaseModel, Field


class SSHConfig(BaseModel):
    """SSH connection configuration."""

    host: str = Field(description="SSH host (user@host or host)")
    user: Optional[str] = Field(default=None, description="SSH username")
    port: int = Field(default=22, description="SSH port")
    key_file: Optional[str] = Field(default=None, description="Path to SSH private key")
    password: Optional[str] = Field(
        default=None, description="SSH password (discouraged)"
    )
    strict_host_key_checking: bool = Field(default=True, description="Verify host keys")


class UptimeKumaConfig(BaseModel):
    """Uptime Kuma configuration."""

    url: str = Field(description="Uptime Kuma push API URL")
    token: Optional[str] = Field(
        default=None, description="Uptime Kuma push token (can be overridden per check)"
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Logging level")
    file: Optional[str] = Field(default=None, description="Log file path")


class RetryConfig(BaseModel):
    """Retry configuration."""

    attempts: int = Field(
        default=0, ge=0, le=10, description="Number of retry attempts on failure"
    )
    delay_seconds: int = Field(
        default=5, ge=0, le=300, description="Delay between retry attempts (seconds)"
    )


class HeartbeatConfig(BaseModel):
    """Heartbeat service configuration."""

    enabled: bool = Field(default=True, description="Enable heartbeat pings")
    interval: int = Field(
        default=300, ge=1, description="Heartbeat interval in seconds"
    )
    token: Optional[str] = Field(
        default=None, description="Uptime Kuma token for heartbeat"
    )


class GlobalConfig(BaseModel):
    """
    Global configuration loaded from YAML.

    These settings apply to all checks unless overridden.
    """

    uptime_kuma: Optional[UptimeKumaConfig] = Field(
        default=None, description="Uptime Kuma settings"
    )
    logging: LoggingConfig = Field(
        default_factory=lambda: LoggingConfig(), description="Logging settings"
    )
    ignore_file_permissions: bool = Field(
        default=False, description="Skip permission checks"
    )
    ssh: Optional[SSHConfig] = Field(default=None, description="Default SSH settings")
    heartbeat: HeartbeatConfig = Field(
        default_factory=HeartbeatConfig, description="Heartbeat settings"
    )
    checks: list[dict] = Field(
        default_factory=list, description="List of check configurations"
    )
