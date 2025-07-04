"""Utility functions for the VM management service"""

import crypt
from collections.abc import Callable
from typing import Any

from msfwk.utils.logging import get_logger

logger = get_logger("application")


async def run_with_error_logging(func: Callable, *args, **kwargs) -> Any:  # noqa: ANN002, ANN003, ANN401
    """Run a function with error logging"""
    try:
        return await func(*args, **kwargs)
    except Exception:
        logger.exception("Background task error in %s", func.__name__)
        raise


def generate_sha512_hash(password: str, rounds: int = 4096) -> str:
    """Generates an SHA-512 password hash compatible with mkpasswd.

    Args:
        password: The password to hash (string).
        rounds: The number of hashing rounds (integer, default 4096).

    Returns:
        The generated hash string, or None on error.
    """
    salt = crypt.mksalt(crypt.METHOD_SHA512, rounds=rounds)  # Generate a salt
    hashed_password = crypt.crypt(password, salt)  # Hash the password
    return hashed_password
