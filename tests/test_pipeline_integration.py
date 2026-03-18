"""Integration tests cho pipeline knowledge flow.

Test toàn bộ context/memory design:
  - Agent 2 → Agent 5 knowledge handoff (exploration_summary)
  - Agent 5 retry → retry carry-forward (previous_findings)
  - Cross-rule exploration cache (ExplorationCache)
  - Config discovery → exploration_summary injection
  - State machine integration with knowledge parameters
  - End-to-end knowledge flow qua runner.py
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from schemas.validation_schemas import ValidationResult, ValidationStatus
from schemas.block_schemas import BlockMappingData
from schemas.diff_schemas import ConfigDiscovery
from schemas.rule_schemas import ParsedRule, RuleCondition, RuleInput
from schemas.agent_inputs import Agent2Input, Agent5Input

from pipeline.state_machine import RetryStateMachine, RetryState
from pipeline.exploration_cache import (
    ExplorationCache,
    extract_exploration_summary,
    extract_investigation_notes,
)


# ── Helpers ──────────────────────────────────────────────


def _make_tool(name: str, args: dict = None, result: str = "") -> MagicMock:
    tool = MagicMock()
    tool.tool_name = name
    tool.tool_args = args or {}
    tool.result = result
    return tool


def _make_validation(
    status=ValidationStatus.WRONG_RESULT,
    actual=None,
    expected=None,
    stderr="",
    code_file="generated_checks/check_rule_R001.py",
    test_case="data/model.slx",
    passed=0,
    total=1,
) -> ValidationResult:
    return ValidationResult(
        rule_id="R001",
        status=status,
        actual_result=actual or {"total_blocks": 5, "pass_count": 5, "fail_count": 0},
        expected_result=expected or {"total_blocks": 19, "pass": 18, "fail": 1},
        stderr=stderr,
        failed_test_case=test_case,
        code_file_path=code_file,
        test_cases_passed=passed,
        test_cases_total=total,
    )


def _make_block_data() -> BlockMappingData:
    return BlockMappingData(
        name_ui="Gain",
        name_xml="Gain",
        config_map_analysis="SaturateOnIntegerOverflow in <P> direct child of <Block>.",
    )


def _make_config_discovery() -> ConfigDiscovery:
    return ConfigDiscovery(
        block_type="Gain",
        config_name="SaturateOnIntegerOverflow",
        location_type="direct_P",
        xpath_pattern=".//Block[@BlockType='Gain']/P[@Name='SaturateOnIntegerOverflow']",
        default_value="off",
        notes="Standard direct P config",
    )


def _make_parsed_rule() -> ParsedRule:
    return ParsedRule(
        rule_id="R001",
        block_keyword="gain",
        rule_alias="Gain block",
        config_name="SaturateOnIntegerOverflow",
        condition=RuleCondition.EQUAL,
        expected_value="on",
    )


# ── 1. Agent 2 → Agent 5 Knowledge Handoff ──────────────


class TestAgent2ToAgent5Handoff:

    def test_exploration_summary_injected_into_agent5_prompt(self):
        """exploration_summary from Agent 2 appears in Agent 5 context."""
        tools = [
            _make_tool("build_model_hierarchy", result="Root → SubSystem1 → SubSystem2"),
            _make_tool("find_blocks_recursive", {"block_type": "Gain"}, "18 Gain blocks"),
        ]
        summary = extract_exploration_summary(tools)

        inp = Agent5Input(
            code_file_path="check.py",
            failed_test_case="model.slx",
            config_map_analysis="analysis",
            attempt=1,
            exploration_summary=summary,
        )
        prompt = inp.to_prompt()
        assert "Root → SubSystem1 → SubSystem2" in prompt
        assert "18 Gain blocks" in prompt

    def test_empty_exploration_not_in_prompt(self):
        """Empty exploration_summary doesn't pollute prompt."""
        inp = Agent5Input(
            code_file_path="check.py",
            failed_test_case="model.slx",
            config_map_analysis="analysis",
            attempt=1,
            exploration_summary="",
        )
        prompt = inp.to_prompt()
        assert "Agent 2 Exploration" not in prompt

    def test_state_machine_passes_exploration_summary(self):
        """build_agent5_context correctly threads exploration_summary."""
        sm = RetryStateMachine(max_agent4=3, max_agent5=3)
        sm.agent5_count = 1
        validation = _make_validation()
        block_data = _make_block_data()

        context = sm.build_agent5_context(
            validation, block_data,
            exploration_summary="## Agent 2 Exploration Log\nHierarchy: Root → Sub",
        )
        assert "Root → Sub" in context


