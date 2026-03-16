"""
Schemas cho dữ liệu Rule.
  - RuleInput: dòng đọc từ rules.json
  - RuleCondition: enum điều kiện
  - AdditionalConfig: config phụ (cho compound rules)
  - ParsedRule: output của Agent 0 (Rule Analyzer)
"""

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class RuleInput(BaseModel):
    """1 entry trong rules.json."""
    rule_id: str = Field(description="ID duy nhất, VD: 'R001'")
    description: str = Field(description="Mô tả luật bằng ngôn ngữ tự nhiên")


class RuleCondition(str, Enum):
    """Các loại điều kiện check rule được hỗ trợ."""
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    NOT_EMPTY = "not_empty"
    CONTAINS = "contains"
    IN_LIST = "in_list"


class AdditionalConfig(BaseModel):
    """Config phụ trong compound rule (nhiều config trên cùng block)."""
    config_name: str = Field(description="Tên config phụ, VD: 'OutDataTypeStr'")
    condition: RuleCondition = Field(description="Điều kiện check")
    expected_value: str = Field(default="", description="Giá trị mong đợi")


class ParsedRule(BaseModel):
    """Output của Agent 0 — dữ liệu cấu trúc từ rule text.

    Hỗ trợ:
      - Single config rule (mặc định, backward compatible)
      - Multi-config compound rule (AND/OR nhiều config trên cùng block)
      - Multi-block rule (nhiều block types cùng 1 rule)
      - Scope filtering (all instances, specific path, subsystem)
    """
    rule_id: str = ""        # Pipeline gán sau, LLM không biết rule_id
    block_keyword: str       # VD: "inport"
    rule_alias: str          # VD: "inport(targetlink)"
    config_name: str         # VD: "DataType" (primary config)
    condition: RuleCondition # "equal" | "not_equal" | "not_empty" | "contains" | "in_list"
    expected_value: str      # VD: "Inherit: auto" (giá trị cần check)

    # Multi-config: compound conditions (AND/OR nhiều config trên cùng block)
    additional_configs: list[AdditionalConfig] = Field(
        default_factory=list,
        description="Configs phụ nếu rule check nhiều config cùng lúc",
    )
    compound_logic: Literal["AND", "OR", "SINGLE"] = Field(
        default="SINGLE",
        description="Logic ghép: SINGLE (1 config), AND (tất cả phải đúng), OR (ít nhất 1 đúng)",
    )

    # Multi-block: rule áp dụng cho nhiều block types
    target_block_types: list[str] = Field(
        default_factory=list,
        description="Explicit list block types. Rỗng = auto-discover từ block_keyword",
    )

    # Scope filtering
    scope: Literal["all_instances", "specific_path", "subsystem"] = Field(
        default="all_instances",
        description="Phạm vi check: tất cả instances, path cụ thể, hoặc 1 subsystem",
    )
    scope_filter: str = Field(
        default="",
        description="Pattern lọc khi scope != 'all_instances'. VD: 'SubSystem1/*'",
    )
