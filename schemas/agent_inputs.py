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

from pydantic import BaseModel, Field
from typing import Optional


# ── Agent 1: Data Reader ────────────────────────────


class Agent1Input(BaseModel):
    """Input cho Agent 1 (Data Reader).

    Example:
        >>> inp = Agent1Input(block_keyword="gain", config_name="SaturateOnIntegerOverflow")
        >>> print(inp.to_prompt())
        block_keyword: gain
        config_name: SaturateOnIntegerOverflow
    """

    block_keyword: str = Field(
        description="Keyword tìm block (lowercase), từ ParsedRule.block_keyword",
        examples=["gain", "inport", "abs", "sum", "delay"],
    )
    config_name: str = Field(
        description="Tên config cần check, từ ParsedRule.config_name",
        examples=["SaturateOnIntegerOverflow", "OutDataTypeStr", "PortDimensions"],
    )

    def to_prompt(self) -> str:
        return (
            f"block_keyword: {self.block_keyword}\n"
            f"config_name: {self.config_name}"
        )


# ── Agent 1.5: Diff Analyzer ────────────────────────


class Agent1_5Input(BaseModel):
    """Input cho Agent 1.5 (Diff Analyzer).

    Example:
        >>> inp = Agent1_5Input(
        ...     block_type="Gain",
        ...     config_name="SaturateOnIntegerOverflow",
        ...     name_ui="Gain",
        ...     config_map_analysis="SaturateOnIntegerOverflow trong <P>...",
        ...     diff_context='{"config_changes": [...], "bddefaults": {...}}'
        ... )
    """

    block_type: str = Field(
        description="BlockType trong XML, từ BlockMappingData.name_xml",
        examples=["Gain", "Abs", "SubSystem"],
    )
    config_name: str = Field(
        description="Tên config, từ ParsedRule.config_name",
        examples=["SaturateOnIntegerOverflow", "OutDataTypeStr"],
    )
    name_ui: str = Field(
        description="Tên UI, từ BlockMappingData.name_ui",
        examples=["Gain", "Abs"],
    )
    config_map_analysis: str = Field(
        description="Phân tích config từ Agent 1, từ BlockMappingData.config_map_analysis",
    )
    diff_context: str = Field(
        description="Raw JSON diff + bddefaults, từ build_agent_context()",
    )

    def to_prompt(self) -> str:
        return (
            f"block_type: {self.block_type}\n"
            f"config_name: {self.config_name}\n"
            f"block_mapping: name_ui={self.name_ui}, "
            f"config_map_analysis={self.config_map_analysis}\n\n"
            f"{self.diff_context}"
        )


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
        description="BlockType trong XML, từ BlockMappingData.name_xml",
        examples=["Gain", "Abs", "TL_Inport"],
    )
    block_name_ui: str = Field(
        description="Tên UI, từ BlockMappingData.name_ui",
        examples=["Gain", "Abs", "Inport"],
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

    # Cross-rule cache (từ rules trước cùng model)
    cache_summary: str = Field(
        default="",
        description="Cache summary từ rules trước cùng model (cross-rule knowledge)",
    )

    def to_prompt(self) -> str:
        context = (
            f"rule_id: {self.rule_id}\n"
            f"block: name_xml={self.block_name_xml}, name_ui={self.block_name_ui}\n"
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
        if self.cache_summary:
            context += f"\n\n{self.cache_summary}"
        return context

    @classmethod
    def from_pipeline(cls, rule, parsed_rule, block_data, config_discovery=None) -> "Agent2Input":
        """Factory từ pipeline data — dùng trong runner.py."""
        kwargs = dict(
            rule_id=rule.rule_id,
            block_name_xml=block_data.name_xml,
            block_name_ui=block_data.name_ui,
            config_name=parsed_rule.config_name,
            condition=str(parsed_rule.condition.value),
            expected_value=parsed_rule.expected_value,
            config_map_analysis=block_data.config_map_analysis,
            output_filename=f"check_rule_{rule.rule_id}.py",
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
        description="Kết quả mong đợi {total_blocks, pass, fail}",
        examples=[{"total_blocks": 19, "pass": 18, "fail": 1}],
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
        description="Validation status string (WRONG_RESULT, PARTIAL_PASS, CODE_ERROR)",
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
    config_discovery_location_type: Optional[str] = Field(default=None, examples=["direct_P"])
    config_discovery_xpath_pattern: Optional[str] = Field(default=None)
    config_discovery_default_value: Optional[str] = Field(default=None, examples=["off"])
    config_discovery_notes: Optional[str] = Field(default=None)

    # Knowledge handoff từ Agent 2 (Fix A)
    exploration_summary: str = Field(
        default="",
        description="Exploration log từ Agent 2 (verified knowledge, không cần re-explore)",
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

        # Core info
        parts.append(
            f"File code: {self.code_file_path}\n"
            f"Test case fail: {self.failed_test_case}\n"
            f"Actual result: {self.actual_result}\n"
            f"Expected result: {self.expected_result}\n"
            f"Block config analysis: {self.config_map_analysis}\n"
            f"Đây là lần điều tra thứ {self.attempt}"
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
                f"  location_type: {self.config_discovery_location_type}\n"
                f"  xpath_pattern: {self.config_discovery_xpath_pattern}\n"
                f"  default_value: {self.config_discovery_default_value}\n"
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
    ) -> "Agent5Input":
        """Factory từ state machine data.

        Args:
            exploration_summary: Knowledge handoff từ Agent 2 (Fix A).
            previous_findings: Investigation notes từ Agent 5 retries trước (Fix B).
        """
        escalated = sm.agent4_count > 0 and validation.status.value == "CODE_ERROR"
        kwargs = dict(
            code_file_path=validation.code_file_path,
            failed_test_case=validation.failed_test_case or "N/A",
            actual_result=validation.actual_result,
            expected_result=validation.expected_result,
            config_map_analysis=block_data.config_map_analysis,
            attempt=sm.agent5_count,
            is_escalated=escalated,
            agent4_count=sm.agent4_count,
            is_last_retry=sm.agent5_count >= sm.max_agent5,
            status_value=validation.status.value,
            test_cases_passed=validation.test_cases_passed,
            test_cases_total=validation.test_cases_total,
            error_history=list(sm._error_history),
            exploration_summary=exploration_summary,
            previous_findings=previous_findings or [],
        )
        if config_discovery:
            kwargs.update(
                config_discovery_location_type=config_discovery.location_type,
                config_discovery_xpath_pattern=config_discovery.xpath_pattern,
                config_discovery_default_value=config_discovery.default_value,
                config_discovery_notes=config_discovery.notes,
            )
        return cls(**kwargs)
