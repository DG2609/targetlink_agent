"""
Pure Python replacement cho Agent 1 (Data Reader).

Thay vì dùng LLM + SearchToolkit, trực tiếp:
  1. Load blocks.json
  2. Fuzzy match block_keyword → name_ui (rapidfuzz)
  3. Trả BlockMappingData (không tốn LLM token)

Logic copy từ tools/search_tools.py fuzzy_search_json().
"""

import json
import logging
from pathlib import Path

from rapidfuzz import fuzz

from schemas.block_schemas import BlockMappingData

logger = logging.getLogger(__name__)

# Cache blocks.json per path (tránh đọc lại mỗi rule)
_blocks_cache: dict[str, list[dict]] = {}


def clear_cache() -> None:
    """Xóa cache — dùng khi test hoặc khi đổi blocks.json."""
    _blocks_cache.clear()


def _load_blocks(blocks_json_path: str) -> list[dict]:
    """Lazy load blocks.json với cache."""
    if blocks_json_path in _blocks_cache:
        return _blocks_cache[blocks_json_path]

    path = Path(blocks_json_path)
    if not path.exists():
        logger.warning(f"blocks.json không tồn tại: {blocks_json_path}")
        _blocks_cache[blocks_json_path] = []
        return []

    try:
        blocks = json.loads(path.read_text(encoding="utf-8"))
        _blocks_cache[blocks_json_path] = blocks
        return blocks
    except json.JSONDecodeError as e:
        logger.warning(f"blocks.json JSON lỗi: {e}")
        _blocks_cache[blocks_json_path] = []
        return []


def _infer_xml_representation(name_xml: str) -> str:
    """Infer xml_representation từ name_xml.

    - TL_ prefix → "masked" (TargetLink MaskType blocks)
    - Có space → "reference" (reference library blocks)
    - Else → "native" (standard Simulink blocks)
    """
    if not name_xml:
        return "unknown"
    if name_xml.startswith("TL_"):
        return "masked"
    if " " in name_xml:
        return "reference"
    return "native"


def search_block_mapping(
    blocks_json_path: str,
    block_keyword: str,
    config_name: str,
) -> BlockMappingData:
    """Tìm block trong blocks.json bằng fuzzy matching — pure Python, không LLM.

    Args:
        blocks_json_path: Path tới blocks.json.
        block_keyword: Keyword từ ParsedRule.block_keyword (VD: "gain", "inport").
        config_name: Config cần check (dùng cho config_map_analysis).

    Returns:
        BlockMappingData với kết quả match tốt nhất.
        Nếu không match → trả về BlockMappingData rỗng.
    """
    blocks = _load_blocks(blocks_json_path)

    if not blocks or not block_keyword:
        return BlockMappingData(
            name_ui="",
            name_xml="",
            xml_representation="unknown",
            search_confidence=0,
            config_map_analysis=f"Không tìm được block cho keyword '{block_keyword}'.",
        )

    # Fuzzy match: token_sort_ratio (giống search_tools.py)
    scored = []
    for block in blocks:
        name_ui = block.get("name_ui") or ""
        score = fuzz.token_sort_ratio(block_keyword.lower(), name_ui.lower())
        scored.append((score, block))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Threshold >= 35 (giống search_tools.py)
    best_score, best_block = scored[0]
    if best_score < 35:
        return BlockMappingData(
            name_ui="",
            name_xml="",
            xml_representation="unknown",
            search_confidence=0,
            config_map_analysis=(
                f"Không tìm thấy block match keyword '{block_keyword}' "
                f"(best score: {best_score}). Thử keyword khác hoặc dùng "
                f"find_config_locations('{config_name}') để tìm tất cả block types."
            ),
        )

    name_xml = best_block.get("name_xml") or ""
    name_ui = best_block.get("name_ui") or ""
    description = best_block.get("description", "")

    logger.debug(
        f"Block match: '{block_keyword}' → '{name_ui}' (score={best_score})"
    )

    return BlockMappingData(
        name_ui=name_ui,
        name_xml=name_xml,
        xml_representation=_infer_xml_representation(name_xml),
        search_confidence=best_score,
        source_type_pattern=best_block.get("source_type_pattern", ""),
        config_map_analysis=description,
    )


def get_block_raw_entry(
    blocks_json_path: str, name_xml: str,
) -> str:
    """Lấy raw JSON entry từ blocks.json cho 1 block type.

    Dùng để inject vào Agent2Input.blocks_raw_data.

    Returns:
        JSON string của block entry, hoặc "" nếu không tìm thấy.
    """
    blocks = _load_blocks(blocks_json_path)
    for block in blocks:
        if block.get("name_xml") == name_xml:
            return json.dumps(block, indent=2, ensure_ascii=False)
    return ""
