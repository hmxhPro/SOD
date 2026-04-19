"""
app/core/logging.py
-------------------
Loguru-based logging configuration.
"""

import sys
from loguru import logger


def setup_logging(debug: bool = False) -> None:
    """Configure loguru logger for the application."""
    logger.remove()  # Remove default handler

    level = "DEBUG" if debug else "INFO"

    # Console handler with colored output
    logger.add(
        sys.stdout,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File handler (rotates daily, keeps 7 days)
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="00:00",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    )


__all__ = ["logger", "setup_logging"]
