import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


def setup_logging(config) -> None:

    level = getattr(config, 'level', 'INFO').upper()
    log_format = getattr(config, 'format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_path = getattr(config, 'file_path', None)
    max_file_size = getattr(config, 'max_file_size', 10 * 1024 * 1024)  # 10MB
    backup_count = getattr(config, 'backup_count', 5)
    console_output = getattr(config, 'console_output', True)

    numeric_level = getattr(logging, level, logging.INFO)

    formatter = logging.Formatter(log_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    root_logger.handlers.clear()

    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if file_path:
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)

    logging.info(f"Logging configured: level={level}, console={console_output}, file={file_path}")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_performance(func):
    import time
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(f"performance.{func.__module__}.{func.__name__}")
        start_time = time.time()

        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            logger.debug(f"Function completed in {elapsed:.3f}s")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Function failed after {elapsed:.3f}s: {e}")
            raise

    return wrapper


def log_memory_usage(operation: str) -> None:
    try:
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        logging.debug(f"Memory usage after {operation}: {memory_mb:.1f} MB")
    except ImportError:
        pass


def set_log_level(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric_level)
    logging.info(f"Log level changed to {level.upper()}")