"""Centralized logging configuration for ARTE Chatbot.

Provides structured logging with configurable levels via the LOG_LEVEL
environment variable. Configures a single StreamHandler for stdout output,
compatible with Docker and containerized deployments.
"""

import logging
import os
import sys


LOG_FORMAT = "[%(asctime)s] %(levelname)-8s %(name)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_DEFAULT_LOG_LEVEL = "INFO"

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def get_log_level() -> int:
    """Resolve the log level from the LOG_LEVEL environment variable.

    Returns:
        The numeric log level (e.g., logging.INFO). Defaults to INFO
        if the env var is not set or contains an invalid value.
    """
    level_str = os.getenv("LOG_LEVEL", _DEFAULT_LOG_LEVEL).upper().strip()
    if level_str not in _VALID_LOG_LEVELS:
        level_str = _DEFAULT_LOG_LEVEL
    return getattr(logging, level_str)


def setup_logging() -> logging.Logger:
    """Configure the root logger and all application loggers.

    Sets up a StreamHandler to stdout with the project's standard format.
    The log level is controlled via the LOG_LEVEL environment variable
    (default: INFO). Safe to call multiple times — idempotent.

    Returns:
        The configured root logger instance.
    """
    root_logger = logging.getLogger()
    log_level = get_log_level()

    # Idempotent: avoid duplicate handlers on repeated calls
    if root_logger.handlers:
        root_logger.setLevel(log_level)
        return root_logger

    root_logger.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT))

    root_logger.addHandler(handler)

    # Suppress noisy third-party loggers in production
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return root_logger
