"""
Schemas cho dữ liệu Block Dictionary.
  - BlockDictEntry: 1 entry trong blocks.json
  - BlockMappingData: output của Agent 1 (Data Reader)
"""

from pydantic import BaseModel, Field


class BlockDictEntry(BaseModel):
    """1 entry trong blocks.json."""
    name_ui: str = Field(description="Tên hiển thị trong UI, VD: 'Inport'")
    name_xml: str = Field(description="Tên trong XML, VD: 'TL_Inport'")
    description: str = Field(description="Mô tả vị trí config, cách ẩn/hiện theo mode")


class BlockMappingData(BaseModel):
    """Output của Agent 1 — thông tin block đã được phân tích."""
    name_ui: str
    name_xml: str
    config_map_analysis: str  # LLM tóm tắt: XPath gợi ý, mode ẩn/hiện, lưu ý đặc biệt
