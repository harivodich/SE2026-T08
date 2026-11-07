"""Run the private ai-service: `python -m vietdoc.entrypoints.api`.

Single worker on purpose: one process owns the model lifecycle and compute slot.
"""

import uvicorn

from vietdoc.entrypoints.api.settings import Settings
from vietdoc.infrastructure.logging import configure_logging


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    uvicorn.run(
        "vietdoc.entrypoints.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        workers=1,
        access_log=False,
        log_config=None,
        server_header=False,
    )


if __name__ == "__main__":
    main()
