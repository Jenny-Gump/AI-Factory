import logging
import sys

def setup_logger(verbose: bool = False):
    """
    Set up the logger configuration.

    Args:
        verbose: If True, shows DEBUG level logs. If False, shows only INFO and above.
    """
    # Set appropriate log level based on verbose mode
    log_level = logging.DEBUG if verbose else logging.INFO

    # Configure logging format - more detailed for verbose mode
    if verbose:
        log_format = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s"
    else:
        log_format = "%(asctime)s [%(levelname)s] - %(message)s"

    # Clear any existing handlers to avoid duplicates
    logging.getLogger().handlers.clear()

    # Create separate error log handler with detailed format
    error_handler = logging.FileHandler("errors.log")
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s\n%(pathname)s"
    )
    error_handler.setFormatter(error_formatter)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler("app.log"),
            logging.StreamHandler(sys.stdout),
            error_handler
        ]
    )

    # Suppress noisy loggers in non-verbose mode
    if not verbose:
        # Reduce noise from external libraries
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)

    return logging.getLogger(__name__)

class QuietModeFilter(logging.Filter):
    """Фильтр для обычного режима - показывает только ключевые сообщения"""

    def filter(self, record):
        # В quiet режиме показываем только ключевые сообщения
        key_patterns = [
            "Starting Basic Articles Pipeline",
            "Starting broad search",
            "Found",
            "Finished URL filtering",
            "Successfully scraped",
            "sources passed validation",
            "Finished scoring sources",
            "Selected top 5 sources",
            "Finished cleaning content",
            "Creating ultimate structure",
            "Successfully generated",
            "Starting grouped fact-checking",
            "Fact-checking completed",
            "CRITICAL:",
            "FINAL WARNING:",
            "Starting editorial review",
            "Editorial review completed",
            "Article published",
            "Pipeline completed",
            "Token usage report",
            "✅",
            "🎉",
            "⚠️",
            "❌",
            "💥",
            "🔥",
            "🎯",  # Editorial review plan
            "🤖",  # Model attempt logs
            "📝",  # Editorial review attempt
            "Prompt:",  # Token data lines
            "TOTAL:",  # Token totals
            "═══",  # Разделители этапов
            "ЭТАП",  # Заголовки этапов
            "Section ",  # Компактный формат секций
            "Group ",  # Компактный формат групп fact-check
            "Pipeline interrupted"
        ]

        message = record.getMessage()
        return any(pattern in message for pattern in key_patterns)

def configure_logging(verbose: bool = False):
    """
    Configure logging for the entire application.

    Args:
        verbose: If True, enables detailed logging. If False, shows only key events.
    """
    # Clear existing configuration completely
    logging.getLogger().handlers.clear()
    logging.getLogger().setLevel(logging.NOTSET)

    # Set appropriate log level based on verbose mode
    log_level = logging.DEBUG if verbose else logging.INFO

    # Configure logging format - more detailed for verbose mode
    if verbose:
        log_format = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s"
    else:
        log_format = "%(asctime)s [%(levelname)s] - %(message)s"

    # Create handlers
    file_handler = logging.FileHandler("app.log")
    console_handler = logging.StreamHandler(sys.stdout)

    # Create separate error log handler with detailed format
    error_handler = logging.FileHandler("errors.log")
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s\n%(pathname)s"
    )
    error_handler.setFormatter(error_formatter)

    # Apply quiet mode filter to console in non-verbose mode
    if not verbose:
        console_handler.addFilter(QuietModeFilter())

    # Set formatters
    formatter = logging.Formatter(log_format)
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(error_handler)

    # Suppress noisy loggers in non-verbose mode
    if not verbose:
        # Reduce noise from external libraries
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
        logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)

    return logging.getLogger(__name__)

# Export logger for backward compatibility
logger = logging.getLogger(__name__)
