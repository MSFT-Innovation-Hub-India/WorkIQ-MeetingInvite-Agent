"""
Hub Config — load / save user-editable configuration.

Defaults ship in hub_config.default.json (checked into repo).
User overrides are stored in ~/.hub-se-agent/hub_config.json (never checked in).
On load, defaults are read first, then user overrides are merged on top.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("hub_se_agent")

_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_PATH = _SCRIPT_DIR / "hub_config.default.json"
_USER_DIR = Path.home() / ".hub-se-agent"
_USER_PATH = _USER_DIR / "hub_config.json"


def load() -> dict:
    """Return merged config (defaults + user overrides)."""
    config = {}
    # Load defaults
    if _DEFAULT_PATH.exists():
        try:
            config = json.loads(_DEFAULT_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to read default config: %s", e)

    # Overlay user overrides
    if _USER_PATH.exists():
        try:
            overrides = json.loads(_USER_PATH.read_text(encoding="utf-8"))
            config.update(overrides)
        except Exception as e:
            logger.warning("Failed to read user config: %s", e)

    return config


def save(config: dict) -> None:
    """Persist user config to ~/.hub-se-agent/hub_config.json."""
    _USER_DIR.mkdir(parents=True, exist_ok=True)
    _USER_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("User config saved to %s", _USER_PATH)
