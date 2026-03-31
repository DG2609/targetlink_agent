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
# Maps resolved slx_path → (extracted_dir, slx_mtime)
_extract_cache: dict[str, tuple[str, float]] = {}
# Chỉ track thư mục temp (do extract_slx tạo) — KHÔNG track thư mục user cung cấp
_temp_dirs: set[str] = set()

# Essential file that must exist in a valid unzipped SLX model
_ESSENTIAL_FILE = "simulink/systems/system_root.xml"


def _cleanup_temp_dirs():
    """Dọn chỉ thư mục TEMP đã extract, không xoá thư mục user cung cấp."""
    with _lock:
        for path in list(_temp_dirs):
            shutil.rmtree(path, ignore_errors=True)
        _temp_dirs.clear()
        _extract_cache.clear()


atexit.register(_cleanup_temp_dirs)


def _get_mtime(path: Path) -> float:
    """Return file/dir mtime, or 0.0 if unavailable."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def extract_slx(slx_path: str) -> str:
    """Unzip file .slx và trả về path tới THƯ MỤC GỐC chứa XML tree.

    File được extract vào thư mục temp, được cache theo slx_path.
    Gọi nhiều lần với cùng slx_path → trả về cùng path mà không extract lại.
    Cache được invalidate tự động nếu file .slx bị chỉnh sửa.

    Args:
        slx_path: Đường dẫn tới file .slx hoặc thư mục đã giải nén.

    Returns:
        Đường dẫn tuyệt đối tới thư mục gốc chứa XML tree đã extract.

    Raises:
        FileNotFoundError: Nếu file .slx không tồn tại.
        ValueError: Nếu file không phải ZIP hợp lệ hoặc thiếu system_root.xml.
    """
    slx_path = str(Path(slx_path).resolve())

    # Cache hit check (thread-safe): validate extracted dir still exists AND slx not modified
    with _lock:
        if slx_path in _extract_cache:
            cached_dir, cached_mtime = _extract_cache[slx_path]
            if Path(cached_dir).exists():
                current_mtime = _get_mtime(Path(slx_path))
                if current_mtime <= cached_mtime:
                    return cached_dir
            # Cache stale — remove and re-extract
            del _extract_cache[slx_path]

    slx = Path(slx_path)
    if not slx.exists():
        raise FileNotFoundError(f"File .slx không tồn tại: {slx_path}")

    # Nếu path là thư mục đã giải nén → validate structure và trả về trực tiếp
    # KHÔNG thêm vào _temp_dirs vì đây là thư mục user cung cấp, không được xoá
    if slx.is_dir():
        essential = slx / _ESSENTIAL_FILE
        if essential.exists():
            result = str(slx.resolve())
            with _lock:
                _extract_cache[slx_path] = (result, _get_mtime(slx))
            return result
        raise ValueError(
            f"Thư mục không phải model SLX hợp lệ "
            f"(thiếu {_ESSENTIAL_FILE}): {slx_path}"
        )

    # Extract vào temp dir
    tmp_dir = Path(tempfile.mkdtemp(prefix="targetlink_slx_"))

    try:
        with zipfile.ZipFile(slx, "r") as zf:
            # Zip Slip protection: validate tất cả paths trước khi extract
            resolved_tmp = tmp_dir.resolve()
            for info in zf.infolist():
                target = (tmp_dir / info.filename).resolve()
                try:
                    target.relative_to(resolved_tmp)
                except ValueError:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    raise ValueError(f"Zip Slip detected: {info.filename}")
            zf.extractall(tmp_dir)
    except zipfile.BadZipFile as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ValueError(f"File .slx không hợp lệ hoặc không phải ZIP: {e}")
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    # Verify essential structure exists after extraction
    essential = tmp_dir / _ESSENTIAL_FILE
    if not essential.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ValueError(
            f"Extraction không hợp lệ — thiếu {_ESSENTIAL_FILE} trong {slx_path}"
        )

    result = str(tmp_dir.resolve())
    slx_mtime = _get_mtime(slx)
    with _lock:
        _extract_cache[slx_path] = (result, slx_mtime)
        _temp_dirs.add(result)
    return result
