import logging
import os
import sys
from pathlib import Path

from loguru import logger


class CustomLogger:
    def __init__(self):
        self._format = "{time:YYYY-MM-DD HH:mm} | {level} | {name}:{function}:{line} - {message}"
        self._rotation = "1 MB"
        self._compression = "zip"
        self._logs_dir_path = os.path.join(Path(__file__).parent.parent.parent / "logs")
        self._level = logging.INFO

    def init_logging(self):
        self.__create_log_dir()

        logger.remove(None)

        logging.basicConfig(handlers=[InterceptHandler()], level=self._level)
        for name in logging.root.manager.loggerDict:
            stdlib_logger = logging.getLogger(name)
            loguru_handler = InterceptHandler(name)
            stdlib_logger.handlers = [loguru_handler]
            stdlib_logger.propagate = False

        # Add a global stdout handler
        logger.add(
            sys.stdout,
            level=self._level
        )

        # Add a global error handler
        logger.add(
            os.path.join(self._logs_dir_path, "error.log"),
            format=self._format,
            level="ERROR",
            rotation=self._rotation,
            compression=self._compression,
        )

    # Add a logger with a specific name and log file
    def add_logger(self, file: str, module_name: str):
        logger.add(
            os.path.join(self._logs_dir_path, file),
            format=self._format,
            rotation=self._rotation,
            level=self._level,
            compression=self._compression,
            filter=self.__create_filter(module_name),
        )

    # Create the log directory
    def __create_log_dir(self) -> None:
        if not os.path.exists(self._logs_dir_path):
            os.makedirs(self._logs_dir_path, exist_ok=True)

    # Create a filter function, ignore errors in logger with specific name
    @staticmethod
    def __create_filter(module_name: str):
        def filter_func(record):
            return record["name"] == module_name and record["level"].no < logger.level("ERROR").no

        return filter_func


class InterceptHandler(logging.Handler):
    def __init__(self, name: str = None) -> None:
        if name is not None:
            self._logger = logger.patch(lambda record: record.update(name=name))
        else:
            self._logger = logger
        super().__init__()

    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        self._logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )
