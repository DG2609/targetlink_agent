"""
Parse bddefaults.xml → build default values map per block type.

Simulink/TargetLink behavior: khi config ở giá trị default, nó KHÔNG xuất hiện
trong XML của block. Chỉ khi user đổi sang giá trị khác, <P> mới được ghi.

File bddefaults.xml chứa BlockParameterDefaults — default values cho mỗi block type.
Module này parse file đó thành dict để các tool khác tra cứu.
"""

import logging
from pathlib import Path
from lxml import etree

logger = logging.getLogger(__name__)

# Cache: parse 1 lần per model_dir
_defaults_cache: dict[str, dict[str, dict[str, str]]] = {}


def parse_bddefaults(model_dir: str) -> dict[str, dict[str, str]]:
    """Parse bddefaults.xml, trả về default values per block type.

    Args:
        model_dir: Đường dẫn tới thư mục gốc chứa XML tree (sau khi unzip .slx).

    Returns:
        Dict 2 tầng: {block_type → {config_name → default_value}}
        VD: {"Gain": {"SaturateOnIntegerOverflow": "off", "Gain": "1", ...}}
        Trả về dict rỗng nếu file không tồn tại hoặc parse lỗi.
    """
    # Normalize path to avoid duplicate cache entries from symlinks / relative paths
    model_dir = str(Path(model_dir).resolve())

    if model_dir in _defaults_cache:
        return _defaults_cache[model_dir]

    bd_path = Path(model_dir) / "simulink" / "bddefaults.xml"
    if not bd_path.exists():
        logger.warning(
            f"bddefaults.xml không tồn tại: {bd_path} — "
            f"default values sẽ không khả dụng. "
            f"Configs vắng trong block XML sẽ không có fallback value."
        )
        _defaults_cache[model_dir] = {}
        return {}

    try:
        tree = etree.parse(str(bd_path))
        root = tree.getroot()
    except etree.XMLSyntaxError as e:
        logger.error(
            f"bddefaults.xml malformed: {bd_path} — {e}. "
            f"Default values sẽ không khả dụng."
        )
        _defaults_cache[model_dir] = {}
        return {}

    defaults: dict[str, dict[str, str]] = {}

    # Support both: root IS BlockParameterDefaults, or nested inside another element
    if root.tag == "BlockParameterDefaults":
        block_param_defaults = root
    else:
        block_param_defaults = root.find(".//BlockParameterDefaults")
    if block_param_defaults is None:
        logger.warning(f"bddefaults.xml có cấu trúc không chuẩn (thiếu BlockParameterDefaults): {bd_path}")
        _defaults_cache[model_dir] = {}
        return {}

    for block_elem in block_param_defaults.findall("Block"):
        block_type = block_elem.get("BlockType")
        if not block_type:
            continue

        configs: dict[str, str] = {}
        for p_elem in block_elem.findall("P"):
            name = p_elem.get("Name")
            value = p_elem.text or ""
            if name:
                configs[name] = value.strip()

        defaults[block_type] = configs

    _defaults_cache[model_dir] = defaults
    return defaults


def get_default_value(
    model_dir: str, block_type: str, config_name: str,
) -> str | None:
    """Tra cứu default value cho 1 config cụ thể.

    Args:
        model_dir: Đường dẫn model tree.
        block_type: VD: "Gain", "Abs", "Sum".
        config_name: VD: "SaturateOnIntegerOverflow".

    Returns:
        Default value (str) hoặc None nếu không tìm thấy.
    """
    defaults = parse_bddefaults(model_dir)
    block_defaults = defaults.get(block_type, {})
    return block_defaults.get(config_name)


def clear_cache() -> None:
    """Xóa cache — dùng khi test hoặc khi đổi model."""
    _defaults_cache.clear()
