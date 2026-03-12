"""
Schemas cho dữ liệu Rule.
  - RuleInput: dòng đọc từ rules.json
  - ParsedRule: output của Agent 0 (Rule Analyzer)
"""

from pydantic import BaseModel, Field


class RuleInput(BaseModel):
    """1 entry trong rules.json."""
    rule_id: str = Field(description="ID duy nhất, VD: 'R001'")
    description: str = Field(description="Mô tả luật bằng ngôn ngữ tự nhiên")


class ParsedRule(BaseModel):
    """Output của Agent 0 — dữ liệu cấu trúc từ rule text."""
    rule_id: str
    block_keyword: str       # VD: "inport"
    rule_alias: str          # VD: "inport(targetlink)"
    config_name: str         # VD: "DataType"
    condition: str           # "equal" | "not_equal" | "not_empty" | "contains" | "in_list"
    expected_value: str      # VD: "Inherit: auto" (giá trị cần check)
