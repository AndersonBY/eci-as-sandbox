import os
from pathlib import Path
from typing import Any, Dict, Optional

import dotenv

from .logger import get_logger


_logger = get_logger("eci-as-sandbox.config")


class Config:
    def __init__(self, endpoint: str, timeout_ms: int, region_id: Optional[str] = None):
        self.endpoint = endpoint
        self.timeout_ms = timeout_ms
        self.region_id = region_id


def _default_config() -> Dict[str, Any]:
    return {
        "endpoint": "eci.cn-shanghai.aliyuncs.com",
        "timeout_ms": 60000,
        "region_id": None,
    }


def _find_dotenv_file(start_path: Optional[Path] = None) -> Optional[Path]:
    if start_path is None:
        start_path = Path.cwd()

    current_path = Path(start_path).resolve()
    while current_path != current_path.parent:
        env_file = current_path / ".env"
        if env_file.exists():
            return env_file
        current_path = current_path.parent

    root_env = current_path / ".env"
    if root_env.exists():
        return root_env

    return None


def _load_dotenv_with_fallback(custom_env_path: Optional[str] = None) -> None:
    if custom_env_path:
        env_path = Path(custom_env_path)
        if env_path.exists():
            dotenv.load_dotenv(env_path)
            _logger.info("Loaded .env from %s", env_path)
            return
        _logger.warning("Custom .env file not found: %s", env_path)

    env_file = _find_dotenv_file()
    if env_file:
        dotenv.load_dotenv(env_file)
        _logger.info("Loaded .env from %s", env_file)


def _load_config(
    cfg: Optional[Config], custom_env_path: Optional[str] = None
) -> Dict[str, Any]:
    if cfg is not None:
        return {
            "endpoint": cfg.endpoint,
            "timeout_ms": cfg.timeout_ms,
            "region_id": cfg.region_id,
        }

    config = _default_config()

    try:
        _load_dotenv_with_fallback(custom_env_path)
    except Exception as exc:
        _logger.warning("Failed to load .env: %s", exc)

    if endpoint := os.getenv("ECI_SANDBOX_ENDPOINT"):
        config["endpoint"] = endpoint
    if timeout_ms := os.getenv("ECI_SANDBOX_TIMEOUT_MS"):
        try:
            config["timeout_ms"] = int(timeout_ms)
        except ValueError:
            _logger.warning("Invalid ECI_SANDBOX_TIMEOUT_MS value: %s", timeout_ms)
    region = os.getenv("ECI_SANDBOX_REGION_ID") or os.getenv("ALIBABA_CLOUD_REGION_ID")
    if region:
        config["region_id"] = region

    return config
