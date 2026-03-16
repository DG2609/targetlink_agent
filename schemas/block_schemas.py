"""
Schemas cho dữ liệu Block Dictionary.
  - BlockMappingData: output của Agent 1 (Data Reader)
"""

from pydantic import BaseModel, Field


class BlockMappingData(BaseModel):
    """Output của Agent 1 — thông tin block đã được phân tích."""
    name_ui: str
    name_xml: str
    config_map_analysis: str  # LLM tóm tắt: XPath gợi ý, mode ẩn/hiện, lưu ý đặc biệt
