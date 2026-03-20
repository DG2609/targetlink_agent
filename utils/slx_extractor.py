"""
Unzip file .slx (Simulink model) và trả về đường dẫn tới thư mục gốc chứa XML tree.

File .slx thực chất là ZIP archive chứa một TREE gồm nhiều file XML:
  - simulink/blockdiagram.xml    (cấu trúc model chính)
  - simulink/configSet0.xml      (simulation config)
  - metadata/coreProperties.xml  (metadata)
  - [Content_Types].xml
  - ... và các file khác tùy model

Agent KHÔNG được đọc toàn bộ tree — phải dùng tools để khám phá từng file.
"""

import atexit
import threading
import zipfile
import tempfile
import shutil
from pathlib import Path


# Thread-safe cache: tránh extract lại cùng 1 file nếu chạy nhiều rules
_lock = threading.Lock()
_extract_cache: dict[str, str] = {}
# Chỉ track thư mục temp (do extract_slx tạo) — KHÔNG track thư mục user cung cấp
_temp_dirs: set[str] = set()


def _cleanup_temp_dirs():
    """Dọn chỉ thư mục TEMP đã extract, không xoá thư mục user cung cấp."""
    with _lock:
        for path in _temp_dirs:
            shutil.rmtree(path, ignore_errors=True)
        _temp_dirs.clear()
        _extract_cache.clear()


atexit.register(_cleanup_temp_dirs)


def extract_slx(slx_path: str) -> str:
    """Unzip file .slx và trả về path tới THƯ MỤC GỐC chứa XML tree.

    File được extract vào thư mục temp, được cache theo slx_path.
    Gọi nhiều lần với cùng slx_path → trả về cùng path mà không extract lại.

    Args:
        slx_path: Đường dẫn tới file .slx.

    Returns:
        Đường dẫn tuyệt đối tới thư mục gốc chứa XML tree đã extract.

    Raises:
        FileNotFoundError: Nếu file .slx không tồn tại.
        ValueError: Nếu file không phải ZIP hợp lệ hoặc không chứa XML nào.
    """
    slx_path = str(Path(slx_path).resolve())

    # Cache hit (thread-safe)
    with _lock:
        if slx_path in _extract_cache:
            cached = _extract_cache[slx_path]
            if Path(cached).exists():
                return cached

    slx = Path(slx_path)
    if not slx.exists():
        raise FileNotFoundError(f"File .slx không tồn tại: {slx_path}")

    # Nếu path là thư mục đã giải nén (có chứa XML) → trả về trực tiếp
    # KHÔNG thêm vào _temp_dirs vì đây là thư mục user cung cấp, không được xoá
    if slx.is_dir():
        xml_files = list(slx.rglob("*.xml"))
        if xml_files:
            result = str(slx.resolve())
            with _lock:
                _extract_cache[slx_path] = result
            return result
        raise ValueError(f"Thư mục không chứa file XML nào: {slx_path}")

    # Extract vào temp dir
    tmp_dir = Path(tempfile.mkdtemp(prefix="targetlink_slx_"))

    try:
        with zipfile.ZipFile(slx, "r") as zf:
            # Zip Slip protection: validate paths trước khi extract
            resolved_tmp = tmp_dir.resolve()
            for info in zf.infolist():
                target = (tmp_dir / info.filename).resolve()
                # So sánh bằng Path.is_relative_to() (Python 3.9+) thay vì startswith
                # tránh false positive trên Windows do backslash vs forward slash
                try:
                    target.relative_to(resolved_tmp)
                except ValueError:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    raise ValueError(f"Zip Slip detected: {info.filename}")
            zf.extractall(tmp_dir)
    except zipfile.BadZipFile as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ValueError(f"File .slx không hợp lệ hoặc không phải ZIP: {e}")

    # Verify có ít nhất 1 file XML trong tree
    xml_files = list(tmp_dir.rglob("*.xml"))
    if not xml_files:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ValueError(f"Không tìm thấy file XML nào trong {slx_path}")

    result = str(tmp_dir.resolve())
    with _lock:
        _extract_cache[slx_path] = result
        _temp_dirs.add(result)
    return result
