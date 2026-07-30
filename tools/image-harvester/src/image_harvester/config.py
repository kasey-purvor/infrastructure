"""Configuration — resolve the ScrapFly API key."""

from __future__ import annotations

import os


def resolve_api_key(cli_value: str | None = None) -> str:
    """
    Return the ScrapFly API key.

    Priority: CLI argument → SCRAPFLY_KEY env variable.

    Raises:
        RuntimeError: if no key is found in either location.
    """
    if cli_value:
        return cli_value
    env_key = os.environ.get("SCRAPFLY_KEY")
    if env_key:
        return env_key
    raise RuntimeError(
        "No ScrapFly API key found. "
        "Set the SCRAPFLY_KEY environment variable or pass --api-key."
    )
