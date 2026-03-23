"""
Input schemas cho tất cả agents.

Mỗi schema:
  - Fields với type, description, examples
  - to_prompt() → string gửi vào agent.arun()
  - Docstring với usage example

Agent 0: input = rule.description (str) → không cần schema
Agent 3: input = method params (code_file, test_cases) → không cần schema
"""

from __future__ import annotations

import json as _json

from pydantic import BaseModel, Field
from typing import Optional


# ── Agent 2: Code Generator ─────────────────────────


class Agent2Input(BaseModel):
    """Input cho Agent 2 (Code Generator).

    Example:
        >>> inp = Agent2Input(
        ...     rule_id="R001",
        ...     block_name_xml="Gain", block_name_ui="Gain",
        ...     config_name="SaturateOnIntegerOverflow",
        ...     condition="equal", expected_value="on",
        ...     config_map_analysis="<P Name='SaturateOnIntegerOverflow'> direct child...",
        ...     output_filename="check_rule_R001.py",
        ... )
        >>> prompt = inp.to_prompt()
        >>> assert "rule_id: R001" in prompt
    """

    rule_id: str = Field(
        description="ID rule, VD: 'R001'",
        examples=["R001", "R002", "R010"],
    )
    block_name_xml: str = Field(
        default="",
        description="Block identifier trong XML. Rỗng nếu rule không nói rõ block — Agent 2 dùng find_config_locations() để tự xác định",
        examples=["Gain", "Abs", "TL_Inport", "Compare To Constant", ""],
    )
    block_name_ui: str = Field(
        default="",
        description="Tên UI, từ BlockMappingData.name_ui. Rỗng nếu config-only rule",
        examples=["Gain", "Abs", "Inport", ""],
    )
    xml_representation: str = Field(
        default="unknown",
        description="Dạng block: native/reference/masked/unknown — từ BlockMappingData",
        examples=["native", "reference", "masked", "unknown"],
    )
    config_name: str = Field(
        description="Tên config cần check",
        examples=["SaturateOnIntegerOverflow", "OutDataTypeStr"],
    )
    condition: str = Field(
        description="Loại so sánh, từ ParsedRule.condition",
        examples=["equal", "not_equal", "not_empty", "contains", "in_list"],
    )
    expected_value: str = Field(
        description="Giá trị mong đợi, từ ParsedRule.expected_value",
        examples=["on", "off", "Inherit: auto"],
    )
    config_map_analysis: str = Field(
        description="Phân tích config từ Agent 1",
    )
    output_filename: str = Field(
        description="Tên file output, format: check_rule_{rule_id}.py",
        examples=["check_rule_R001.py", "check_rule_R002.py"],
    )

    # Optional: ground truth từ Agent 1.5
    config_discovery_block_type: Optional[str] = Field(default=None, examples=["Gain"])
    config_discovery_mask_type: Optional[str] = Field(default=None, examples=["", "TL_Gain"])
    config_discovery_config_name: Optional[str] = Field(default=None, examples=["SaturateOnIntegerOverflow"])
    config_discovery_location_type: Optional[str] = Field(default=None, examples=["direct_P", "InstanceData", "MaskValueString"])
    config_discovery_xpath_pattern: Optional[str] = Field(default=None, examples=[".//Block[@BlockType='Gain']/P[@Name='SaturateOnIntegerOverflow']"])
    config_discovery_default_value: Optional[str] = Field(default=None, examples=["off", "0", "Inherit: auto"])
    config_discovery_value_format: Optional[str] = Field(default=None, examples=["on/off", "integer", "fixdt(...)"])
    config_discovery_notes: Optional[str] = Field(default=None)

    # Multi-config / multi-block / scope (từ ParsedRule mở rộng)
    compound_logic: str = Field(
        default="SINGLE",
        description="Logic ghép: SINGLE (1 config), AND (tất cả đúng), OR (ít nhất 1 đúng)",
    )
    additional_configs_json: str = Field(
        default="",
        description="JSON serialized additional_configs từ ParsedRule (compound rules)",
    )
    target_block_types: list[str] = Field(
        default_factory=list,
        description="Explicit block types từ ParsedRule. Rỗng = auto-discover",
    )
    scope: str = Field(
        default="all_instances",
        description="Phạm vi check: all_instances, specific_path, subsystem",
    )
    scope_filter: str = Field(
        default="",
        description="Pattern lọc khi scope != 'all_instances'",
    )

    # Raw data injection (giảm exploration tool calls)
    blocks_raw_data: str = Field(
        default="",
        description="Raw JSON entry từ blocks.json cho block type này",
    )
    bddefaults_context: str = Field(
        default="",
        description="Default values từ bddefaults.xml cho block type này (JSON)",
    )

    # Complexity level (từ ParsedRule)
    complexity_level: int = Field(
        default=1,
        description=(
            "Độ phức tạp rule: 1-2=flat, 3=cross-subsystem, "
            "4=connection-based, 5=contextual"
        ),
    )

    # Cross-rule cache (từ rules trước cùng model)
    cache_summary: str = Field(
        default="",
        description="Cache summary từ rules trước cùng model (cross-rule knowledge)",
    )

    def to_prompt(self) -> str:
        if self.block_name_xml:
            block_line = (
                f"block: name_xml={self.block_name_xml}, name_ui={self.block_name_ui}, "
                f"xml_representation={self.xml_representation}"
            )
        else:
            block_line = (
                "block: KHÔNG XÁC ĐỊNH — rule chỉ nói về config, "
                "dùng find_config_locations() và list_all_block_types() để tìm tất cả block types có config này"
            )
        context = (
            f"rule_id: {self.rule_id}\n"
            f"{block_line}\n"
            f"config_name: {self.config_name}\n"
            f"condition: {self.condition}\n"
            f"expected_value: {self.expected_value}\n"
            f"config_map_analysis: {self.config_map_analysis}\n"
            f"output_filename: {self.output_filename}"
        )
        if self.config_discovery_location_type:
            context += (
                f"\n\nCONFIG DISCOVERY (ground truth from model diff — Agent 1.5):\n"
                f"  block_type: {self.config_discovery_block_type}\n"
                f"  mask_type: {self.config_discovery_mask_type}\n"
                f"  config_name: {self.config_discovery_config_name}\n"
                f"  location_type: {self.config_discovery_location_type}\n"
                f"  xpath_pattern: {self.config_discovery_xpath_pattern}\n"
                f"  default_value: {self.config_discovery_default_value}\n"
                f"  value_format: {self.config_discovery_value_format}\n"
                f"  notes: {self.config_discovery_notes}"
            )
        # ParsedRule extended fields (chỉ hiện khi non-default)
        if self.compound_logic != "SINGLE":
            context += f"\ncompound_logic: {self.compound_logic}"
            if self.additional_configs_json:
                context += f"\nadditional_configs: {self.additional_configs_json}"
        if self.target_block_types:
            context += f"\ntarget_block_types: {self.target_block_types}"
        if self.scope != "all_instances":
            context += f"\nscope: {self.scope}, scope_filter: {self.scope_filter}"
        if self.complexity_level > 1:
            context += f"\ncomplexity_level: {self.complexity_level}"

        if self.blocks_raw_data:
            context += f"\n\nBLOCKS_DICTIONARY_ENTRY (raw from blocks.json):\n{self.blocks_raw_data}"
        if self.bddefaults_context:
            context += f"\n\nBLOCK_DEFAULTS (from bddefaults.xml):\n{self.bddefaults_context}"
        if self.cache_summary:
            context += f"\n\n{self.cache_summary}"
        return context

    @classmethod
    def from_pipeline(
        cls, rule, parsed_rule, block_data, config_discovery=None,
        blocks_raw_data: str = "", bddefaults_context: str = "",
    ) -> "Agent2Input":
        """Factory từ pipeline data — dùng trong runner.py."""
        kwargs = dict(
            rule_id=rule.rule_id,
            block_name_xml=block_data.name_xml,
            block_name_ui=block_data.name_ui,
            xml_representation=getattr(block_data, "xml_representation", "unknown"),
            config_name=parsed_rule.config_name,
            condition=str(parsed_rule.condition.value),
            expected_value=parsed_rule.expected_value,
            config_map_analysis=block_data.config_map_analysis,
            output_filename=f"check_rule_{rule.rule_id}.py",
            compound_logic=parsed_rule.compound_logic,
            target_block_types=list(parsed_rule.target_block_types),
            scope=parsed_rule.scope,
            scope_filter=parsed_rule.scope_filter,
            complexity_level=parsed_rule.complexity_level,
            blocks_raw_data=blocks_raw_data,
            bddefaults_context=bddefaults_context,
        )
        if parsed_rule.additional_configs:
            kwargs["additional_configs_json"] = _json.dumps(
                [c.model_dump() for c in parsed_rule.additional_configs],
                ensure_ascii=False,
            )
        if config_discovery:
            kwargs.update(
                config_discovery_block_type=config_discovery.block_type,
                config_discovery_mask_type=config_discovery.mask_type,
                config_discovery_config_name=config_discovery.config_name,
                config_discovery_location_type=config_discovery.location_type,
                config_discovery_xpath_pattern=config_discovery.xpath_pattern,
                config_discovery_default_value=config_discovery.default_value,
                config_discovery_value_format=config_discovery.value_format,
                config_discovery_notes=config_discovery.notes,
            )
        return cls(**kwargs)


