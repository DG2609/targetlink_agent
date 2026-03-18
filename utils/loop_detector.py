"""
Phát hiện agent gọi tool lặp lại liên tiếp với cùng arguments.
Khi phát hiện loop (mặc định 3 lần), trả về recovery hint thay vì chạy tool.

Nâng cấp: phân loại loop type → recovery hint targeted thay vì generic.
Pattern từ reference codebase (agentic/agent/nodes.py):
  3 identical consecutive tool calls → classified recovery hint injected.
"""

import hashlib
import json


class LoopType:
    """Phân loại nguyên nhân loop để đưa recovery hint phù hợp."""
    XPATH_NO_RESULT = "xpath_no_result"
    BLOCK_NOT_FOUND = "block_not_found"
    REGEX_NO_MATCH = "regex_no_match"
    CONFIG_NOT_FOUND = "config_not_found"
    GENERIC = "generic"


_RECOVERY_HINTS: dict[str, str] = {
    LoopType.XPATH_NO_RESULT: (
        "XPath không match — thử:\n"
        "  1. deep_search_xml_text() tìm keyword trong toàn bộ file\n"
        "  2. Kiểm tra MaskType thay vì BlockType (TargetLink blocks)\n"
        "  3. Thử file XML khác (blocks nằm ở system_*.xml, KHÔNG phải blockdiagram.xml)"
    ),
    LoopType.BLOCK_NOT_FOUND: (
        "Block type không tìm thấy — thử:\n"
        "  1. auto_discover_blocks() với keyword rộng hơn\n"
        "  2. Kiểm tra MaskType (VD: TL_Inport thay vì Inport)\n"
        "  3. build_model_hierarchy() xem model chứa block types nào"
    ),
    LoopType.REGEX_NO_MATCH: (
        "Regex không match — thử:\n"
        "  1. Pattern đơn giản hơn (bỏ bớt constraints)\n"
        "  2. Tìm trong file XML khác\n"
        "  3. Dùng read_xml_structure() xem trực tiếp cấu trúc"
    ),
    LoopType.CONFIG_NOT_FOUND: (
        "Config không tìm thấy — thử:\n"
        "  1. list_all_configs() xem TẤT CẢ configs của block\n"
        "  2. Config có thể nằm trong InstanceData (nested container)\n"
        "  3. Config có thể dùng tên khác — deep_search_xml_text() tìm keyword"
    ),
    LoopType.GENERIC: (
        "Bạn đang lặp cùng tool call — thử approach khác:\n"
        "  1. Thay đổi arguments\n"
        "  2. Dùng tool KHÁC để tìm thông tin\n"
        "  3. Nếu thông tin đã đủ, viết code dựa trên những gì đã biết"
    ),
}

# Mapping tool_name → loop type
_TOOL_LOOP_TYPE: dict[str, str] = {
    "test_xpath_query": LoopType.XPATH_NO_RESULT,
    "read_xml_structure": LoopType.XPATH_NO_RESULT,
    "read_parent_nodes": LoopType.XPATH_NO_RESULT,
    "find_blocks_recursive": LoopType.BLOCK_NOT_FOUND,
    "auto_discover_blocks": LoopType.BLOCK_NOT_FOUND,
    "deep_search_xml_text": LoopType.REGEX_NO_MATCH,
    "query_config": LoopType.CONFIG_NOT_FOUND,
    "list_all_configs": LoopType.CONFIG_NOT_FOUND,
    "read_raw_block_config": LoopType.CONFIG_NOT_FOUND,
    "build_model_hierarchy": LoopType.GENERIC,
    "trace_connections": LoopType.GENERIC,
    "trace_cross_subsystem": LoopType.GENERIC,
}


class LoopDetector:
    """Track tool calls và phát hiện repeated calls liên tiếp.

    Nâng cấp: phân loại loop type → recovery hint targeted thay vì generic.
    """

    def __init__(self, max_repeats: int = 3):
        self.max_repeats = max_repeats
        self._history: list[tuple[str, str]] = []

    def check(self, tool_name: str, **kwargs) -> str | None:
        """Kiểm tra xem tool call có bị lặp liên tiếp không.

        Args:
            tool_name: Tên tool đang được gọi.
            **kwargs: Arguments của tool call.

        Returns:
            Recovery hint string nếu loop detected, None nếu OK tiếp tục.
        """
        args_str = json.dumps(kwargs, sort_keys=True, default=str)
        args_hash = hashlib.md5(args_str.encode()).hexdigest()[:12]
        sig = (tool_name, args_hash)

        self._history.append(sig)

        # Đếm lần gọi liên tiếp cùng signature
        consecutive = 0
        for prev in reversed(self._history):
            if prev == sig:
                consecutive += 1
            else:
                break

        if consecutive >= self.max_repeats:
            loop_type = _TOOL_LOOP_TYPE.get(tool_name, LoopType.GENERIC)
            hint = _RECOVERY_HINTS[loop_type]
            return (
                f"⚠ LOOP DETECTED: {tool_name}() gọi {consecutive} lần "
                f"liên tiếp cùng arguments — kết quả KHÔNG đổi.\n\n{hint}"
            )
        return None

    def reset(self) -> None:
        """Reset history — gọi khi bắt đầu task mới hoặc agent mới."""
        self._history.clear()