# ── 2. Agent 5 Retry Carry-Forward ──────────────────────


class TestAgent5RetryCarryForward:

    def test_previous_findings_in_prompt(self):
        """previous_findings appear in Agent 5 prompt."""
        findings = [
            "Đã điều tra:\n- find_blocks_recursive(Gain): 18 blocks",
            "Đã điều tra:\n- query_config(Gain, Sat): 17 on, 1 default",
        ]
        inp = Agent5Input(
            code_file_path="check.py",
            failed_test_case="model.slx",
            config_map_analysis="analysis",
            attempt=3,
            previous_findings=findings,
        )
        prompt = inp.to_prompt()
        assert "Agent 5 ĐÃ ĐIỀU TRA 2 lần" in prompt
        assert "find_blocks_recursive(Gain)" in prompt
        assert "query_config(Gain, Sat)" in prompt

    def test_empty_findings_not_in_prompt(self):
        """No previous_findings header when list is empty."""
        inp = Agent5Input(
            code_file_path="check.py",
            failed_test_case="model.slx",
            config_map_analysis="analysis",
            attempt=1,
            previous_findings=[],
        )
        prompt = inp.to_prompt()
        assert "ĐÃ ĐIỀU TRA" not in prompt

    def test_state_machine_passes_previous_findings(self):
        """build_agent5_context threads previous_findings."""
        sm = RetryStateMachine(max_agent4=3, max_agent5=3)
        sm.agent5_count = 2
        validation = _make_validation()
        block_data = _make_block_data()
        findings = ["finding 1", "finding 2"]

        context = sm.build_agent5_context(
            validation, block_data,
            previous_findings=findings,
        )
        assert "finding 1" in context
        assert "finding 2" in context

    def test_findings_capping_logic(self):
        """Simulate findings accumulation and capping at 3."""
        agent5_findings: list[str] = []

        for i in range(5):
            notes = f"finding_{i}"
            agent5_findings.append(notes)
            if len(agent5_findings) > 3:
                agent5_findings = agent5_findings[-3:]

        assert len(agent5_findings) == 3
        assert agent5_findings == ["finding_2", "finding_3", "finding_4"]

    def test_investigation_notes_extraction(self):
        """extract_investigation_notes captures Agent 5 tool calls."""
        tools = [
            _make_tool("find_blocks_recursive", {"block_type": "Gain"}, "18 blocks"),
            _make_tool("read_raw_block_config", {"block_sid": "42"}, "raw xml data"),
            _make_tool("rewrite_advanced_code", {"reason": "MaskType fix"}, "OK"),
        ]
        notes = extract_investigation_notes(tools)
        assert "find_blocks_recursive(Gain)" in notes
        assert "read_raw_block_config(SID=42)" in notes
        assert "REWRITE: MaskType fix" in notes


# ── 3. Cross-Rule Exploration Cache ──────────────────────


class TestCrossRuleCache:

    def test_cache_populated_and_reused(self):
        """Rule 1 populates cache, Rule 2 gets summary."""
        cache = ExplorationCache()

        # Rule 1: Agent 2 discovers hierarchy + blocks
        rule1_tools = [
            _make_tool("build_model_hierarchy", result="Root → SubSystem1"),
            _make_tool("find_blocks_recursive", {"block_type": "Gain"}, "18 Gain blocks"),
            _make_tool("query_config", {"block_type": "Gain", "config_name": "Sat"}, "17 on, 1 off"),
        ]
        cache.populate_from_tools(rule1_tools, block_type="Gain", config_name="Sat")

        # Rule 2: Same model, different block type — gets hierarchy
        summary = cache.get_summary_for_agent("Abs", "SaturateOnIntegerOverflow")
        assert "Root → SubSystem1" in summary
        # Abs blocks not cached
        assert "Gain blocks" not in summary

    def test_cache_same_block_type_gets_full_data(self):
        """Same block type gets hierarchy + blocks + config from cache."""
        cache = ExplorationCache()
        rule1_tools = [
            _make_tool("build_model_hierarchy", result="Root → Sub1"),
            _make_tool("find_blocks_recursive", {"block_type": "Gain"}, "18 Gain blocks"),
            _make_tool("query_config", {"block_type": "Gain", "config_name": "Sat"}, "17 on"),
        ]
        cache.populate_from_tools(rule1_tools, block_type="Gain", config_name="Sat")

        summary = cache.get_summary_for_agent("Gain", "Sat")
        assert "Root → Sub1" in summary
        assert "18 Gain blocks" in summary
        assert "17 on" in summary
        assert "SKIP" in summary

    def test_cache_injected_into_agent2_input(self):
        """cache_summary appears in Agent 2 prompt."""
        cache = ExplorationCache()
        cache.store_hierarchy("Root → SubSystem1")

        summary = cache.get_summary_for_agent("Gain", "Sat")
        inp = Agent2Input(
            rule_id="R002",
            block_name_xml="Gain",
            block_name_ui="Gain",
            config_name="Sat",
            condition="equal",
            expected_value="on",
            config_map_analysis="analysis",
            output_filename="check_rule_R002.py",
            cache_summary=summary,
        )
        prompt = inp.to_prompt()
        assert "KNOWN FROM PREVIOUS RULES" in prompt
        assert "Root → SubSystem1" in prompt


