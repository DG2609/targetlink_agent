"""
Schemas cho dữ liệu Rule.
  - RuleInput: dòng đọc từ rules.json
  - RuleCondition: enum điều kiện
  - AdditionalConfig: config phụ (cho compound rules)
  - ParsedRule: output của Agent 0 (Rule Analyzer)
"""

from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class RuleInput(BaseModel):
    """1 entry trong rules.json.

    Example:
        >>> r = RuleInput(rule_id="R001", description="Tất cả Gain block phải có SaturateOnIntegerOverflow bằng 'on'")
    """

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "rule_id": "R001",
                "description": "Tất cả Gain block phải có SaturateOnIntegerOverflow bằng 'on'",
            },
            {
                "rule_id": "R002",
                "description": "Tất cả Abs block phải có SaturateOnIntegerOverflow bằng 'off'",
            },
        ]
    })

    rule_id: str = Field(description="ID duy nhất", examples=["R001", "R002", "R010"])
    description: str = Field(
        description="Mô tả luật bằng ngôn ngữ tự nhiên",
        examples=[
            "Tất cả Gain block phải có SaturateOnIntegerOverflow bằng 'on'",
            "Tất cả inport(targetlink) phải set DataType cụ thể, không được để Inherited",
        ],
    )


class RuleCondition(str, Enum):
    """Các loại điều kiện check rule được hỗ trợ."""
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    NOT_EMPTY = "not_empty"
    CONTAINS = "contains"
    IN_LIST = "in_list"
    # Numeric comparisons (convert to float before comparing)
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    REGEX_MATCH = "regex_match"   # re.search(expected_value, actual_value)


class AdditionalConfig(BaseModel):
    """Config phụ trong compound rule (nhiều config trên cùng block).

    Example:
        >>> c = AdditionalConfig(config_name="PortDimensions", condition=RuleCondition.NOT_EMPTY)
    """

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {"config_name": "PortDimensions", "condition": "not_empty", "expected_value": ""},
            {"config_name": "OutDataTypeStr", "condition": "not_equal", "expected_value": "Inherit: auto"},
        ]
    })

    config_name: str = Field(
        description="Tên config phụ",
        examples=["OutDataTypeStr", "PortDimensions", "RndMeth"],
    )
    condition: RuleCondition = Field(description="Điều kiện check: equal, not_equal, not_empty, contains, in_list, greater_than, less_than, greater_equal, less_equal, regex_match")
    expected_value: str = Field(
        default="",
        description="Giá trị mong đợi",
        examples=["Inherit: auto", "on", "off", ""],
    )


