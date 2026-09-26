import os
import sys

from loguru import logger

from src.configs import LOGS_DIR


def setup_logging(log_file: str = "assistant.log"):
    """Configure loguru logger with enhanced formatting for console and file"""
    logger.remove()  # Remove default handler

    # ===== Console Logger with Colors =====
    logger.add(
        sys.stderr,
        level="INFO",
        format=("<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"),
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # ===== File Logger (rotating log) =====
    logger.add(log_file, level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}", rotation="2 MB", retention="7 days", encoding="utf-8")

    return logger


logger_ = setup_logging(os.path.join(LOGS_DIR, "assistant.log"))
