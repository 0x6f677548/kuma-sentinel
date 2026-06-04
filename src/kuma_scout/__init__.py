"""Kuma Scout - Uptime Kuma monitoring agent."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("kuma-scout")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]
