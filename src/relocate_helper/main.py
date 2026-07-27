"""Uvicorn entrypoint for the API server."""

from __future__ import annotations

import uvicorn

from relocate_helper.common.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "relocate_helper.api.app:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
