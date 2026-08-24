import logging
import sys

class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[94m",      # Blue
        "INFO": "\033[92m",       # Green
        "WARNING": "\033[93m",    # Yellow
        "ERROR": "\033[91m",      # Red
        "CRITICAL": "\033[1;91m", # Bold Red
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname:^8}{self.RESET}"
        record.msg = f"{record.msg}"
        return super().format(record)

def setup_logging(level: int = logging.INFO) -> None:
    """Cấu hình logging chung cho toàn bộ backend."""
    # Disable uvicorn's default access logger to prevent double logging
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers = []
    uvicorn_access.propagate = False
    uvicorn_access.disabled = True

    formatter = ColorFormatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers if any
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    root_logger.addHandler(console_handler)
