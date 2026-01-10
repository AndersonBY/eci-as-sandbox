import logging
from typing import Any, Dict, Optional


_LOGGING_CONFIGURED = False


def _configure_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_logging()
    return logging.getLogger(name)


def _log_api_call(api_name: str, details: str) -> None:
    logger = get_logger("eci-as-sandbox.api")
    logger.info("Call %s: %s", api_name, details)


def _log_api_response(
    api_name: str,
    request_id: str,
    success: bool,
    key_fields: Optional[Dict[str, Any]] = None,
) -> None:
    logger = get_logger("eci-as-sandbox.api")
    summary = "ok" if success else "failed"
    if key_fields:
        logger.info(
            "%s %s request_id=%s details=%s", api_name, summary, request_id, key_fields
        )
    else:
        logger.info("%s %s request_id=%s", api_name, summary, request_id)


def _log_operation_error(operation: str, message: str, exc_info: bool = False) -> None:
    logger = get_logger("eci-as-sandbox")
    logger.error("%s error: %s", operation, message, exc_info=exc_info)