# ── Agent 4: Bug Fixer ──────────────────────────────


class Agent4Input(BaseModel):
    """Input cho Agent 4 (Bug Fixer).

    Example:
        >>> inp = Agent4Input(
        ...     code_file_path="generated_checks/check_rule_R001.py",
        ...     failed_test_case="data/model4_CcodeGeneration.slx",
        ...     stderr="AttributeError: 'NoneType' object has no attribute 'text'",
        ...     attempt=1,
        ... )
        >>> prompt = inp.to_prompt()
        >>> assert "check_rule_R001.py" in prompt
    """

    rule_id: str = Field(
        default="",
        description="ID rule đang xử lý, VD: 'R001'",
        examples=["R001", "R002"],
    )
    code_file_path: str = Field(
        description="Path file Python bị lỗi",
        examples=["generated_checks/check_rule_R001.py"],
    )
    failed_test_case: str = Field(
        description="model_path của test case gây lỗi",
        examples=["data/model4_CcodeGeneration.slx", "N/A"],
    )
    stderr: str = Field(
        description="Stderr từ subprocess (traceback)",
        examples=[
            "Traceback (most recent call last):\n"
            "  File \"check_rule_R001.py\", line 32\n"
            "    value = config_node.text\n"
            "AttributeError: 'NoneType' object has no attribute 'text'"
        ],
    )
    attempt: int = Field(
        description="Lần fix thứ mấy (1-based, đã increment)",
        examples=[1, 2, 3],
    )
    error_history: list[str] = Field(
        default_factory=list,
        description="Lịch sử lỗi từ các lần retry trước",
        examples=[
            [
                "CODE_ERROR(unknown): AttributeError: 'NoneType' has no attribute 'text'",
                "CODE_ERROR(xpath_error): lxml.etree.XPathError: Invalid expression",
            ]
        ],
    )

    def to_prompt(self) -> str:
        context = (
            f"Rule: {self.rule_id}\n"
            f"File bị lỗi: {self.code_file_path}\n"
            f"Test case fail: {self.failed_test_case}\n"
            f"Stderr:\n{self.stderr}\n"
            f"Đây là lần fix thứ {self.attempt}"
        )
        if self.error_history:
            context += "\n\n⚠ Lịch sử lỗi TRƯỚC ĐÓ (KHÔNG lặp lại cách fix đã thất bại):\n"
            for i, err in enumerate(self.error_history, 1):
                context += f"  {i}. {err}\n"
        return context


