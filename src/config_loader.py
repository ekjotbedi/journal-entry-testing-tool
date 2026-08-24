"""Load and validate the project configuration.

Keeping configuration loading in one place means every script (data
generation, testing, reporting) reads the exact same thresholds, which is
important for reproducible audit results.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

# Project root = parent of the ``src`` directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def load_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """Read the YAML config file and return it as a dictionary.

    Parameters
    ----------
    config_path:
        Optional path to a config file. Defaults to ``config/config.yaml``.

    Returns
    -------
    dict
        Parsed configuration.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    _validate(config)
    return config


def resolve_path(relative: str) -> Path:
    """Resolve a path from the config (relative to project root) to absolute."""
    return (PROJECT_ROOT / relative).resolve()


def _validate(config: Dict[str, Any]) -> None:
    """Light validation so a malformed config fails fast with a clear error."""
    required_sections = ["data_generation", "tests", "risk_weights", "paths"]
    missing = [s for s in required_sections if s not in config]
    if missing:
        raise ValueError(
            f"Config is missing required section(s): {', '.join(missing)}"
        )
