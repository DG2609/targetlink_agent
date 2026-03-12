"""
Tools cho việc tìm kiếm block trong từ điển JSON.
Agent 1 (Data Reader) sử dụng toolkit này.

Fuzzy search dùng rapidfuzz — KHÔNG tốn LLM token cho bước tìm kiếm.
"""

import json
from pathlib import Path
from rapidfuzz import fuzz
from agno.tools import Toolkit


class SearchToolkit(Toolkit):
    """Cung cấp khả năng tra cứu từ điển block cho Agent.

    Load toàn bộ blocks.json vào memory 1 lần, sau đó search bằng fuzzy matching.
    """

    def __init__(self, blocks_json_path: str):
        super().__init__(name="search_tools")
        self.blocks_json_path = blocks_json_path
        self._blocks: list[dict] | None = None

        self.register(self.fuzzy_search_json)
        self.register(self.read_dictionary)

    def _get_blocks(self) -> list[dict]:
        """Lazy load blocks JSON (chỉ đọc 1 lần)."""
        if self._blocks is None:
            content = Path(self.blocks_json_path).read_text(encoding="utf-8")
            self._blocks = json.loads(content)
        return self._blocks

    # ──────────────────────────────────────────────
    # Tool 1: fuzzy_search_json
    # ──────────────────────────────────────────────

    def fuzzy_search_json(self, keyword: str, top_k: int = 3) -> str:
        """Tìm block trong từ điển blocks.json bằng fuzzy text matching.
        So sánh keyword với trường 'name_ui' của mỗi block.

        Dùng khi cần tìm block tương ứng với keyword từ rule (VD: "inport" → tìm block "Inport").
        Trả về top_k kết quả tốt nhất kèm điểm similarity.

        Args:
            keyword: Từ khóa tìm kiếm (VD: "inport", "main data", "outport"). Case-insensitive.
            top_k: Số kết quả trả về (mặc định 3, tối đa 5).

        Returns:
            JSON array top matches, mỗi entry gồm: name_ui, name_xml, score, description (rút gọn).
            Trả về thông báo nếu không tìm thấy match nào >= 50% similarity.
        """
        blocks = self._get_blocks()
        top_k = min(max(top_k, 1), 5)

        scored = []
        for block in blocks:
            name_ui = block.get("name_ui", "")
            # Dùng token_sort_ratio: so sánh không phụ thuộc thứ tự từ
            score = fuzz.token_sort_ratio(keyword.lower(), name_ui.lower())
            scored.append((score, block))

        # Sort giảm dần theo score
        scored.sort(key=lambda x: x[0], reverse=True)

        # Lọc threshold >= 50
        results = []
        for score, block in scored[:top_k]:
            if score < 50:
                break
            results.append({
                "name_ui": block.get("name_ui", ""),
                "name_xml": block.get("name_xml", ""),
                "score": score,
                "description": (block.get("description", ""))[:300],
            })

        if not results:
            return f"Không tìm thấy block nào match keyword '{keyword}' (threshold >= 50%). Thử keyword khác."

        return f"Tìm thấy {len(results)} matches cho '{keyword}':\n" + json.dumps(
            results, indent=2, ensure_ascii=False
        )

    # ──────────────────────────────────────────────
    # Tool 2: read_dictionary
    # ──────────────────────────────────────────────

    def read_dictionary(self, name_xml: str) -> str:
        """Đọc toàn bộ thông tin của 1 block từ từ điển, search chính xác bằng name_xml.

        Dùng SAU KHI đã biết name_xml (từ kết quả fuzzy_search_json) để lấy description đầy đủ.
        Description chứa thông tin QUAN TRỌNG về vị trí config, mode ẩn/hiện, tên XML khác UI.

        Args:
            name_xml: Tên XML chính xác của block (VD: "TL_Inport", "TL_MAIN_DATA"). Case-sensitive.

        Returns:
            JSON object đầy đủ của block (name_ui, name_xml, description).
            Trả về thông báo lỗi nếu không tìm thấy exact match.
        """
        blocks = self._get_blocks()

        for block in blocks:
            if block.get("name_xml") == name_xml:
                return json.dumps(block, indent=2, ensure_ascii=False)

        # Fallback: tìm case-insensitive
        for block in blocks:
            if block.get("name_xml", "").lower() == name_xml.lower():
                return (
                    f"Tìm thấy (case-insensitive match, tên chính xác là '{block['name_xml']}'):\n"
                    + json.dumps(block, indent=2, ensure_ascii=False)
                )

        return f"Không tìm thấy block với name_xml='{name_xml}'. Hãy dùng fuzzy_search_json trước."
