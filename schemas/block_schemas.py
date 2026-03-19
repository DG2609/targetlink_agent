"""
Schemas cho dữ liệu Block Dictionary.
  - BlockMappingData: output của Agent 1 (Data Reader)
"""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class BlockMappingData(BaseModel):
    """Output của Agent 1 — thông tin block đã được mapping.

    Agent 1 dùng SearchToolkit để tìm block trong blocks.json,
    rồi phân tích vị trí config trong XML tree.

    Example:
        >>> b = BlockMappingData(
        ...     name_ui="Gain", name_xml="Gain",
        ...     xml_representation="native",
        ...     search_confidence=95,
        ...     config_map_analysis=(
        ...         "SaturateOnIntegerOverflow nằm trong <P Name='SaturateOnIntegerOverflow'> "
        ...         "là child trực tiếp của <Block BlockType='Gain'>. "
        ...         "Giá trị: 'on' hoặc 'off'. Default: 'off' (từ bddefaults.xml). "
        ...         "Blocks nằm trong simulink/systems/system_*.xml."
        ...     ),
        ... )
    """

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "name_ui": "Gain",
                "name_xml": "Gain",
                "xml_representation": "native",
                "search_confidence": 95,
                "config_map_analysis": (
                    "SaturateOnIntegerOverflow nằm trong <P Name='SaturateOnIntegerOverflow'> "
                    "là child trực tiếp của <Block BlockType='Gain'>. "
                    "Giá trị: 'on' hoặc 'off'. Default: 'off' (từ bddefaults.xml). "
                    "Blocks nằm trong simulink/systems/system_*.xml, "
                    "KHÔNG nằm trong blockdiagram.xml."
                ),
            },
            {
                "name_ui": "Compare To Constant",
                "name_xml": "Compare To Constant",
                "xml_representation": "reference",
                "search_confidence": 80,
                "source_type_pattern": "Compare To Constant",
                "config_map_analysis": (
                    "Block là Reference: BlockType='Reference', tìm qua SourceType. "
                    "Config nằm trong <InstanceData>/<P>, KHÔNG phải direct <P>."
                ),
            },
        ]
    })

    name_ui: str = Field(
        description="Tên hiển thị (UI), từ blocks.json",
        examples=["Gain", "Abs", "Inport", "Sum", "Delay"],
    )
    name_xml: str = Field(
        description="Block identifier — có thể là BlockType, MaskType, hoặc SourceType",
        examples=["Gain", "Abs", "TL_Inport", "Compare To Constant"],
    )
    xml_representation: Literal["native", "reference", "masked", "unknown"] = Field(
        default="unknown",
        description=(
            "Dạng block trong XML: "
            "native = BlockType trực tiếp, "
            "reference = BlockType='Reference' + SourceType, "
            "masked = BlockType='SubSystem' + MaskType (TL blocks), "
            "unknown = chưa xác định (Agent 2 cần tự khám phá)"
        ),
    )
    search_confidence: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Fuzzy search score (0-100). Dưới 70 = cần Agent 2 verify thêm",
        examples=[95, 80, 60],
    )
    source_type_pattern: str = Field(
        default="",
        description="SourceType value cho Reference blocks. Rỗng nếu không phải Reference",
        examples=["", "Compare To Constant"],
    )
    config_map_analysis: str = Field(
        description=(
            "LLM phân tích: config nằm ở đâu trong XML, XPath gợi ý, "
            "giá trị default, lưu ý đặc biệt (MaskType, InstanceData, etc.)"
        ),
    )
