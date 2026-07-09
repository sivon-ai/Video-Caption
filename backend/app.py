from __future__ import annotations

import sys

from loguru import logger

from config import settings
from src.fireworks_client import ApiConfigurationError
from src.video_processor import process_default_video_folder


def main() -> int:
    settings.ensure_directories()
    if not settings.videos_dir.exists():
        logger.error("Videos folder does not exist: {}", settings.videos_dir)
        return 1

    try:
        response = process_default_video_folder()
    except ApiConfigurationError as exc:
        logger.error(str(exc))
        return 1

    if response.stats.total == 0:
        logger.warning("No videos found in {}", settings.videos_dir)
        return 0

    logger.info(
        "Completed: {} succeeded, {} failed. Output: {}",
        response.stats.succeeded,
        response.stats.failed,
        response.output_file,
    )
    return 0 if response.stats.failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
