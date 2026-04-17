"""
Shared helpers for consistent phase-by-phase timing logs.
"""
import logging
import time
from typing import Any


def log_phase(logger: logging.Logger, scope: str, phase: str, started: float, **details: Any) -> float:
    """Log a consistent timing line and return the elapsed time in seconds."""
    elapsed = time.perf_counter() - started
    suffix = ""
    if details:
        suffix = " | " + ", ".join(f"{key}={value}" for key, value in details.items())
    logger.info("[timing][%s] %s=%.3fs%s", scope, phase, elapsed, suffix)
    return elapsed
