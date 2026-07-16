from pathlib import Path


def ensure_dir(path: Path | str) -> Path:
    """Tạo thư mục (kể cả thư mục cha) nếu chưa tồn tại, trả về Path đã resolve."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
