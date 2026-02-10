"""Shared data models for scout checks."""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class CheckResult:
    """Result of a check operation.

    Attributes:
        check_name: Name of the check (e.g., "portscan")
        status: Status to report ("up" or "down")
        message: Human-readable message
        duration_seconds: How long the check took to execute
        details: Additional metadata for the check (optional)
        tags: Tags associated with this check for aggregation (optional)
        plugin_type: Type of plugin that generated this result (optional)
    """

    check_name: str
    status: str
    message: str
    duration_seconds: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    plugin_type: str = ""

    def __post_init__(self):
        """Validate status field."""
        if self.status not in ("up", "down"):
            raise ValueError(f"Status must be 'up' or 'down', got '{self.status}'")