# ── 4. Config Discovery → Exploration Summary ───────────


class TestConfigDiscoveryInjection:

    def test_config_discovery_appended_to_exploration_summary(self):
        """Simulate runner.py logic: append config_discovery to exploration_summary."""
        # Agent 2 tools
        tools = [_make_tool("build_model_hierarchy", result="Root → Sub")]
        exploration_summary = extract_exploration_summary(tools)
        config_discovery = _make_config_discovery()

        # Simulate runner.py lines 298-314
        if config_discovery and exploration_summary:
            exploration_summary += (
                f"\n\n### Config Discovery (Agent 1.5 ground truth):\n"
                f"- location_type: {config_discovery.location_type}\n"
                f"- xpath_pattern: {config_discovery.xpath_pattern}\n"
                f"- default_value: {config_discovery.default_value}\n"
                f"- notes: {config_discovery.notes}"
            )

        assert "Config Discovery" in exploration_summary
        assert "direct_P" in exploration_summary
        assert "Block[@BlockType='Gain']" in exploration_summary

    def test_config_discovery_standalone_when_no_exploration(self):
        """When Agent 2 has no tools, config_discovery becomes the exploration_summary."""
        exploration_summary = ""
        config_discovery = _make_config_discovery()

        # Simulate runner.py logic
        if config_discovery and not exploration_summary:
            exploration_summary = (
                f"## Config Discovery (Agent 1.5 ground truth):\n"
                f"- location_type: {config_discovery.location_type}\n"
                f"- xpath_pattern: {config_discovery.xpath_pattern}\n"
                f"- default_value: {config_discovery.default_value}\n"
                f"- notes: {config_discovery.notes}"
            )

        assert "direct_P" in exploration_summary
        assert "Agent 1.5" in exploration_summary

    def test_config_discovery_in_agent5_input_direct(self):
        """Agent 5 also receives config_discovery directly via its own fields."""
        cd = _make_config_discovery()
        inp = Agent5Input(
            code_file_path="check.py",
            failed_test_case="model.slx",
            config_map_analysis="analysis",
            attempt=1,
            config_discovery_location_type=cd.location_type,
            config_discovery_xpath_pattern=cd.xpath_pattern,
            config_discovery_default_value=cd.default_value,
            config_discovery_notes=cd.notes,
        )
        prompt = inp.to_prompt()
        assert "CONFIG DISCOVERY" in prompt
        assert "direct_P" in prompt


# ── 5. State Machine Full Integration ────────────────────