# ── Agent 5: Model Inspector ────────────────────────


class Agent5Input(BaseModel):
    """Input cho Agent 5 (Model Inspector).

    Example:
        >>> inp = Agent5Input(
        ...     code_file_path="generated_checks/check_rule_R001.py",
        ...     failed_test_case="data/model4_CcodeGeneration.slx",
        ...     actual_result={"total_blocks": 5, "pass_count": 5, "fail_count": 0},
        ...     expected_result={"total_blocks": 19, "pass": 18, "fail": 1},
        ...     config_map_analysis="SaturateOnIntegerOverflow trong <P>...",
        ...     attempt=1,
        ... )
        >>> prompt = inp.to_prompt()
        >>> assert "total_blocks" in prompt
    """

    rule_id: str = Field(
        default="",
        description="ID rule đang xử lý, VD: 'R001'",
        examples=["R001", "R002"],
    )
    # ParsedRule context — giúp Agent 5 biết logic check mong muốn
    condition: str = Field(
        default="",
        description="Check condition từ ParsedRule: equal, not_equal, not_empty, contains, in_list",
        examples=["equal", "not_equal", "not_empty"],
    )
    expected_value: str = Field(
        default="",
        description="Giá trị mong đợi từ ParsedRule",
        examples=["on", "off", "Inherit: auto"],
    )
    block_keyword: str = Field(
        default="",
        description="Block keyword từ ParsedRule",
        examples=["gain", "abs", "inport"],
    )
    code_file_path: str = Field(
        description="Path file Python cần điều tra",
        examples=["generated_checks/check_rule_R001.py"],
    )
    failed_test_case: str = Field(
        description="model_path của test case fail đầu tiên",
        examples=["data/model4_CcodeGeneration.slx", "N/A"],
    )
    actual_result: Optional[dict] = Field(
        default=None,
        description="Kết quả thực tế từ code {total_blocks, pass_count, fail_count}",
        examples=[{"total_blocks": 5, "pass_count": 5, "fail_count": 0}],
    )
    expected_result: Optional[dict] = Field(
        default=None,
        description="Kết quả mong đợi {total_blocks, pass_count, fail_count}",
        examples=[{"total_blocks": 19, "pass_count": 18, "fail_count": 1}],
    )
    actual_details: Optional[dict] = Field(
        default=None,
        description="Chi tiết block names pass/fail từ Agent 3 (giúp diagnose chính xác)",
        examples=[None, {"pass_block_names": ["Gain1"], "fail_block_names": ["Gain3"]}],
    )
    config_map_analysis: str = Field(
        description="Phân tích config từ Agent 1, BlockMappingData.config_map_analysis",
    )
    attempt: int = Field(
        description="Lần điều tra thứ mấy (1-based, đã increment)",
        examples=[1, 2, 3],
    )

    # Flags
    is_escalated: bool = Field(
        default=False,
        description="True nếu escalate từ Agent 4 (Agent 4 đã thất bại)",
    )
    agent4_count: int = Field(
        default=0,
        description="Số lần Agent 4 đã thử trước khi escalate",
    )
    is_last_retry: bool = Field(
        default=False,
        description="True nếu đây là lần retry cuối cùng",
    )
    status_value: str = Field(
        default="",
        description="Validation status (ValidationStatus enum value)",
        examples=["WRONG_RESULT", "PARTIAL_PASS", "CODE_ERROR"],
    )
    test_cases_passed: int = Field(default=0, description="Số test cases đã pass")
    test_cases_total: int = Field(default=0, description="Tổng test cases")

    # History
    error_history: list[str] = Field(
        default_factory=list,
        description="Lịch sử lỗi từ các lần retry trước",
    )

    # Ground truth (optional)
    config_discovery_block_type: Optional[str] = Field(default=None, examples=["Gain"])
    config_discovery_mask_type: Optional[str] = Field(default=None, examples=["", "TL_Gain"])
    config_discovery_config_name: Optional[str] = Field(default=None, examples=["SaturateOnIntegerOverflow"])
    config_discovery_location_type: Optional[str] = Field(default=None, examples=["direct_P"])
    config_discovery_xpath_pattern: Optional[str] = Field(default=None)
    config_discovery_default_value: Optional[str] = Field(default=None, examples=["off"])
    config_discovery_value_format: Optional[str] = Field(default=None, examples=["on/off", "integer"])
    config_discovery_notes: Optional[str] = Field(default=None)

    # Knowledge handoff từ Agent 2 (Fix A)
    exploration_summary: str = Field(
        default="",
        description="Exploration log từ Agent 2 (verified knowledge, không cần re-explore)",
    )

    # Complexity level (từ ParsedRule)
    complexity_level: int = Field(
        default=1,
        description=(
            "Độ phức tạp rule: 1-2=flat, 3=cross-subsystem, "
            "4=connection-based, 5=contextual"
        ),
    )

    # Carry forward từ Agent 5 retries trước (Fix B)
    previous_findings: list[str] = Field(
        default_factory=list,
        description="Investigation notes từ các lần Agent 5 trước",
    )

    def to_prompt(self) -> str:
        parts: list[str] = []

        # Escalation header
        if self.is_escalated:
            parts.append(
                f"⚠ ESCALATION: Agent 4 đã fix {self.agent4_count} lần nhưng code vẫn lỗi.\n"
                f"Loại lỗi có thể SAI GỐC — cần điều tra lại model XML."
            )

        # Partial pass note
        if self.status_value == "PARTIAL_PASS":
            parts.append(
                f"⚠ PARTIAL PASS: {self.test_cases_passed}/{self.test_cases_total} "
                f"test cases passed — code chạy được nhưng logic KHÔNG đúng cho mọi model."
            )

        # Rule check logic (từ ParsedRule)
        if self.condition and self.expected_value:
            parts.append(
                f"Rule Check Logic:\n"
                f"  block_keyword: {self.block_keyword}\n"
                f"  condition: {self.condition}\n"
                f"  expected_value: {self.expected_value}"
            )

        # Core info
        parts.append(
            f"Rule: {self.rule_id}\n"
            f"Status: {self.status_value}\n"
            f"File code: {self.code_file_path}\n"
            f"Test case fail: {self.failed_test_case}\n"
            f"Actual result: {self.actual_result}\n"
            f"Expected result: {self.expected_result}\n"
            f"Block config analysis: {self.config_map_analysis}\n"
            f"Đây là lần điều tra thứ {self.attempt}"
        )

        # Complexity level
        if self.complexity_level > 1:
            parts.append(f"complexity_level: {self.complexity_level}")

        # Block-level details from Agent 3 (giúp diagnose chính xác block nào lỗi)
        if self.actual_details:
            parts.append(
                f"Block details: pass={self.actual_details.get('pass_block_names', [])}, "
                f"fail={self.actual_details.get('fail_block_names', [])}"
            )

        # Last retry hint
        if self.is_last_retry:
            parts.append(
                "🔴 ĐÂY LÀ LẦN RETRY CUỐI — dùng read_raw_block_config() để đọc "
                "TOÀN BỘ raw config của block gây lỗi. Không bỏ sót gì."
            )

        # Error history
        if self.error_history:
            label = (
                "Agent 4 đã thất bại — cần approach MỚI HOÀN TOÀN"
                if self.is_escalated
                else "KHÔNG lặp lại approach đã thất bại"
            )
            parts.append(f"\n⚠ Lịch sử lỗi ({label}):")
            for i, err in enumerate(self.error_history, 1):
                parts.append(f"  {i}. {err}")

        # Previous Agent 5 investigation findings (Fix B)
        if self.previous_findings:
            parts.append(
                f"\n⚠ Agent 5 ĐÃ ĐIỀU TRA {len(self.previous_findings)} lần trước "
                f"— KHÔNG lặp lại, hãy thử approach KHÁC:"
            )
            for i, finding in enumerate(self.previous_findings, 1):
                parts.append(f"\n--- Lần {i} ---\n{finding}")

        # Config discovery ground truth
        if self.config_discovery_location_type:
            parts.append(
                f"\nCONFIG DISCOVERY (ground truth from model diff — Agent 1.5):\n"
                f"  block_type: {self.config_discovery_block_type}\n"
                f"  mask_type: {self.config_discovery_mask_type}\n"
                f"  config_name: {self.config_discovery_config_name}\n"
                f"  location_type: {self.config_discovery_location_type}\n"
                f"  xpath_pattern: {self.config_discovery_xpath_pattern}\n"
                f"  default_value: {self.config_discovery_default_value}\n"
                f"  value_format: {self.config_discovery_value_format}\n"
                f"  notes: {self.config_discovery_notes}"
            )

        # Agent 2 exploration knowledge (Fix A)
        if self.exploration_summary:
            parts.append(f"\n{self.exploration_summary}")

        return "\n\n".join(parts)

    @classmethod
    def from_state_machine(
        cls,
        validation,
        block_data,
        sm,
        config_discovery=None,
        exploration_summary: str = "",
        previous_findings: list[str] | None = None,
        parsed_rule=None,
    ) -> "Agent5Input":
        """Factory từ state machine data.

        Args:
            exploration_summary: Knowledge handoff từ Agent 2 (Fix A).
            previous_findings: Investigation notes từ Agent 5 retries trước (Fix B).
            parsed_rule: ParsedRule object — cung cấp condition/expected_value cho Agent 5.
        """
        # Agent 4 đã thử → luôn coi là escalated cho Agent 5.
        # Không dùng validation.status vì lúc này status có thể đã đổi
        # (VD: re-validation cho WRONG_RESULT thay vì CODE_ERROR).
        escalated = sm.agent4_count > 0
        kwargs = dict(
            rule_id=validation.rule_id,
            code_file_path=validation.code_file_path,
            failed_test_case=validation.failed_test_case or "N/A",
            actual_result=validation.actual_result,
            expected_result=validation.expected_result,
            actual_details=validation.actual_details,
            config_map_analysis=block_data.config_map_analysis,
            attempt=sm.agent5_count,
            is_escalated=escalated,
            agent4_count=sm.agent4_count,
            is_last_retry=sm.agent5_count >= sm.max_agent5,
            status_value=validation.status.value,
            test_cases_passed=validation.test_cases_passed,
            test_cases_total=validation.test_cases_total,
            error_history=sm.error_history,
            exploration_summary=exploration_summary,
            previous_findings=previous_findings or [],
        )
        if config_discovery:
            kwargs.update(
                config_discovery_block_type=config_discovery.block_type,
                config_discovery_mask_type=config_discovery.mask_type,
                config_discovery_config_name=config_discovery.config_name,
                config_discovery_location_type=config_discovery.location_type,
                config_discovery_xpath_pattern=config_discovery.xpath_pattern,
                config_discovery_default_value=config_discovery.default_value,
                config_discovery_value_format=config_discovery.value_format,
                config_discovery_notes=config_discovery.notes,
            )
        if parsed_rule:
            kwargs.update(
                condition=str(parsed_rule.condition.value),
                expected_value=parsed_rule.expected_value,
                block_keyword=parsed_rule.block_keyword,
                complexity_level=parsed_rule.complexity_level,
            )
        return cls(**kwargs)
