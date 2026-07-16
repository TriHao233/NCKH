import logging


def setup_logging(level: int = logging.INFO) -> None:
    """Cấu hình logging chung cho toàn bộ backend, gọi đúng 1 lần lúc app khởi động."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