class TestStateMachineKnowledgeFlow:

    def test_full_retry_loop_knowledge_accumulation(self):
        """Simulate full retry: WRONG_RESULT → INSPECT → re-validate."""
        sm = RetryStateMachine(max_agent4=2, max_agent5=3)
        block_data = _make_block_data()
        config_discovery = _make_config_discovery()
        exploration_summary = "## Agent 2 Log\nHierarchy: Root → Sub"
        agent5_findings: list[str] = []

        # First validation: WRONG_RESULT
        validation = _make_validation(status=ValidationStatus.WRONG_RESULT)
        state = sm.next_state(validation)
        assert state == RetryState.INSPECT

        # Agent 5 attempt 1
        sm.increment("agent5")
        sm.record_error(validation)
        context = sm.build_agent5_context(
            validation, block_data, config_discovery,
            exploration_summary=exploration_summary,
            previous_findings=agent5_findings,
        )
        # Should contain exploration + config discovery + no previous findings
        assert "Root → Sub" in context
        assert "CONFIG DISCOVERY" in context
        assert "ĐÃ ĐIỀU TRA" not in context

        # Simulate Agent 5 investigation
        agent5_tools = [
            _make_tool("find_blocks_recursive", {"block_type": "Gain"}, "18 blocks"),
        ]
        notes = extract_investigation_notes(agent5_tools)
        agent5_findings.append(notes)

        # Re-validate: still WRONG_RESULT
        validation2 = _make_validation(status=ValidationStatus.WRONG_RESULT)
        state = sm.next_state(validation2)
        assert state == RetryState.INSPECT

        # Agent 5 attempt 2
        sm.increment("agent5")
        sm.record_error(validation2)
        context2 = sm.build_agent5_context(
            validation2, block_data, config_discovery,
            exploration_summary=exploration_summary,
            previous_findings=agent5_findings,
        )
        # Should now contain previous findings
        assert "ĐÃ ĐIỀU TRA 1 lần" in context2
        assert "find_blocks_recursive(Gain)" in context2

    def test_escalation_from_agent4_to_agent5(self):
        """CODE_ERROR → Agent 4 fails → escalate to Agent 5 with full context."""
        sm = RetryStateMachine(max_agent4=1, max_agent5=2)
        block_data = _make_block_data()

        # First: CODE_ERROR → BUG_FIX
        validation = _make_validation(
            status=ValidationStatus.CODE_ERROR,
            stderr="AttributeError: NoneType",
        )
        state = sm.next_state(validation)
        assert state == RetryState.BUG_FIX

        sm.increment("agent4")
        sm.record_error(validation)

        # After Agent 4 fix: still CODE_ERROR → escalate to INSPECT
        validation2 = _make_validation(
            status=ValidationStatus.CODE_ERROR,
            stderr="lxml.etree.XPathError: Invalid expression",
        )
        state = sm.next_state(validation2)
        assert state == RetryState.INSPECT

        # Agent 5 gets escalation info
        sm.increment("agent5")
        sm.record_error(validation2)
        context = sm.build_agent5_context(
            validation2, block_data,
            exploration_summary="Agent 2 explored hierarchy",
        )
        assert "ESCALATION" in context
        assert "Agent 2 explored hierarchy" in context

    def test_last_retry_flag(self):
        """Last retry sets is_last_retry flag in Agent 5 context."""
        sm = RetryStateMachine(max_agent4=1, max_agent5=2)
        block_data = _make_block_data()

        # Burn through retries
        validation = _make_validation(status=ValidationStatus.WRONG_RESULT)
        sm.next_state(validation)
        sm.increment("agent5")
        sm.record_error(validation)

        validation2 = _make_validation(status=ValidationStatus.WRONG_RESULT)
        sm.next_state(validation2)
        sm.increment("agent5")
        sm.record_error(validation2)

        # agent5_count=2, max=2 → is_last_retry=True
        context = sm.build_agent5_context(validation2, block_data)
        assert "LẦN RETRY CUỐI" in context


# ── 6. Null Safety ──────────────────────────────────────


class TestNullSafety:

    def test_extract_exploration_summary_none_tools(self):
        """extract_exploration_summary handles None tools list."""
        assert extract_exploration_summary(None) == ""
        assert extract_exploration_summary([]) == ""

    def test_extract_investigation_notes_none_tools(self):
        """extract_investigation_notes handles None tools list."""
        assert extract_investigation_notes(None) == ""
        assert extract_investigation_notes([]) == ""

    def test_tool_with_none_result(self):
        """Tools with None result are skipped."""
        tool = MagicMock()
        tool.tool_name = "build_model_hierarchy"
        tool.tool_args = {}
        tool.result = None
        assert extract_exploration_summary([tool]) == ""

    def test_tool_without_attributes(self):
        """Tools without tool_name attribute are skipped."""
        tool = MagicMock(spec=[])  # No attributes
        assert extract_exploration_summary([tool]) == ""

    def test_getattr_response_tools_pattern(self):
        """Verify the defensive getattr pattern used in runner.py."""
        # Response with no tools attribute
        response = MagicMock(spec=["content"])
        tools = getattr(response, "tools", None) or []
        assert tools == []

        # Response with None tools
        response2 = MagicMock()
        response2.tools = None
        tools2 = getattr(response2, "tools", None) or []
        assert tools2 == []

        # Response with actual tools
        response3 = MagicMock()
        response3.tools = [_make_tool("build_model_hierarchy", result="data")]
        tools3 = getattr(response3, "tools", None) or []
        assert len(tools3) == 1


# ── 7. trace_cross_subsystem Extraction ─────────────────


