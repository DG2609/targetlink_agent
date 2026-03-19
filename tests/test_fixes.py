"""
Tests cho các fixes: schema changes, tool changes, pipeline changes.
"""

import ast
import pytest
from unittest.mock import MagicMock

from schemas.block_schemas import BlockMappingData
from schemas.rule_schemas import ParsedRule, RuleCondition
from schemas.agent_inputs import Agent2Input
from schemas.validation_schemas import ValidationResult, ValidationStatus
from tools.code_tools import CodeToolkit


# ══════════════════════════════════════════════════════
# Fix 1: BlockMappingData new fields
# ══════════════════════════════════════════════════════


class TestBlockMappingDataNewFields:
    def test_default_xml_representation(self):
        b = BlockMappingData(
            name_ui="Gain", name_xml="Gain",
            config_map_analysis="test",
        )
        assert b.xml_representation == "unknown"
        assert b.search_confidence == 0
        assert b.source_type_pattern == ""

    def test_native_representation(self):
        b = BlockMappingData(
            name_ui="Gain", name_xml="Gain",
            xml_representation="native",
            search_confidence=95,
            config_map_analysis="test",
        )
        assert b.xml_representation == "native"
        assert b.search_confidence == 95

    def test_reference_representation(self):
        b = BlockMappingData(
            name_ui="Compare To Constant",
            name_xml="Compare To Constant",
            xml_representation="reference",
            search_confidence=80,
            source_type_pattern="Compare To Constant",
            config_map_analysis="test",
        )
        assert b.xml_representation == "reference"
        assert b.source_type_pattern == "Compare To Constant"

    def test_masked_representation(self):
        b = BlockMappingData(
            name_ui="Inport", name_xml="TL_Inport",
            xml_representation="masked",
            search_confidence=85,
            config_map_analysis="test",
        )
        assert b.xml_representation == "masked"

    def test_backward_compatible(self):
        """Old code chỉ set 3 fields vẫn hoạt động."""
        b = BlockMappingData(
            name_ui="Gain", name_xml="Gain",
            config_map_analysis="test analysis",
        )
        assert b.name_ui == "Gain"
        assert b.name_xml == "Gain"
        assert b.config_map_analysis == "test analysis"


# ══════════════════════════════════════════════════════
# Fix 2: Agent2Input empty block handling
# ══════════════════════════════════════════════════════


class TestAgent2InputEmptyBlock:
    def test_empty_block_prompt(self):
        inp = Agent2Input(
            rule_id="R099",
            block_name_xml="",
            block_name_ui="",
            config_name="SaturateOnIntegerOverflow",
            condition="equal",
            expected_value="on",
            config_map_analysis="config-only rule",
            output_filename="check_rule_R099.py",
        )
        prompt = inp.to_prompt()
        assert "KHÔNG XÁC ĐỊNH" in prompt
        assert "find_config_locations" in prompt

    def test_normal_block_prompt(self):
        inp = Agent2Input(
            rule_id="R001",
            block_name_xml="Gain",
            block_name_ui="Gain",
            config_name="SaturateOnIntegerOverflow",
            condition="equal",
            expected_value="on",
            config_map_analysis="test",
            output_filename="check_rule_R001.py",
        )
        prompt = inp.to_prompt()
        assert "name_xml=Gain" in prompt
        assert "KHÔNG XÁC ĐỊNH" not in prompt

    def test_xml_representation_in_prompt(self):
        inp = Agent2Input(
            rule_id="R001",
            block_name_xml="Compare To Constant",
            block_name_ui="Compare To Constant",
            xml_representation="reference",
            config_name="const",
            condition="equal",
            expected_value="42",
            config_map_analysis="test",
            output_filename="check_rule_R001.py",
        )
        prompt = inp.to_prompt()
        assert "xml_representation=reference" in prompt

    def test_from_pipeline_with_new_fields(self):
        rule = MagicMock()
        rule.rule_id = "R001"
        parsed = MagicMock()
        parsed.config_name = "SaturateOnIntegerOverflow"
        parsed.condition = RuleCondition.EQUAL
        parsed.expected_value = "on"
        block = BlockMappingData(
            name_ui="Gain", name_xml="Gain",
            xml_representation="native",
            search_confidence=95,
            config_map_analysis="test",
        )
        inp = Agent2Input.from_pipeline(rule, parsed, block)
        assert inp.xml_representation == "native"


# ══════════════════════════════════════════════════════
# Fix 3: ParsedRule empty block_keyword
# ══════════════════════════════════════════════════════


class TestParsedRuleEmptyKeyword:
    def test_empty_keyword_allowed(self):
        p = ParsedRule(
            block_keyword="",
            rule_alias="all blocks",
            config_name="SaturateOnIntegerOverflow",
            condition=RuleCondition.EQUAL,
            expected_value="on",
        )
        assert p.block_keyword == ""

    def test_normal_keyword(self):
        p = ParsedRule(
            block_keyword="gain",
            rule_alias="Gain block",
            config_name="SaturateOnIntegerOverflow",
            condition=RuleCondition.EQUAL,
            expected_value="on",
        )
        assert p.block_keyword == "gain"


# ══════════════════════════════════════════════════════
# Fix 4: ValidationResult actual_details
# ══════════════════════════════════════════════════════


class TestValidationResultDetails:
    def test_actual_details_default_none(self):
        r = ValidationResult(
            rule_id="R001",
            status=ValidationStatus.PASS,
            code_file_path="test.py",
        )
        assert r.actual_details is None

    def test_actual_details_with_blocks(self):
        r = ValidationResult(
            rule_id="R001",
            status=ValidationStatus.WRONG_RESULT,
            code_file_path="test.py",
            actual_details={
                "pass_block_names": ["Gain1", "Gain2"],
                "fail_block_names": ["Gain3"],
            },
        )
        assert r.actual_details["fail_block_names"] == ["Gain3"]


