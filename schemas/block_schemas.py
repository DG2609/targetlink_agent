"""
Schemas cho dữ liệu Block Dictionary.
  - BlockMappingData: output của Agent 1 (Data Reader)
"""

from pydantic import BaseModel, ConfigDict, Field


class BlockMappingData(BaseModel):
    """Output của Agent 1 — thông tin block đã được mapping.

    Agent 1 dùng SearchToolkit để tìm block trong blocks.json,
    rồi phân tích vị trí config trong XML tree.

    Example:
        >>> b = BlockMappingData(
        ...     name_ui="Gain", name_xml="Gain",
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
                "config_map_analysis": (
                    "SaturateOnIntegerOverflow nằm trong <P Name='SaturateOnIntegerOverflow'> "
                    "là child trực tiếp của <Block BlockType='Gain'>. "
                    "Giá trị: 'on' hoặc 'off'. Default: 'off' (từ bddefaults.xml). "
                    "Blocks nằm trong simulink/systems/system_*.xml, "
                    "KHÔNG nằm trong blockdiagram.xml."
                ),
            },
            {
                "name_ui": "Abs",
                "name_xml": "Abs",
                "config_map_analysis": (
                    "SaturateOnIntegerOverflow nằm trong <P Name='SaturateOnIntegerOverflow'> "
                    "là child trực tiếp. Default: 'off'. "
                    "Abs blocks CHỈ xuất hiện ở system_root.xml trong model này."
                ),
            },
        ]
    })

    name_ui: str = Field(
        description="Tên hiển thị (UI), từ blocks.json",
        examples=["Gain", "Abs", "Inport", "Sum", "Delay"],
    )
    name_xml: str = Field(
        description="BlockType trong XML attribute, dùng cho XPath",
        examples=["Gain", "Abs", "Inport", "TL_Inport", "SubSystem"],
    )
    config_map_analysis: str = Field(
        description=(
            "LLM phân tích: config nằm ở đâu trong XML, XPath gợi ý, "
            "giá trị default, lưu ý đặc biệt (MaskType, InstanceData, etc.)"
        ),
    )
