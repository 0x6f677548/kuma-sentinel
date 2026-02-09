"""
Plugin system for Kuma-Scout monitoring checks.

This module provides automatic discovery and registration of monitoring plugins.
Each plugin is a single file that combines configuration, CLI generation, and execution logic.
"""

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Dict, Type

from .base import Plugin

# Global registry of discovered plugins
_PLUGIN_REGISTRY: Dict[str, Type[Plugin]] = {}


@lru_cache(maxsize=1)
def discover_plugins() -> Dict[str, Type[Plugin]]:
    """
    Automatically discover and register all plugins in this package.

    Returns:
        Dictionary mapping plugin names to plugin classes.
    """
    global _PLUGIN_REGISTRY

    if _PLUGIN_REGISTRY:  # Already discovered
        return _PLUGIN_REGISTRY

    # Get the plugins package path
    plugins_path = Path(__file__).parent

    # Find all Python files in the plugins directory (excluding __init__.py and base.py)
    for py_file in plugins_path.glob("*.py"):
        if py_file.name in ("__init__.py", "base.py", "models.py"):
            continue

        module_name = py_file.stem

        try:
            # Import the module
            module = importlib.import_module(f"kuma_scout.plugins.{module_name}")

            # Find plugin classes in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Plugin)
                    and attr != Plugin
                ):
                    # Register the plugin
                    plugin_name = getattr(attr, "name", None)
                    if plugin_name:
                        _PLUGIN_REGISTRY[plugin_name] = attr

        except Exception as e:
            # Log warning but continue with other plugins
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to load plugin {module_name}: {e}")

    return _PLUGIN_REGISTRY


def get_all_plugins() -> Dict[str, Type[Plugin]]:
    """
    Get all discovered plugins.

    Returns:
        Dictionary mapping plugin names to plugin classes.
    """
    return discover_plugins()