# ══════════════════════════════════════════════════════
# Fix 5: write_python_file syntax validation
# ══════════════════════════════════════════════════════


class TestWriteSyntaxValidation:
    @pytest.fixture
    def toolkit(self, tmp_path):
        return CodeToolkit(output_dir=str(tmp_path))

    def test_valid_code_writes(self, toolkit):
        result = toolkit.write_python_file("test.py", "x = 1\nprint(x)")
        assert "thành công" in result

    def test_syntax_error_rejected(self, toolkit):
        result = toolkit.write_python_file("test.py", "def foo(\n  x = ")
        assert "SYNTAX ERROR" in result
        # File should NOT be created
        file_path = toolkit._safe_path("test.py")
        assert not file_path.exists()

    def test_indentation_error_rejected(self, toolkit):
        result = toolkit.write_python_file("test.py", "if True:\nx = 1")
        assert "SYNTAX ERROR" in result

    def test_patch_syntax_error_rejected(self, toolkit):
        """patch_python_file cũng phải check syntax."""
        # Create valid file first
        toolkit.write_python_file("test.py", "x = 1")
        # Try to patch with invalid code
        result = toolkit.patch_python_file("test.py", "def foo(\n  x = ")
        assert "SYNTAX ERROR" in result
        # Original file should be unchanged
        content = toolkit._safe_path("test.py").read_text(encoding="utf-8")
        assert content == "x = 1"

    def test_rewrite_syntax_error_rejected(self, toolkit):
        """rewrite_advanced_code cũng phải check syntax."""
        result = toolkit.rewrite_advanced_code("test.py", "def foo(\n  x = ", "test")
        assert "SYNTAX ERROR" in result


# ══════════════════════════════════════════════════════
# Fix 6: Agent4Input & Agent5Input rule_id
# ══════════════════════════════════════════════════════


class TestAgentInputRuleId:
    def test_agent4_rule_id_in_prompt(self):
        from schemas.agent_inputs import Agent4Input
        inp = Agent4Input(
            rule_id="R001",
            code_file_path="generated_checks/check_rule_R001.py",
            failed_test_case="data/model.slx",
            stderr="some error",
            attempt=1,
        )
        prompt = inp.to_prompt()
        assert "Rule: R001" in prompt

    def test_agent5_rule_id_in_prompt(self):
        from schemas.agent_inputs import Agent5Input
        inp = Agent5Input(
            rule_id="R002",
            code_file_path="generated_checks/check_rule_R002.py",
            failed_test_case="data/model.slx",
            config_map_analysis="test",
            attempt=1,
        )
        prompt = inp.to_prompt()
        assert "Rule: R002" in prompt

    def test_agent5_from_state_machine_passes_rule_id(self):
        from schemas.agent_inputs import Agent5Input
        from pipeline.state_machine import RetryStateMachine
        sm = RetryStateMachine()
        sm.increment("agent5")
        validation = ValidationResult(
            rule_id="R003",
            status=ValidationStatus.WRONG_RESULT,
            code_file_path="test.py",
        )
        block_data = BlockMappingData(
            name_ui="Gain", name_xml="Gain",
            config_map_analysis="test",
        )
        inp = Agent5Input.from_state_machine(validation, block_data, sm)
        assert inp.rule_id == "R003"


# ══════════════════════════════════════════════════════
# Fix 7: input_validator empty block_keyword
# ══════════════════════════════════════════════════════


class TestInputValidatorEmptyKeyword:
    def test_empty_keyword_no_false_positive(self):
        """Empty block_keyword should NOT match all block types."""
        from utils.input_validator import validate_rule_input
        rule = ParsedRule(
            block_keyword="",
            rule_alias="all blocks",
            config_name="SaturateOnIntegerOverflow",
            condition=RuleCondition.EQUAL,
            expected_value="on",
        )
        # Use real model dir
        msgs = validate_rule_input(rule, "data/model4_CcodeGeneration")
        # Should NOT have warning about block_keyword matching — skip check entirely
        keyword_warnings = [m for m in msgs if "block_keyword" in m and "không khớp" in m]
        assert len(keyword_warnings) == 0


# ══════════════════════════════════════════════════════
# Fix 8: block_finder MaskValueString
# ══════════════════════════════════════════════════════


class TestBlockFinderMaskValueString:
    def test_mask_value_string_lookup(self):
        """get_block_config should find values in MaskValueString."""
        from lxml import etree
        from utils.block_finder import get_block_config
        xml = """<Block BlockType="SubSystem" Name="TL_Block1" SID="99">
            <P Name="MaskType">TL_Custom</P>
            <P Name="MaskNames">Gain|Offset|Init</P>
            <P Name="MaskValueString">5|10|0</P>
        </Block>"""
        block = etree.fromstring(xml)
        assert get_block_config(block, "Gain") == "5"
        assert get_block_config(block, "Offset") == "10"
        assert get_block_config(block, "Init") == "0"
        assert get_block_config(block, "NonExistent") is None

    def test_direct_p_overrides_mask_value_string(self):
        """Direct <P> should take priority over MaskValueString."""
        from lxml import etree
        from utils.block_finder import get_block_config
        xml = """<Block BlockType="SubSystem" Name="TL_Block1" SID="99">
            <P Name="Gain">DIRECT_VALUE</P>
            <P Name="MaskNames">Gain|Offset</P>
            <P Name="MaskValueString">5|10</P>
        </Block>"""
        block = etree.fromstring(xml)
        assert get_block_config(block, "Gain") == "DIRECT_VALUE"