class TestCrossSubsystemExtraction:

    def test_trace_cross_subsystem_in_exploration_summary(self):
        """trace_cross_subsystem appears in exploration summary."""
        tools = [
            _make_tool("trace_cross_subsystem", {"block_sid": "10", "direction": "outgoing"}, "3 connections"),
        ]
        summary = extract_exploration_summary(tools)
        assert "Cross-subsystem Trace" in summary
        assert "SID=10" in summary
        assert "outgoing" in summary

    def test_trace_cross_subsystem_in_investigation_notes(self):
        """trace_cross_subsystem appears in investigation notes."""
        tools = [
            _make_tool("trace_cross_subsystem", {"block_sid": "10", "direction": "incoming"}, "2 connections"),
        ]
        notes = extract_investigation_notes(tools)
        assert "trace_cross_subsystem(SID=10, incoming)" in notes


# ── 8. End-to-End Knowledge Chain ────────────────────────


class TestEndToEndKnowledgeChain:

    def test_full_chain_agent2_cache_agent5_findings(self):
        """Simulate full chain: Agent 2 → cache → Agent 5 → findings → retry."""
        cache = ExplorationCache()

        # ── Rule 1 ──
        # Agent 2 explores model
        agent2_tools = [
            _make_tool("build_model_hierarchy", result="Root → SubSystem1 → SubSystem2"),
            _make_tool("find_blocks_recursive", {"block_type": "Gain"}, "18 Gain blocks in 3 systems"),
            _make_tool("query_config", {"block_type": "Gain", "config_name": "Sat"}, "17 on, 1 off"),
        ]
        exploration_summary_r1 = extract_exploration_summary(agent2_tools)
        cache.populate_from_tools(agent2_tools, block_type="Gain", config_name="Sat")

        # Agent 5 investigates (WRONG_RESULT)
        agent5_tools_r1 = [
            _make_tool("find_blocks_recursive", {"block_type": "Gain"}, "18 blocks confirmed"),
            _make_tool("query_config", {"block_type": "Gain", "config_name": "Sat"}, "17 on, 1 default off"),
            _make_tool("rewrite_advanced_code", {"reason": "default value handling"}, "OK"),
        ]
        notes_r1 = extract_investigation_notes(agent5_tools_r1)

        assert "Agent 2 Exploration Log" in exploration_summary_r1
        assert "Đã điều tra:" in notes_r1
        assert "REWRITE: default value handling" in notes_r1

        # ── Rule 2 (same model, different block type) ──
        cache_summary_r2 = cache.get_summary_for_agent("Abs", "SaturateOnIntegerOverflow")
        assert "Root → SubSystem1 → SubSystem2" in cache_summary_r2
        assert "SKIP" in cache_summary_r2

        # Agent 2 for Rule 2 gets cache injected
        agent2_input_r2 = Agent2Input(
            rule_id="R002",
            block_name_xml="Abs",
            block_name_ui="Abs",
            config_name="SaturateOnIntegerOverflow",
            condition="equal",
            expected_value="off",
            config_map_analysis="analysis",
            output_filename="check_rule_R002.py",
            cache_summary=cache_summary_r2,
        )
        prompt_r2 = agent2_input_r2.to_prompt()
        assert "KNOWN FROM PREVIOUS RULES" in prompt_r2

    def test_multiple_retries_accumulate_and_cap(self):
        """5 Agent 5 retries → findings capped at 3."""
        sm = RetryStateMachine(max_agent4=0, max_agent5=5)
        block_data = _make_block_data()
        agent5_findings: list[str] = []

        for i in range(5):
            validation = _make_validation(status=ValidationStatus.WRONG_RESULT)
            state = sm.next_state(validation)
            assert state == RetryState.INSPECT

            sm.increment("agent5")
            sm.record_error(validation)

            context = sm.build_agent5_context(
                validation, block_data,
                previous_findings=agent5_findings,
            )

            # Verify previous findings count
            if i == 0:
                assert "ĐÃ ĐIỀU TRA" not in context
            elif i >= 1:
                assert f"ĐÃ ĐIỀU TRA {len(agent5_findings)} lần" in context

            # Simulate Agent 5 investigation
            tools = [
                _make_tool("find_blocks_recursive", {"block_type": "Gain"}, f"attempt {i+1}"),
            ]
            notes = extract_investigation_notes(tools)
            agent5_findings.append(notes)
            if len(agent5_findings) > 3:
                agent5_findings = agent5_findings[-3:]

        # After 5 retries, only last 3 findings kept
        assert len(agent5_findings) == 3
        assert "attempt 3" in agent5_findings[0]
        assert "attempt 4" in agent5_findings[1]
        assert "attempt 5" in agent5_findings[2]