class ParsedRule(BaseModel):
    """Output của Agent 0 — dữ liệu cấu trúc từ rule text.

    Hỗ trợ:
      - Single config rule (mặc định)
      - Multi-config compound rule (AND/OR nhiều config trên cùng block)
      - Multi-block rule (nhiều block types cùng 1 rule)
      - Scope filtering (all instances, specific path, subsystem)

    Example — single rule:
        >>> p = ParsedRule(
        ...     block_keyword="gain", rule_alias="Gain block",
        ...     config_name="SaturateOnIntegerOverflow",
        ...     condition=RuleCondition.EQUAL, expected_value="on",
        ... )

    Example — compound rule:
        >>> p = ParsedRule(
        ...     block_keyword="inport", rule_alias="inport(targetlink)",
        ...     config_name="OutDataTypeStr",
        ...     condition=RuleCondition.NOT_EQUAL, expected_value="Inherit: auto",
        ...     additional_configs=[
        ...         AdditionalConfig(config_name="PortDimensions", condition=RuleCondition.NOT_EMPTY),
        ...     ],
        ...     compound_logic="AND",
        ...     target_block_types=["TL_Inport"],
        ... )

    Example — model-level rule:
        >>> p = ParsedRule(
        ...     block_keyword="",
        ...     rule_alias="Code generation target",
        ...     config_name="SystemTargetFile",
        ...     condition=RuleCondition.EQUAL, expected_value="ert.tlc",
        ...     rule_type="model_level",
        ...     config_component_class="Simulink.RTWCC",
        ... )
    """

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "rule_id": "R001",
                "block_keyword": "gain",
                "rule_alias": "Gain block",
                "config_name": "SaturateOnIntegerOverflow",
                "condition": "equal",
                "expected_value": "on",
                "additional_configs": [],
                "compound_logic": "SINGLE",
                "target_block_types": [],
                "scope": "all_instances",
                "scope_filter": "",
                "complexity_level": 1,
            },
            {
                "rule_id": "R002",
                "block_keyword": "abs",
                "rule_alias": "Abs block",
                "config_name": "SaturateOnIntegerOverflow",
                "condition": "equal",
                "expected_value": "off",
                "additional_configs": [],
                "compound_logic": "SINGLE",
                "target_block_types": [],
                "scope": "all_instances",
                "scope_filter": "",
                "complexity_level": 1,
            },
        ]
    })

    rule_id: str = ""        # Pipeline gán sau, LLM không biết rule_id
    block_keyword: str = Field(
        default="",
        description="Keyword tìm block, lowercase. Rỗng nếu rule không nói rõ block type — Agent 2 sẽ dùng find_config_locations() để tự xác định",
        examples=["gain", "inport", "abs", "sum", ""],
    )
    rule_alias: str = Field(
        description="Tên gốc của block trong rule text",
        examples=["Gain block", "inport(targetlink)", "Abs block"],
    )
    config_name: str = Field(
        description="Tên config chính cần check",
        examples=["SaturateOnIntegerOverflow", "OutDataTypeStr", "DataType"],
    )
    condition: RuleCondition = Field(
        description="Loại so sánh: equal, not_equal, not_empty, contains, in_list, greater_than, less_than, greater_equal, less_equal, regex_match",
    )
    expected_value: str = Field(
        description="Giá trị mong đợi",
        examples=["on", "off", "Inherit: auto", ""],
    )

    # Multi-config
    additional_configs: list[AdditionalConfig] = Field(
        default_factory=list,
        description="Configs phụ nếu rule check nhiều config cùng lúc",
    )
    compound_logic: Literal["AND", "OR", "SINGLE"] = Field(
        default="SINGLE",
        description="Logic ghép: SINGLE (1 config), AND (tất cả đúng), OR (ít nhất 1 đúng)",
    )

    # Multi-block
    target_block_types: list[str] = Field(
        default_factory=list,
        description="Explicit list block types. Rỗng = auto-discover từ block_keyword",
        examples=[[], ["TL_Inport"], ["Gain", "Sum"]],
    )

    # Scope
    scope: Literal["all_instances", "specific_path", "subsystem"] = Field(
        default="all_instances",
        description="Phạm vi check",
    )
    scope_filter: str = Field(
        default="",
        description="Pattern lọc khi scope != 'all_instances'",
        examples=["", "SubSystem1/*"],
    )

    # Complexity
    complexity_level: int = Field(
        default=1,
        ge=1,
        le=5,
        description=(
            "Độ phức tạp rule: "
            "1-2 = flat config check (1 block type, 1 config), "
            "3 = cross-subsystem (cần hierarchy path, depth filter), "
            "4 = connection-based (cần trace signal flow), "
            "5 = contextual (phụ thuộc parent subsystem context)"
        ),
        examples=[1, 2, 3, 4, 5],
    )

    # Rule type classification
    rule_type: Literal["block_level", "config_only", "model_level"] = Field(
        default="block_level",
        description=(
            "Loại rule: "
            "block_level = check config trên block cụ thể, "
            "config_only = tìm tất cả blocks có config (không biết block type), "
            "model_level = đọc từ Simulink ConfigSet (solver/codegen/hardware settings)"
        ),
    )
    config_component_class: Optional[str] = Field(
        default=None,
        description=(
            "Chỉ cho model_level: ClassName của ConfigSet component. "
            "VD: 'Simulink.RTWCC' (codegen), 'Simulink.SolverCC' (solver), "
            "'Simulink.HardwareCC' (hardware), 'Simulink.OptimizationCC' (optimization)"
        ),
    )
