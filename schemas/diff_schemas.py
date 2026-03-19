"""
Schemas cho Diff-Based Config Discovery.
  - ConfigChange: 1 config thay đổi giữa 2 model versions
  - BlockChange: tổng hợp thay đổi cho 1 block
  - ModelDiff: raw diff output của utils/model_differ.py
  - ConfigDiscovery: output của Agent 1.5 — ground truth config locations
"""

from pydantic import BaseModel, Field


class ConfigChange(BaseModel):
    """1 config thay đổi giữa 2 model versions."""

    block_sid: str = Field(description="SID của block chứa config thay đổi")
    block_name: str = Field(description="Tên block, VD: 'Gain1'")
    block_type: str = Field(description="BlockType attribute, VD: 'Gain', 'SubSystem'")
    mask_type: str = Field(default="", description="MaskType nếu là TL block, VD: 'TL_Gain'")
    system_file: str = Field(description="File XML chứa block, VD: 'simulink/systems/system_root.xml'")
    config_name: str = Field(description="Tên config, VD: 'SaturateOnIntegerOverflow'")
    old_value: str | None = Field(default=None, description="Giá trị trước (None = config mới thêm)")
    new_value: str | None = Field(default=None, description="Giá trị sau (None = config bị xoá)")
    default_value: str = Field(default="", description="Default value từ bddefaults.xml (nếu biết)")
    location_type: str = Field(
        description="Vị trí config trong XML: 'direct_P' | 'InstanceData' | 'MaskValueString' | 'attribute'",
    )
    xpath: str = Field(description="XPath tới element thay đổi")
    change_type: str = Field(description="'modified' | 'added' | 'removed'")


class BlockChange(BaseModel):
    """Tổng hợp thay đổi cho 1 block."""

    block_sid: str = Field(description="SID của block")
    block_name: str = Field(description="Tên block")
    block_type: str = Field(description="BlockType")
    mask_type: str = Field(default="", description="MaskType nếu có")
    system_file: str = Field(description="File XML chứa block")
    change_type: str = Field(description="'added' | 'removed' | 'modified'")
    config_changes: list[ConfigChange] = Field(default_factory=list)


class ModelDiff(BaseModel):
    """Raw diff giữa 2 model versions — output của utils/model_differ.py."""

    model_before: str = Field(description="Đường dẫn model before")
    model_after: str = Field(description="Đường dẫn model after")
    block_changes: list[BlockChange] = Field(default_factory=list)
    config_changes: list[ConfigChange] = Field(
        default_factory=list,
        description="Flat list tất cả config changes (tiện lọc theo rule)",
    )
    files_only_before: list[str] = Field(
        default_factory=list,
        description="XML files chỉ có trong model before (bị xoá)",
    )
    files_only_after: list[str] = Field(
        default_factory=list,
        description="XML files chỉ có trong model after (mới thêm)",
    )


class ConfigDiscovery(BaseModel):
    """Output của Agent 1.5 — ground truth config locations.

    Agent 2 dùng trực tiếp để biết config nằm ở đâu → skip exploration.
    """

    block_type: str = Field(description="BlockType, VD: 'Gain', 'SubSystem'")
    mask_type: str = Field(default="", description="MaskType nếu là TL block, VD: 'TL_Gain'")
    config_name: str = Field(description="Tên config cần check, VD: 'SaturateOnIntegerOverflow'")
    location_type: str = Field(
        default="",
        description=(
            "Config nằm ở đâu trong XML block element: "
            "'direct_P' (thẻ <P> trực tiếp) | "
            "'InstanceData' (trong <InstanceData>/<P>) | "
            "'MaskValueString' (pipe-separated trong <P Name='MaskValueString'>)"
        ),
    )
    xpath_pattern: str = Field(
        description=(
            "XPath pattern TỔNG QUÁT để tìm config trên TẤT CẢ blocks cùng type. "
            "VD: \".//Block[@BlockType='Gain']/P[@Name='SaturateOnIntegerOverflow']\""
        ),
    )
    default_value: str = Field(
        default="",
        description="Giá trị default khi config vắng trong XML (tra từ bddefaults.xml hoặc diff)",
    )
    value_format: str = Field(
        default="",
        description="Format giá trị: 'on/off', 'integer', 'fixdt(...)', 'string', etc.",
    )
    notes: str = Field(
        default="",
        description="Ghi chú đặc biệt: cách parse MaskValueString, special handling, etc.",
    )
