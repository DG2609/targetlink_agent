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
        assert "name_xml: Gain" in prompt
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
        assert "xml_representation: reference" in prompt

    def test_from_pipeline_with_new_fields(self):
        rule = MagicMock()
        rule.rule_id = "R001"
        parsed = MagicMock()
        parsed.config_name = "SaturateOnIntegerOverflow"
        parsed.condition = RuleCondition.EQUAL
        parsed.expected_value = "on"
        parsed.additional_configs = []
        parsed.compound_logic = "SINGLE"
        parsed.target_block_types = []
        parsed.scope = "all_instances"
        parsed.scope_filter = ""
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


# ══════════════════════════════════════════════════════
# Fix 9: skill_loader include_references + helpers
# ══════════════════════════════════════════════════════


class TestSkillLoaderReferences:
    def test_load_skill_without_references(self):
        """Default: references NOT included."""
        from utils.skill_loader import load_skill
        body = load_skill("code-generator")
        assert len(body) == 1
        # Templates moved to references — should NOT be in body
        assert "Template code — Config Check Rule" not in body[0]

    def test_load_skill_with_references(self):
        """include_references=True appends references/*.md."""
        from utils.skill_loader import load_skill
        body = load_skill("code-generator", include_references=True)
        assert len(body) == 1
        # Templates from references/templates.md should be appended
        assert "Template — Config Check Rule" in body[0]
        assert "Template — Forbidden Block Rule" in body[0]
        assert "Template — Config-Only Rule" in body[0]

    def test_list_skill_references(self):
        from utils.skill_loader import list_skill_references
        refs = list_skill_references("code-generator")
        assert "templates.md" in refs

    def test_load_skill_reference(self):
        from utils.skill_loader import load_skill_reference
        content = load_skill_reference("code-generator", "templates.md")
        assert "find_blocks" in content
        assert "get_block_config" in content

    def test_load_skill_reference_not_found(self):
        from utils.skill_loader import load_skill_reference
        with pytest.raises(FileNotFoundError):
            load_skill_reference("code-generator", "nonexistent.md")

    def test_skill_without_references_dir(self):
        """Skills without references/ return empty list."""
        from utils.skill_loader import list_skill_references
        refs = list_skill_references("rule-analyzer")
        assert refs == []


# ══════════════════════════════════════════════════════
# Fix 10: Agent2Input compound fields in to_prompt()
# ══════════════════════════════════════════════════════


class TestAgent2InputCompoundPrompt:
    def test_single_logic_hidden(self):
        """SINGLE compound_logic should NOT appear in prompt (default)."""
        inp = Agent2Input(
            rule_id="R001",
            block_name_xml="Gain", block_name_ui="Gain",
            config_name="SaturateOnIntegerOverflow",
            condition="equal", expected_value="on",
            config_map_analysis="test",
            output_filename="check_rule_R001.py",
        )
        prompt = inp.to_prompt()
        assert "compound_logic" not in prompt
        assert "target_block_types" not in prompt
        assert "scope:" not in prompt

    def test_and_logic_shown(self):
        """AND compound_logic should appear in prompt."""
        inp = Agent2Input(
            rule_id="R010",
            block_name_xml="Gain", block_name_ui="Gain",
            config_name="SaturateOnIntegerOverflow",
            condition="equal", expected_value="on",
            compound_logic="AND",
            additional_configs_json='[{"config_name": "OutDataTypeStr", "condition": "equal", "expected_value": "Inherit: auto"}]',
            config_map_analysis="test",
            output_filename="check_rule_R010.py",
        )
        prompt = inp.to_prompt()
        assert "compound_logic: AND" in prompt
        assert "additional_configs:" in prompt
        assert "OutDataTypeStr" in prompt

    def test_target_block_types_shown(self):
        """Explicit target_block_types should appear in prompt."""
        inp = Agent2Input(
            rule_id="R020",
            block_name_xml="", block_name_ui="",
            config_name="SaturateOnIntegerOverflow",
            condition="equal", expected_value="on",
            target_block_types=["Gain", "Abs", "Sum"],
            config_map_analysis="test",
            output_filename="check_rule_R020.py",
        )
        prompt = inp.to_prompt()
        assert "target_block_types:" in prompt
        assert "Gain" in prompt
        assert "KHÔNG XÁC ĐỊNH" in prompt

    def test_scope_filter_shown(self):
        """Non-default scope should appear in prompt."""
        inp = Agent2Input(
            rule_id="R030",
            block_name_xml="Gain", block_name_ui="Gain",
            config_name="SaturateOnIntegerOverflow",
            condition="equal", expected_value="on",
            scope="subsystem",
            scope_filter="Controller/*",
            config_map_analysis="test",
            output_filename="check_rule_R030.py",
        )
        prompt = inp.to_prompt()
        assert "scope: subsystem" in prompt
        assert "scope_filter: Controller/*" in prompt

    def test_from_pipeline_compound_fields(self):
        """from_pipeline passes compound fields correctly."""
        from schemas.rule_schemas import ParsedRule, RuleCondition, AdditionalConfig
        rule = MagicMock()
        rule.rule_id = "R010"
        parsed = ParsedRule(
            block_keyword="gain",
            rule_alias="Gain compound",
            config_name="SaturateOnIntegerOverflow",
            condition=RuleCondition.EQUAL,
            expected_value="on",
            compound_logic="AND",
            additional_configs=[
                AdditionalConfig(
                    config_name="OutDataTypeStr",
                    condition=RuleCondition.EQUAL,
                    expected_value="Inherit: auto",
                )
            ],
            target_block_types=["Gain"],
            scope="subsystem",
            scope_filter="Controller/*",
        )
        block = BlockMappingData(
            name_ui="Gain", name_xml="Gain",
            config_map_analysis="test",
        )
        inp = Agent2Input.from_pipeline(rule, parsed, block)
        assert inp.compound_logic == "AND"
        assert "OutDataTypeStr" in inp.additional_configs_json
        assert inp.target_block_types == ["Gain"]
        assert inp.scope == "subsystem"
        assert inp.scope_filter == "Controller/*"

    def test_tier2_ground_truth_shown(self):
        """config_discovery fields should produce Tier 2 block."""
        inp = Agent2Input(
            rule_id="R001",
            block_name_xml="Gain", block_name_ui="Gain",
            config_name="SaturateOnIntegerOverflow",
            condition="equal", expected_value="on",
            config_map_analysis="test",
            output_filename="check_rule_R001.py",
            config_discovery_location_type="direct_P",
            config_discovery_block_type="Gain",
            config_discovery_xpath_pattern=".//Block[@BlockType='Gain']/P[@Name='SaturateOnIntegerOverflow']",
        )
        prompt = inp.to_prompt()
        assert "TIER 2" in prompt
        assert "GROUND TRUTH" in prompt
        assert "direct_P" in prompt
        assert "BỎ QUA" in prompt

    def test_tier4_suppressed_when_config_discovery_present(self):
        """cache_summary should NOT appear when config_discovery is also set."""
        inp = Agent2Input(
            rule_id="R001",
            block_name_xml="Gain", block_name_ui="Gain",
            config_name="SaturateOnIntegerOverflow",
            condition="equal", expected_value="on",
            config_map_analysis="test",
            output_filename="check_rule_R001.py",
            cache_summary="CACHE: previously found direct_P at xpath X",
            config_discovery_location_type="direct_P",
        )
        prompt = inp.to_prompt()
        assert "TIER 2" in prompt          # ground truth present
        assert "TIER 4" not in prompt      # cache suppressed
        assert "CACHE" not in prompt       # cache content not leaked

    def test_tier5_shown_for_complex_rule(self):
        """complexity_level >= 3 should trigger Tier 5 with complexity_level shown."""
        inp = Agent2Input(
            rule_id="R040",
            block_name_xml="SubSystem", block_name_ui="SubSystem",
            config_name="SomeConfig",
            condition="equal", expected_value="on",
            config_map_analysis="test",
            output_filename="check_rule_R040.py",
            complexity_level=3,
        )
        prompt = inp.to_prompt()
        assert "TIER 5" in prompt
        assert "complexity_level: 3" in prompt
        assert "compound_logic" not in prompt   # not compound, only complex


# ══════════════════════════════════════════════════════
# Fix 11: Audit fixes — tool_call_limit, field naming,
#          Literal types, actual_details handoff
# ══════════════════════════════════════════════════════


class TestAuditFixes:
    def test_agent0_has_tool_call_limit(self):
        """Agent 0 should have explicit tool_call_limit."""
        from agents.agent0_rule_analyzer import create_agent0
        agent = create_agent0()
        assert agent.tool_call_limit == 5

    def test_agent1_has_tool_call_limit(self):
        """Agent 1 should have explicit tool_call_limit."""
        from agents.agent1_data_reader import create_agent1
        agent = create_agent1("data/blocks.json")
        assert agent.tool_call_limit == 5

    def test_result_field_naming_consistent(self):
        """Validator expected_summary should use pass_count/fail_count (not pass/fail)."""
        from agents.agent3_validator import Validator
        from schemas.validation_schemas import TestCase
        v = Validator()
        tc = TestCase(
            model_path="data/model4_CcodeGeneration.slx",
            expected_total_blocks=19, expected_pass=18, expected_fail=1,
        )
        # Test JSON parse error case — expected_summary keys should match actual_summary
        result = v._compare("invalid json", tc)
        expected_keys = set(result["expected_summary"].keys())
        assert "pass_count" in expected_keys
        assert "fail_count" in expected_keys
        assert "pass" not in expected_keys
        assert "fail" not in expected_keys

    def test_config_change_location_type_literal(self):
        """ConfigChange.location_type should accept valid Literals only."""
        from schemas.diff_schemas import ConfigChange
        # Valid
        cc = ConfigChange(
            block_sid="1", block_name="Gain1", block_type="Gain",
            system_file="system_root.xml", config_name="Gain",
            location_type="direct_P", xpath=".//Block", change_type="modified",
        )
        assert cc.location_type == "direct_P"
        assert cc.change_type == "modified"

    def test_config_change_invalid_location_type_rejected(self):
        """ConfigChange with invalid location_type should fail validation."""
        from schemas.diff_schemas import ConfigChange
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ConfigChange(
                block_sid="1", block_name="Gain1", block_type="Gain",
                system_file="system_root.xml", config_name="Gain",
                location_type="INVALID", xpath=".//Block", change_type="modified",
            )

    def test_agent5_actual_details_in_prompt(self):
        """Agent5Input should include actual_details in prompt."""
        from schemas.agent_inputs import Agent5Input
        inp = Agent5Input(
            rule_id="R001",
            code_file_path="test.py",
            failed_test_case="model.slx",
            actual_details={"pass_block_names": ["G1"], "fail_block_names": ["G3"]},
            config_map_analysis="test",
            attempt=1,
        )
        prompt = inp.to_prompt()
        assert "G3" in prompt
        assert "fail=" in prompt

    def test_agent5_no_details_no_block_section(self):
        """Agent5Input without actual_details should not have block details."""
        from schemas.agent_inputs import Agent5Input
        inp = Agent5Input(
            rule_id="R001",
            code_file_path="test.py",
            failed_test_case="model.slx",
            config_map_analysis="test",
            attempt=1,
        )
        prompt = inp.to_prompt()
        assert "Block details" not in prompt

    def test_agent5_from_state_machine_passes_actual_details(self):
        """from_state_machine should pass actual_details from validation."""
        from schemas.agent_inputs import Agent5Input
        from pipeline.state_machine import RetryStateMachine
        sm = RetryStateMachine()
        sm.increment("agent5")
        validation = ValidationResult(
            rule_id="R001",
            status=ValidationStatus.WRONG_RESULT,
            code_file_path="test.py",
            actual_details={"pass_block_names": ["G1"], "fail_block_names": ["G3"]},
        )
        block_data = BlockMappingData(
            name_ui="Gain", name_xml="Gain",
            config_map_analysis="test",
        )
        inp = Agent5Input.from_state_machine(validation, block_data, sm)
        assert inp.actual_details == {"pass_block_names": ["G1"], "fail_block_names": ["G3"]}


# ══════════════════════════════════════════════════════
# Fix 12: Zip Slip protection via Path.relative_to()
# ══════════════════════════════════════════════════════


class TestZipSlipProtection:
    """Tests that extract_slx() blocks malicious ZIP paths using Path.relative_to()."""

    def _make_zip(self, tmp_path, entries: list[tuple[str, str]]) -> str:
        """Helper: create a ZIP at tmp_path/test.zip with given (name, content) entries."""
        import zipfile
        zip_path = str(tmp_path / "test.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            for name, content in entries:
                zf.writestr(name, content)
        return zip_path

    def test_normal_slx_extracts_ok(self, tmp_path):
        """A ZIP with safe paths should extract without error."""
        from utils.slx_extractor import extract_slx
        zip_path = self._make_zip(tmp_path, [
            ("simulink/blockdiagram.xml", "<root/>"),
            ("simulink/systems/system_root.xml", "<System/>"),
            ("metadata/coreProperties.xml", "<props/>"),
        ])
        # Rename to .slx
        slx_path = str(tmp_path / "model.slx")
        import shutil
        shutil.move(zip_path, slx_path)
        result = extract_slx(slx_path)
        from pathlib import Path
        assert Path(result).is_dir()
        assert (Path(result) / "simulink" / "blockdiagram.xml").exists()

    def test_zip_slip_absolute_path_rejected(self, tmp_path):
        """A ZIP entry with an absolute path should be rejected."""
        import zipfile, shutil
        from utils.slx_extractor import extract_slx, _extract_cache
        zip_path = str(tmp_path / "malicious.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            # On Windows, absolute paths like /etc/passwd won't traverse dirs,
            # but paths like ../../evil.xml will. We test what Path.relative_to catches.
            zf.writestr("../../evil.txt", "pwned")
            # Also add a valid XML so the file isn't rejected for missing XML first
            zf.writestr("simulink/blockdiagram.xml", "<root/>")
        slx_path = str(tmp_path / "malicious.slx")
        shutil.move(zip_path, slx_path)
        # Clear cache to ensure fresh extraction
        _extract_cache.pop(slx_path, None)
        with pytest.raises(ValueError, match="Zip Slip detected"):
            extract_slx(slx_path)

    def test_zip_slip_traversal_rejected(self, tmp_path):
        """A ZIP entry explicitly traversing outside the extract dir is rejected."""
        import zipfile, shutil
        from utils.slx_extractor import extract_slx, _extract_cache
        zip_path = str(tmp_path / "traversal.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../outside.xml", "<evil/>")
            zf.writestr("simulink/blockdiagram.xml", "<root/>")
        slx_path = str(tmp_path / "traversal.slx")
        shutil.move(zip_path, slx_path)
        _extract_cache.pop(slx_path, None)
        with pytest.raises(ValueError, match="Zip Slip detected"):
            extract_slx(slx_path)

    def test_no_xml_raises_value_error(self, tmp_path):
        """A valid ZIP missing system_root.xml should raise ValueError."""
        import zipfile, shutil
        from utils.slx_extractor import extract_slx, _extract_cache
        zip_path = str(tmp_path / "no_xml.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", "no xml here")
        slx_path = str(tmp_path / "no_xml.slx")
        shutil.move(zip_path, slx_path)
        _extract_cache.pop(slx_path, None)
        with pytest.raises(ValueError, match="system_root.xml"):
            extract_slx(slx_path)

    def test_missing_file_raises_file_not_found(self, tmp_path):
        """A nonexistent .slx path should raise FileNotFoundError."""
        from utils.slx_extractor import extract_slx
        with pytest.raises(FileNotFoundError):
            extract_slx(str(tmp_path / "nonexistent.slx"))

    def test_bad_zip_raises_value_error(self, tmp_path):
        """A file that is not a valid ZIP should raise ValueError."""
        from utils.slx_extractor import extract_slx, _extract_cache
        slx_path = tmp_path / "bad.slx"
        slx_path.write_bytes(b"this is not a zip")
        _extract_cache.pop(str(slx_path), None)
        with pytest.raises(ValueError, match="không hợp lệ"):
            extract_slx(str(slx_path))

    def test_nested_safe_paths_allowed(self, tmp_path):
        """Deep but safe nested paths inside the extract dir should pass."""
        import shutil
        from utils.slx_extractor import extract_slx, _extract_cache
        from pathlib import Path
        zip_path = self._make_zip(tmp_path, [
            ("simulink/systems/system_root.xml", "<System/>"),
            ("a/b/c/d/blockdiagram.xml", "<root/>"),
            ("a/b/c/d/config.xml", "<cfg/>"),
        ])
        slx_path = str(tmp_path / "nested.slx")
        shutil.move(zip_path, slx_path)
        _extract_cache.pop(slx_path, None)
        result = extract_slx(slx_path)
        assert Path(result).is_dir()


# ══════════════════════════════════════════════════════
# Fix 13: mark_final_status() — immutable, no mutation
# ══════════════════════════════════════════════════════


class TestMarkFinalStatus:
    """Tests that mark_final_status() returns new ValidationResult without mutating original."""

    def _make_validation(self, status: ValidationStatus) -> ValidationResult:
        return ValidationResult(
            rule_id="R001",
            status=status,
            code_file_path="test.py",
            stderr="some error",
            test_cases_passed=0,
            test_cases_total=1,
        )

    def test_returns_new_object(self):
        """mark_final_status must return a NEW object, not the same instance."""
        from pipeline.state_machine import RetryStateMachine
        sm = RetryStateMachine()
        original = self._make_validation(ValidationStatus.CODE_ERROR)
        result = sm.mark_final_status(original)
        assert result is not original

    def test_original_not_mutated(self):
        """The original ValidationResult status must remain unchanged."""
        from pipeline.state_machine import RetryStateMachine
        sm = RetryStateMachine()
        original = self._make_validation(ValidationStatus.CODE_ERROR)
        sm.mark_final_status(original)
        assert original.status == ValidationStatus.CODE_ERROR

    def test_code_error_maps_to_failed_code_error(self):
        from pipeline.state_machine import RetryStateMachine
        sm = RetryStateMachine()
        original = self._make_validation(ValidationStatus.CODE_ERROR)
        result = sm.mark_final_status(original)
        assert result.status == ValidationStatus.FAILED_CODE_ERROR

    def test_wrong_result_maps_to_failed_wrong_result(self):
        from pipeline.state_machine import RetryStateMachine
        sm = RetryStateMachine()
        original = self._make_validation(ValidationStatus.WRONG_RESULT)
        result = sm.mark_final_status(original)
        assert result.status == ValidationStatus.FAILED_WRONG_RESULT

    def test_partial_pass_maps_to_failed_partial_pass(self):
        from pipeline.state_machine import RetryStateMachine
        sm = RetryStateMachine()
        original = self._make_validation(ValidationStatus.PARTIAL_PASS)
        result = sm.mark_final_status(original)
        assert result.status == ValidationStatus.FAILED_PARTIAL_PASS

    def test_unmapped_status_returned_unchanged(self):
        """Statuses not in the map (e.g. SCHEMA_ERROR) should pass through unchanged."""
        from pipeline.state_machine import RetryStateMachine
        sm = RetryStateMachine()
        original = self._make_validation(ValidationStatus.SCHEMA_ERROR)
        result = sm.mark_final_status(original)
        assert result.status == ValidationStatus.SCHEMA_ERROR

    def test_already_failed_status_unchanged(self):
        """FAILED_CODE_ERROR input should stay FAILED_CODE_ERROR (not double-map)."""
        from pipeline.state_machine import RetryStateMachine
        sm = RetryStateMachine()
        original = self._make_validation(ValidationStatus.FAILED_CODE_ERROR)
        result = sm.mark_final_status(original)
        assert result.status == ValidationStatus.FAILED_CODE_ERROR

    def test_other_fields_preserved(self):
        """Non-status fields (rule_id, stderr, etc.) should be preserved in the new object."""
        from pipeline.state_machine import RetryStateMachine
        sm = RetryStateMachine()
        original = self._make_validation(ValidationStatus.WRONG_RESULT)
        result = sm.mark_final_status(original)
        assert result.rule_id == original.rule_id
        assert result.stderr == original.stderr
        assert result.code_file_path == original.code_file_path
        assert result.test_cases_passed == original.test_cases_passed
        assert result.test_cases_total == original.test_cases_total


# ══════════════════════════════════════════════════════
# Fix 14: stdout HEAD truncation, stderr TAIL truncation
# ══════════════════════════════════════════════════════


class TestTruncation:
    """Tests that _execute() keeps HEAD of stdout and TAIL of stderr on truncation."""

    def _make_validator_with_limits(self, stdout_limit: int, stderr_limit: int):
        """Create a Validator and monkey-patch settings for truncation limits."""
        from agents.agent3_validator import Validator
        from config import settings
        v = Validator(timeout=10)
        # Temporarily override settings values for the test
        object.__setattr__(settings, "STDOUT_TRUNCATION", stdout_limit)
        object.__setattr__(settings, "STDERR_TRUNCATION", stderr_limit)
        return v

    def _restore_settings(self):
        from config import settings
        object.__setattr__(settings, "STDOUT_TRUNCATION", 5000)
        object.__setattr__(settings, "STDERR_TRUNCATION", 3000)

    def test_stdout_full_in_execute(self, tmp_path):
        """_execute() must return FULL stdout — truncation happens only in validate() for display.

        Regression: previous version truncated stdout in _execute(), which broke json.loads()
        on large model outputs (cutting JSON mid-way → parse error → false WRONG_RESULT).
        """
        import textwrap
        from agents.agent3_validator import Validator
        from config import settings

        # Write a script that prints exactly 200 'A' chars then 200 'B' chars (400 total)
        code = textwrap.dedent("""\
            import sys, json
            def main():
                print("A" * 200 + "B" * 200, end="")
            main()
        """)
        code_file = tmp_path / "emit_long.py"
        code_file.write_text(code, encoding="utf-8")

        # Set limit to 100 chars (much shorter than 400 total)
        original_limit = settings.STDOUT_TRUNCATION
        object.__setattr__(settings, "STDOUT_TRUNCATION", 100)
        try:
            v = Validator(timeout=10)
            result = v._execute(str(code_file), str(tmp_path))
            stdout = result["stdout"]
            # _execute() must return FULL stdout (400 chars), not truncated to 100
            assert len(stdout) == 400
            assert stdout.startswith("A")
            assert stdout.endswith("B")
        finally:
            object.__setattr__(settings, "STDOUT_TRUNCATION", original_limit)

    def test_stderr_truncated_from_tail(self, tmp_path):
        """stderr longer than STDERR_TRUNCATION should keep the last N chars."""
        import textwrap
        from agents.agent3_validator import Validator
        from config import settings

        # Write a script that writes 200 'X' chars then 200 'Y' chars to stderr, then exits 1
        code = textwrap.dedent("""\
            import sys
            sys.stderr.write("X" * 200)
            sys.stderr.write("Y" * 200)
            sys.stderr.flush()
            sys.exit(1)
        """)
        code_file = tmp_path / "emit_stderr.py"
        code_file.write_text(code, encoding="utf-8")

        original_limit = settings.STDERR_TRUNCATION
        object.__setattr__(settings, "STDERR_TRUNCATION", 100)
        try:
            v = Validator(timeout=10)
            result = v._execute(str(code_file), str(tmp_path))
            stderr = result["stderr"]
            # Should be exactly 100 chars (TAIL)
            assert len(stderr) == 100
            # TAIL: should end with Y's
            assert stderr.endswith("Y")
            assert "X" not in stderr
        finally:
            object.__setattr__(settings, "STDERR_TRUNCATION", original_limit)

    def test_stdout_within_limit_not_truncated(self, tmp_path):
        """stdout shorter than limit should be returned unchanged."""
        import textwrap
        from agents.agent3_validator import Validator
        from config import settings

        code = textwrap.dedent("""\
            import sys
            sys.stdout.write("hello")
        """)
        code_file = tmp_path / "short_stdout.py"
        code_file.write_text(code, encoding="utf-8")

        original_limit = settings.STDOUT_TRUNCATION
        object.__setattr__(settings, "STDOUT_TRUNCATION", 100)
        try:
            v = Validator(timeout=10)
            result = v._execute(str(code_file), str(tmp_path))
            assert result["stdout"] == "hello"
        finally:
            object.__setattr__(settings, "STDOUT_TRUNCATION", original_limit)

    def test_stderr_within_limit_not_truncated(self, tmp_path):
        """stderr shorter than limit should be returned unchanged."""
        import textwrap
        from agents.agent3_validator import Validator
        from config import settings

        code = textwrap.dedent("""\
            import sys
            sys.stderr.write("err")
            sys.exit(1)
        """)
        code_file = tmp_path / "short_stderr.py"
        code_file.write_text(code, encoding="utf-8")

        original_limit = settings.STDERR_TRUNCATION
        object.__setattr__(settings, "STDERR_TRUNCATION", 100)
        try:
            v = Validator(timeout=10)
            result = v._execute(str(code_file), str(tmp_path))
            assert result["stderr"] == "err"
        finally:
            object.__setattr__(settings, "STDERR_TRUNCATION", original_limit)

    def test_stdout_at_exact_limit_not_truncated(self, tmp_path):
        """stdout of exactly STDOUT_TRUNCATION chars should not be truncated."""
        import textwrap
        from agents.agent3_validator import Validator
        from config import settings

        code = textwrap.dedent("""\
            import sys
            sys.stdout.write("Z" * 50)
        """)
        code_file = tmp_path / "exact_stdout.py"
        code_file.write_text(code, encoding="utf-8")

        original_limit = settings.STDOUT_TRUNCATION
        object.__setattr__(settings, "STDOUT_TRUNCATION", 50)
        try:
            v = Validator(timeout=10)
            result = v._execute(str(code_file), str(tmp_path))
            assert result["stdout"] == "Z" * 50
        finally:
            object.__setattr__(settings, "STDOUT_TRUNCATION", original_limit)


# ══════════════════════════════════════════════════════
# Fix 15: ConfigDiscovery.location_type Literal type
# ══════════════════════════════════════════════════════


class TestConfigDiscoveryLiteral:
    """Tests that ConfigDiscovery.location_type enforces the 5-value Literal."""

    _VALID_LOCATION_TYPES = ["direct_P", "InstanceData", "MaskValueString", "attribute", ""]

    def _make_discovery(self, location_type: str) -> "ConfigDiscovery":
        from schemas.diff_schemas import ConfigDiscovery
        return ConfigDiscovery(
            block_type="Gain",
            config_name="SaturateOnIntegerOverflow",
            location_type=location_type,
            xpath_pattern=".//Block[@BlockType='Gain']/P[@Name='SaturateOnIntegerOverflow']",
        )

    def test_direct_p_accepted(self):
        cd = self._make_discovery("direct_P")
        assert cd.location_type == "direct_P"

    def test_instance_data_accepted(self):
        cd = self._make_discovery("InstanceData")
        assert cd.location_type == "InstanceData"

    def test_mask_value_string_accepted(self):
        cd = self._make_discovery("MaskValueString")
        assert cd.location_type == "MaskValueString"

    def test_attribute_accepted(self):
        cd = self._make_discovery("attribute")
        assert cd.location_type == "attribute"

    def test_empty_string_accepted(self):
        """Empty string is valid (default — not yet discovered)."""
        cd = self._make_discovery("")
        assert cd.location_type == ""

    def test_all_valid_values_accepted(self):
        """All 5 Literal values must be accepted without error."""
        from pydantic import ValidationError
        for loc_type in self._VALID_LOCATION_TYPES:
            try:
                cd = self._make_discovery(loc_type)
                assert cd.location_type == loc_type
            except Exception as exc:
                pytest.fail(f"Valid location_type {loc_type!r} was rejected: {exc}")

    def test_invalid_value_rejected(self):
        """Arbitrary strings not in the Literal must be rejected."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._make_discovery("INVALID_TYPE")

    def test_wrong_case_rejected(self):
        """Literal is case-sensitive: 'direct_p' (lowercase p) must be rejected."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._make_discovery("direct_p")

    def test_partial_value_rejected(self):
        """Partial strings must be rejected."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._make_discovery("direct")

    def test_default_is_empty_string(self):
        """When location_type is omitted it defaults to empty string."""
        from schemas.diff_schemas import ConfigDiscovery
        cd = ConfigDiscovery(
            block_type="Gain",
            config_name="SaturateOnIntegerOverflow",
            xpath_pattern=".//Block",
        )
        assert cd.location_type == ""


# ══════════════════════════════════════════════════════
# Fix 16: gemini_safe_schema() strips examples recursively
# ══════════════════════════════════════════════════════


class TestGeminiSafeSchema:
    """Tests that gemini_safe_schema() removes 'examples' keys at all nesting levels."""

    def test_top_level_examples_stripped(self):
        """Examples at the top-level model_config are removed."""
        from pydantic import BaseModel, Field
        from utils.schema_utils import gemini_safe_schema

        class SimpleModel(BaseModel):
            value: int = Field(examples=[1, 2, 3])

        safe = gemini_safe_schema(SimpleModel)
        schema = safe.model_json_schema()
        # 'examples' should not appear anywhere in the schema
        import json
        schema_str = json.dumps(schema)
        assert '"examples"' not in schema_str

    def test_nested_examples_stripped(self):
        """Examples nested inside property definitions are removed."""
        from pydantic import BaseModel, Field
        from utils.schema_utils import gemini_safe_schema

        class Inner(BaseModel):
            name: str = Field(examples=["Alice", "Bob"])
            count: int = Field(examples=[10, 20])

        class Outer(BaseModel):
            inner: Inner
            label: str = Field(examples=["x", "y"])

        safe = gemini_safe_schema(Outer)
        schema = safe.model_json_schema()
        import json
        schema_str = json.dumps(schema)
        assert '"examples"' not in schema_str

    def test_other_fields_preserved(self):
        """Non-examples fields like 'description' and 'type' must survive stripping."""
        from pydantic import BaseModel, Field
        from utils.schema_utils import gemini_safe_schema

        class MyModel(BaseModel):
            value: int = Field(description="A count", examples=[42])

        safe = gemini_safe_schema(MyModel)
        schema = safe.model_json_schema()
        props = schema.get("properties", {})
        value_schema = props.get("value", {})
        assert value_schema.get("description") == "A count"
        assert "type" in value_schema
        assert "examples" not in value_schema

    def test_original_class_not_modified(self):
        """The original model class schema must still contain examples."""
        from pydantic import BaseModel, Field
        from utils.schema_utils import gemini_safe_schema
        import json

        class OriginalModel(BaseModel):
            value: int = Field(examples=[99])

        safe = gemini_safe_schema(OriginalModel)
        # Call safe schema (strips examples)
        safe.model_json_schema()
        # Original class schema must still have examples
        original_schema = OriginalModel.model_json_schema()
        schema_str = json.dumps(original_schema)
        assert '"examples"' in schema_str

    def test_class_name_preserved(self):
        """The proxy class should retain the original class __name__ and __module__."""
        from pydantic import BaseModel, Field
        from utils.schema_utils import gemini_safe_schema

        class MySpecialModel(BaseModel):
            x: int = Field(examples=[1])

        safe = gemini_safe_schema(MySpecialModel)
        assert safe.__name__ == "MySpecialModel"
        assert safe.__module__ == MySpecialModel.__module__

    def test_list_of_examples_in_schema_stripped(self):
        """examples that appear as a list value (not dict) are also removed."""
        from utils.schema_utils import _strip_examples
        schema = {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "examples": ["a", "b"],
                    "description": "A field",
                }
            },
            "examples": [{"field": "x"}],
        }
        result = _strip_examples(schema)
        import json
        result_str = json.dumps(result)
        assert '"examples"' not in result_str
        # description and type must survive
        assert result["properties"]["field"]["description"] == "A field"
        assert result["properties"]["field"]["type"] == "string"

    def test_deeply_nested_examples_stripped(self):
        """examples embedded three or more levels deep are removed."""
        from utils.schema_utils import _strip_examples
        schema = {
            "level1": {
                "level2": {
                    "level3": {
                        "examples": ["deep"],
                        "description": "deep field",
                    }
                }
            }
        }
        result = _strip_examples(schema)
        import json
        assert '"examples"' not in json.dumps(result)
        assert result["level1"]["level2"]["level3"]["description"] == "deep field"

    def test_real_validation_schema_examples_stripped(self):
        """ValidationResult (which has many examples) should have them all stripped."""
        from schemas.validation_schemas import ValidationResult
        from utils.schema_utils import gemini_safe_schema
        import json

        safe = gemini_safe_schema(ValidationResult)
        schema = safe.model_json_schema()
        schema_str = json.dumps(schema)
        assert '"examples"' not in schema_str
        # But required fields like 'properties' must still be present
        assert "properties" in schema


# ══════════════════════════════════════════════════════
# Fix 17: slx_extractor thread-safety (_lock, cache ops)
# ══════════════════════════════════════════════════════


class TestSlxExtractorThreadSafety:
    """Verify _lock exists and is a threading.Lock, and that basic cache functionality works."""

    def test_lock_exists(self):
        """_lock module-level attribute must exist in slx_extractor."""
        import utils.slx_extractor as mod
        assert hasattr(mod, "_lock"), "_lock attribute missing from slx_extractor"

    def test_lock_is_threading_lock(self):
        """_lock must be a threading.Lock() instance (RLock is NOT acceptable)."""
        import threading
        import utils.slx_extractor as mod
        # threading.Lock() returns a _thread.lock / _thread.RLock, check via acquire/release
        lock = mod._lock
        # The canonical way: isinstance check against threading.Lock type
        assert isinstance(lock, type(threading.Lock()))

    def test_temp_dirs_is_set(self):
        """_temp_dirs must be a set (thread-safe container used with _lock)."""
        import utils.slx_extractor as mod
        assert isinstance(mod._temp_dirs, set)

    def test_extract_cache_is_dict(self):
        """_extract_cache must be a dict."""
        import utils.slx_extractor as mod
        assert isinstance(mod._extract_cache, dict)

    def test_cache_hit_returns_same_path(self, tmp_path):
        """Calling extract_slx twice with same path returns identical result (cache hit)."""
        import shutil, zipfile
        from utils.slx_extractor import extract_slx, _extract_cache

        zip_path = str(tmp_path / "model_threadtest.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("simulink/blockdiagram.xml", "<root/>")
            zf.writestr("simulink/systems/system_root.xml", "<System/>")
        slx_path = str(tmp_path / "model_threadtest.slx")
        shutil.move(zip_path, slx_path)

        # Clear cache entry in case a previous test left it
        _extract_cache.pop(slx_path, None)

        result1 = extract_slx(slx_path)
        result2 = extract_slx(slx_path)
        assert result1 == result2

    def test_concurrent_extractions_safe(self, tmp_path):
        """Multiple threads extracting the same file must all get the same directory."""
        import shutil, zipfile, threading
        from utils.slx_extractor import extract_slx, _extract_cache
        from pathlib import Path

        zip_path = str(tmp_path / "concurrent_model.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("simulink/blockdiagram.xml", "<root/>")
            zf.writestr("simulink/systems/system_root.xml", "<System/>")
        slx_path = str(tmp_path / "concurrent_model.slx")
        shutil.move(zip_path, slx_path)
        _extract_cache.pop(slx_path, None)

        results = []
        errors = []

        def worker():
            try:
                r = extract_slx(slx_path)
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Threads raised errors: {errors}"
        # All threads should get back valid directories
        assert len(results) == 5
        for r in results:
            assert Path(r).is_dir()


# ══════════════════════════════════════════════════════
# Fix 18: ExplorationCache MAX_ENTRIES limit
# ══════════════════════════════════════════════════════


class TestExplorationCacheMaxEntries:
    """Verify that ExplorationCache stops accepting new entries after MAX_ENTRIES."""

    def test_max_entries_constant_exists(self):
        """ExplorationCache.MAX_ENTRIES must be defined and equal to 50."""
        from pipeline.exploration_cache import ExplorationCache
        assert hasattr(ExplorationCache, "MAX_ENTRIES")
        assert ExplorationCache.MAX_ENTRIES == 50

    def test_store_blocks_stops_at_max(self):
        """store_blocks should not add more entries once MAX_ENTRIES is reached."""
        from pipeline.exploration_cache import ExplorationCache
        cache = ExplorationCache()

        # Store MAX_ENTRIES block entries
        for i in range(ExplorationCache.MAX_ENTRIES):
            cache.store_blocks(f"BlockType{i}", f"result_{i}")

        # Attempt to store one more
        cache.store_blocks("OverflowBlock", "overflow_result")

        # Only MAX_ENTRIES should be stored
        total = len(cache._blocks) + len(cache._configs)
        assert total == ExplorationCache.MAX_ENTRIES
        assert "OverflowBlock" not in cache._blocks

    def test_store_51_entries_only_50_kept(self):
        """Storing 51 blocks should result in exactly 50 stored (MAX_ENTRIES)."""
        from pipeline.exploration_cache import ExplorationCache
        cache = ExplorationCache()

        for i in range(51):
            cache.store_blocks(f"Type{i}", f"result_{i}")

        assert len(cache._blocks) == 50

    def test_store_config_stops_at_max(self):
        """store_config respects MAX_ENTRIES combined with store_blocks count."""
        from pipeline.exploration_cache import ExplorationCache
        cache = ExplorationCache()

        # Fill up all slots with block entries
        for i in range(ExplorationCache.MAX_ENTRIES):
            cache.store_blocks(f"BlockType{i}", f"result_{i}")

        # Attempt to store a config entry — should be ignored
        cache.store_config("Gain", "SaturateOnIntegerOverflow", "some_result")

        assert len(cache._configs) == 0

    def test_mixed_blocks_and_configs_respect_max(self):
        """Mixed store_blocks + store_config calls together should not exceed MAX_ENTRIES."""
        from pipeline.exploration_cache import ExplorationCache
        cache = ExplorationCache()

        half = ExplorationCache.MAX_ENTRIES // 2
        for i in range(half):
            cache.store_blocks(f"BlockType{i}", f"result_{i}")
        for i in range(half):
            cache.store_config(f"Block{i}", f"Config{i}", f"result_{i}")

        # Attempt to store beyond the limit
        cache.store_blocks("ExtraBlock", "extra")
        cache.store_config("ExtraBlock", "ExtraConfig", "extra")

        total = len(cache._blocks) + len(cache._configs)
        assert total == ExplorationCache.MAX_ENTRIES

    def test_hierarchy_not_counted_in_max(self):
        """store_hierarchy should always work regardless of MAX_ENTRIES."""
        from pipeline.exploration_cache import ExplorationCache
        cache = ExplorationCache()

        # Fill all entries
        for i in range(ExplorationCache.MAX_ENTRIES):
            cache.store_blocks(f"BlockType{i}", f"result_{i}")

        # Hierarchy should still be storable
        cache.store_hierarchy("hierarchy_data")
        assert cache._model_hierarchy == "hierarchy_data"


# ══════════════════════════════════════════════════════
# Fix 19: Agent 1 blocks_json_path validation
# ══════════════════════════════════════════════════════


class TestAgent1BlocksPathValidation:
    """Verify create_agent1() validates blocks_json_path exists."""

    def test_nonexistent_path_raises_file_not_found(self):
        """create_agent1 with nonexistent path must raise FileNotFoundError."""
        from agents.agent1_data_reader import create_agent1
        with pytest.raises(FileNotFoundError):
            create_agent1("nonexistent_blocks.json")

    def test_nonexistent_path_message_includes_path(self):
        """FileNotFoundError message should include the invalid path."""
        from agents.agent1_data_reader import create_agent1
        try:
            create_agent1("no_such_file.json")
            pytest.fail("Expected FileNotFoundError was not raised")
        except FileNotFoundError as exc:
            assert "no_such_file.json" in str(exc)

    def test_valid_path_creates_agent(self):
        """create_agent1 with an existing blocks.json must not raise any error."""
        from agents.agent1_data_reader import create_agent1
        # Use real demo data that ships with the repo
        agent = create_agent1("data/blocks.json")
        assert agent is not None

    def test_valid_path_agent_has_correct_tool_call_limit(self):
        """Agent created with valid path should have tool_call_limit=5."""
        from agents.agent1_data_reader import create_agent1
        agent = create_agent1("data/blocks.json")
        assert agent.tool_call_limit == 5

    def test_deeply_nested_nonexistent_path_raises(self):
        """A path that clearly does not exist should raise FileNotFoundError."""
        from agents.agent1_data_reader import create_agent1
        with pytest.raises(FileNotFoundError):
            create_agent1("no/such/dir/blocks.json")

    def test_another_nonexistent_path_raises(self, tmp_path):
        """A path inside an existing dir that does not exist should raise FileNotFoundError."""
        from agents.agent1_data_reader import create_agent1
        missing = str(tmp_path / "missing_blocks.json")
        with pytest.raises(FileNotFoundError):
            create_agent1(missing)


# ══════════════════════════════════════════════════════
# Fix 20: _find_test_cases logs warning for unknown rule_id
# ══════════════════════════════════════════════════════


class TestFindTestCasesWarning:
    """Verify _find_test_cases returns [] and logs a warning for unknown rule_id."""

    def test_unknown_rule_returns_empty_list(self):
        """_find_test_cases should return [] when rule_id is not in expected_list."""
        from pipeline.runner import _find_test_cases
        result = _find_test_cases([], "R999")
        assert result == []

    def test_unknown_rule_returns_empty_list_nonempty_data(self):
        """_find_test_cases returns [] when expected_list contains other rules."""
        from pipeline.runner import _find_test_cases
        expected_list = [
            {"rule_id": "R001", "test_cases": [
                {"model_path": "model.slx", "expected_total_blocks": 5,
                 "expected_pass": 4, "expected_fail": 1}
            ]},
        ]
        result = _find_test_cases(expected_list, "R999")
        assert result == []

    def test_unknown_rule_logs_warning(self, caplog):
        """_find_test_cases should emit a WARNING log for unknown rule_id."""
        import logging
        from pipeline.runner import _find_test_cases

        with caplog.at_level(logging.WARNING, logger="pipeline.runner"):
            _find_test_cases([], "RXYZ")

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) >= 1
        assert "RXYZ" in warning_records[0].message

    def test_known_rule_returns_test_cases(self):
        """_find_test_cases returns TestCase list when rule_id is found."""
        from pipeline.runner import _find_test_cases
        expected_list = [
            {"rule_id": "R001", "test_cases": [
                {"model_path": "data/model.slx", "expected_total_blocks": 10,
                 "expected_pass": 9, "expected_fail": 1}
            ]},
        ]
        result = _find_test_cases(expected_list, "R001")
        assert len(result) == 1
        assert result[0].model_path == "data/model.slx"

    def test_known_rule_does_not_log_warning(self, caplog):
        """No WARNING should be emitted when rule_id is found."""
        import logging
        from pipeline.runner import _find_test_cases

        expected_list = [
            {"rule_id": "R001", "test_cases": [
                {"model_path": "model.slx", "expected_total_blocks": 5,
                 "expected_pass": 5, "expected_fail": 0}
            ]},
        ]
        with caplog.at_level(logging.WARNING, logger="pipeline.runner"):
            _find_test_cases(expected_list, "R001")

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 0

    def test_empty_test_cases_list_returns_empty(self):
        """Rule found but with empty test_cases should return []."""
        from pipeline.runner import _find_test_cases
        expected_list = [
            {"rule_id": "R001", "test_cases": []},
        ]
        result = _find_test_cases(expected_list, "R001")
        assert result == []


# ══════════════════════════════════════════════════════
# Fix 21: Pure Python Agent 1 (pipeline/data_reader.py)
# ══════════════════════════════════════════════════════


class TestPurePythonAgent1:
    def test_exact_match_gain(self):
        from pipeline.data_reader import search_block_mapping
        result = search_block_mapping("data/blocks.json", "gain", "SaturateOnIntegerOverflow")
        assert result.name_xml == "Gain"
        assert result.name_ui == "Gain"
        assert result.search_confidence > 80

    def test_fuzzy_match_inport(self):
        from pipeline.data_reader import search_block_mapping
        result = search_block_mapping("data/blocks.json", "inport", "SampleTime")
        assert result.name_xml == "Inport"

    def test_case_insensitive(self):
        from pipeline.data_reader import search_block_mapping
        result = search_block_mapping("data/blocks.json", "GAIN", "SaturateOnIntegerOverflow")
        assert result.name_xml == "Gain"

    def test_no_match_returns_empty(self):
        from pipeline.data_reader import search_block_mapping
        result = search_block_mapping("data/blocks.json", "zzz_nonexistent_zzz", "X")
        assert result.name_xml == ""
        assert result.search_confidence == 0

    def test_returns_block_mapping_data_type(self):
        from pipeline.data_reader import search_block_mapping
        result = search_block_mapping("data/blocks.json", "gain", "X")
        assert isinstance(result, BlockMappingData)

    def test_native_xml_representation(self):
        from pipeline.data_reader import _infer_xml_representation
        assert _infer_xml_representation("Gain") == "native"
        assert _infer_xml_representation("Abs") == "native"

    def test_masked_xml_representation(self):
        from pipeline.data_reader import _infer_xml_representation
        assert _infer_xml_representation("TL_Inport") == "masked"
        assert _infer_xml_representation("TL_Gain") == "masked"

    def test_reference_xml_representation(self):
        from pipeline.data_reader import _infer_xml_representation
        assert _infer_xml_representation("Compare To Constant") == "reference"

    def test_unknown_xml_representation(self):
        from pipeline.data_reader import _infer_xml_representation
        assert _infer_xml_representation("") == "unknown"

    def test_empty_keyword_returns_empty(self):
        from pipeline.data_reader import search_block_mapping
        result = search_block_mapping("data/blocks.json", "", "X")
        assert result.name_xml == ""

    def test_nonexistent_blocks_file(self):
        from pipeline.data_reader import search_block_mapping, clear_cache
        clear_cache()
        result = search_block_mapping("nonexistent.json", "gain", "X")
        assert result.name_xml == ""
        clear_cache()

    def test_get_block_raw_entry_found(self):
        from pipeline.data_reader import get_block_raw_entry
        import json
        raw = get_block_raw_entry("data/blocks.json", "Gain")
        assert raw != ""
        data = json.loads(raw)
        assert data["name_xml"] == "Gain"

    def test_get_block_raw_entry_not_found(self):
        from pipeline.data_reader import get_block_raw_entry
        raw = get_block_raw_entry("data/blocks.json", "NonExistent")
        assert raw == ""

    def test_clear_cache(self):
        from pipeline.data_reader import clear_cache, _blocks_cache, search_block_mapping
        # Load something into cache
        search_block_mapping("data/blocks.json", "gain", "X")
        assert len(_blocks_cache) > 0
        clear_cache()
        assert len(_blocks_cache) == 0


# ══════════════════════════════════════════════════════
# Fix 22: Pure Python Agent 1.5 (pipeline/diff_analyzer.py)
# ══════════════════════════════════════════════════════


class TestPurePythonAgent1_5:
    def _make_diff(self, config_changes):
        from schemas.diff_schemas import ModelDiff
        return ModelDiff(
            model_before="before/", model_after="after/",
            config_changes=config_changes,
        )

    def _make_change(self, config_name="SaturateOnIntegerOverflow",
                     block_type="Gain", mask_type="", location_type="direct_P",
                     old_value="off", new_value="on"):
        from schemas.diff_schemas import ConfigChange
        return ConfigChange(
            block_sid="5", block_name="Gain1", block_type=block_type,
            mask_type=mask_type, system_file="simulink/systems/system_root.xml",
            config_name=config_name, old_value=old_value, new_value=new_value,
            location_type=location_type, xpath=f".//Block[@SID='5']/P[@Name='{config_name}']",
            change_type="modified",
        )

    def test_filter_by_config_name(self):
        from pipeline.diff_analyzer import analyze_diff_for_config
        diff = self._make_diff([
            self._make_change(config_name="SaturateOnIntegerOverflow"),
            self._make_change(config_name="OutDataTypeStr"),
        ])
        result = analyze_diff_for_config(diff, "Gain", "SaturateOnIntegerOverflow")
        assert result is not None
        assert result.config_name == "SaturateOnIntegerOverflow"

    def test_filter_by_block_type(self):
        from pipeline.diff_analyzer import analyze_diff_for_config
        diff = self._make_diff([
            self._make_change(config_name="Sat", block_type="Gain"),
            self._make_change(config_name="Sat", block_type="Abs"),
        ])
        result = analyze_diff_for_config(diff, "Abs", "Sat")
        assert result is not None
        assert result.block_type == "Abs"

    def test_no_match_returns_none(self):
        from pipeline.diff_analyzer import analyze_diff_for_config
        diff = self._make_diff([self._make_change(config_name="Other")])
        result = analyze_diff_for_config(diff, "Gain", "SaturateOnIntegerOverflow")
        assert result is None

    def test_empty_diff_returns_none(self):
        from pipeline.diff_analyzer import analyze_diff_for_config
        diff = self._make_diff([])
        result = analyze_diff_for_config(diff, "Gain", "X")
        assert result is None

    def test_none_diff_returns_none(self):
        from pipeline.diff_analyzer import analyze_diff_for_config
        result = analyze_diff_for_config(None, "Gain", "X")
        assert result is None

    def test_priority_instance_data_over_direct_p(self):
        from pipeline.diff_analyzer import analyze_diff_for_config
        diff = self._make_diff([
            self._make_change(location_type="direct_P"),
            self._make_change(location_type="InstanceData"),
        ])
        result = analyze_diff_for_config(diff, "Gain", "SaturateOnIntegerOverflow")
        assert result.location_type == "InstanceData"

    def test_xpath_generalized(self):
        from pipeline.diff_analyzer import _generalize_xpath
        result = _generalize_xpath(
            ".//Block[@SID='5']/P[@Name='Gain']", "Gain", "",
        )
        assert "@BlockType='Gain'" in result
        assert "@SID" not in result

    def test_xpath_with_mask_type(self):
        from pipeline.diff_analyzer import _generalize_xpath
        result = _generalize_xpath(
            ".//Block[@SID='5']/P[@Name='Sat']", "SubSystem", "TL_Gain",
        )
        assert "@MaskType='TL_Gain'" in result

    def test_builds_valid_config_discovery(self):
        from pipeline.diff_analyzer import analyze_diff_for_config
        from schemas.diff_schemas import ConfigDiscovery
        diff = self._make_diff([self._make_change()])
        result = analyze_diff_for_config(diff, "Gain", "SaturateOnIntegerOverflow")
        assert isinstance(result, ConfigDiscovery)
        assert result.block_type == "Gain"
        assert result.xpath_pattern != ""

    def test_infer_value_format_on_off(self):
        from pipeline.diff_analyzer import _infer_value_format
        assert _infer_value_format("off", "on") == "on/off"

    def test_infer_value_format_integer(self):
        from pipeline.diff_analyzer import _infer_value_format
        assert _infer_value_format("0", "5") == "integer"

    def test_infer_value_format_empty(self):
        from pipeline.diff_analyzer import _infer_value_format
        assert _infer_value_format(None, None) == "unknown"


# ══════════════════════════════════════════════════════
# Fix 23: Agent 4 with XmlToolkit
# ══════════════════════════════════════════════════════


class TestAgent4WithXmlToolkit:
    def test_create_agent4_without_xml_toolkit(self):
        """Backward compatible — no crash without xml_toolkit."""
        from agents.agent4_bug_fixer import create_agent4
        agent = create_agent4()
        assert agent is not None

    def test_create_agent4_with_xml_toolkit(self):
        """XmlToolkit should appear in agent tools."""
        from agents.agent4_bug_fixer import create_agent4
        from tools.xml_tools import XmlToolkit
        xml_toolkit = XmlToolkit(model_dir="data/model4_CcodeGeneration", shared_cache={})
        agent = create_agent4(xml_toolkit=xml_toolkit, output_dir="generated_checks")
        # Check that xml_toolkit is in the tools list
        tool_types = [type(t).__name__ for t in agent.tools]
        assert "XmlToolkit" in tool_types
        assert "CodeToolkit" in tool_types

    def test_agent4_tool_call_limit(self):
        """tool_call_limit should be 15 (increased from 10)."""
        from agents.agent4_bug_fixer import create_agent4
        agent = create_agent4()
        assert agent.tool_call_limit == 15


# ══════════════════════════════════════════════════════
# Fix 24: Agent 5 with ParsedRule context
# ══════════════════════════════════════════════════════


class TestAgent5WithParsedRule:
    def test_agent5_input_has_new_fields(self):
        from schemas.agent_inputs import Agent5Input
        inp = Agent5Input(
            rule_id="R001",
            condition="equal",
            expected_value="on",
            block_keyword="gain",
            code_file_path="test.py",
            failed_test_case="model.slx",
            config_map_analysis="test",
            attempt=1,
        )
        assert inp.condition == "equal"
        assert inp.expected_value == "on"
        assert inp.block_keyword == "gain"

    def test_agent5_prompt_contains_check_logic(self):
        from schemas.agent_inputs import Agent5Input
        inp = Agent5Input(
            rule_id="R001",
            condition="equal",
            expected_value="on",
            block_keyword="gain",
            code_file_path="test.py",
            failed_test_case="model.slx",
            config_map_analysis="test",
            attempt=1,
        )
        prompt = inp.to_prompt()
        assert "Rule Check Logic" in prompt
        assert "condition: equal" in prompt
        assert "expected_value: on" in prompt
        assert "block_keyword: gain" in prompt

    def test_agent5_from_state_machine_with_parsed_rule(self):
        from schemas.agent_inputs import Agent5Input
        from pipeline.state_machine import RetryStateMachine
        sm = RetryStateMachine()
        sm.increment("agent5")
        validation = ValidationResult(
            rule_id="R001",
            status=ValidationStatus.WRONG_RESULT,
            code_file_path="test.py",
        )
        block_data = BlockMappingData(
            name_ui="Gain", name_xml="Gain",
            config_map_analysis="test",
        )
        parsed = ParsedRule(
            block_keyword="gain",
            rule_alias="Gain",
            config_name="SaturateOnIntegerOverflow",
            condition=RuleCondition.EQUAL,
            expected_value="on",
        )
        inp = Agent5Input.from_state_machine(
            validation, block_data, sm, parsed_rule=parsed,
        )
        assert inp.condition == "equal"
        assert inp.expected_value == "on"
        assert inp.block_keyword == "gain"

    def test_agent5_from_state_machine_without_parsed_rule(self):
        """Backward compatible — empty fields without parsed_rule."""
        from schemas.agent_inputs import Agent5Input
        from pipeline.state_machine import RetryStateMachine
        sm = RetryStateMachine()
        sm.increment("agent5")
        validation = ValidationResult(
            rule_id="R001",
            status=ValidationStatus.WRONG_RESULT,
            code_file_path="test.py",
        )
        block_data = BlockMappingData(
            name_ui="Gain", name_xml="Gain",
            config_map_analysis="test",
        )
        inp = Agent5Input.from_state_machine(validation, block_data, sm)
        assert inp.condition == ""
        assert inp.expected_value == ""
        assert inp.block_keyword == ""

    def test_agent5_no_check_logic_when_empty(self):
        """to_prompt() should NOT show Rule Check Logic when fields are empty."""
        from schemas.agent_inputs import Agent5Input
        inp = Agent5Input(
            rule_id="R001",
            code_file_path="test.py",
            failed_test_case="model.slx",
            config_map_analysis="test",
            attempt=1,
        )
        prompt = inp.to_prompt()
        assert "Rule Check Logic" not in prompt


# ══════════════════════════════════════════════════════
# Fix 25: test_config.json parser
# ══════════════════════════════════════════════════════


class TestTestConfigParser:
    def test_parse_valid_config(self, tmp_path):
        import json
        from pipeline.test_config_parser import parse_test_config
        config = {
            "blocks_path": "data/blocks.json",
            "rules": [
                {
                    "rule_id": "R001",
                    "description": "All Gain blocks must have Sat=on",
                    "test_cases": [
                        {
                            "model_path": "data/model4_CcodeGeneration.slx",
                            "expected_total_blocks": 19,
                            "expected_pass": 18,
                            "expected_fail": 1,
                        }
                    ],
                }
            ],
        }
        config_file = tmp_path / "test_config.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")
        result = parse_test_config(str(config_file))
        assert result["model"] == "data/model4_CcodeGeneration.slx"
        assert result["blocks"] == "data/blocks.json"
        assert result["model_before"] is None
        # Verify generated files are valid JSON
        from pathlib import Path
        rules = json.loads(Path(result["rules"]).read_text(encoding="utf-8"))
        assert len(rules) == 1
        assert rules[0]["rule_id"] == "R001"
        expected = json.loads(Path(result["expected"]).read_text(encoding="utf-8"))
        assert len(expected) == 1
        assert expected[0]["test_cases"][0]["expected_total_blocks"] == 19

    def test_missing_rules_raises(self, tmp_path):
        import json
        from pipeline.test_config_parser import parse_test_config
        config = {"rules": []}
        config_file = tmp_path / "empty.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")
        with pytest.raises(ValueError, match="ít nhất 1 rule"):
            parse_test_config(str(config_file))

    def test_nonexistent_file_raises(self):
        from pipeline.test_config_parser import parse_test_config
        with pytest.raises(FileNotFoundError):
            parse_test_config("nonexistent_config.json")

    def test_config_with_model_before(self, tmp_path):
        import json
        from pipeline.test_config_parser import parse_test_config
        config = {
            "blocks_path": "data/blocks.json",
            "model_before": "data/model4_before",
            "rules": [
                {
                    "rule_id": "R005",
                    "description": "test",
                    "test_cases": [
                        {
                            "model_path": "data/model4_CcodeGeneration.slx",
                            "expected_total_blocks": 19,
                            "expected_pass": 18,
                            "expected_fail": 1,
                        }
                    ],
                }
            ],
        }
        config_file = tmp_path / "with_before.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")
        result = parse_test_config(str(config_file))
        assert result["model_before"] == "data/model4_before"

    def test_schema_validation(self, tmp_path):
        """Invalid schema should raise."""
        import json
        from pipeline.test_config_parser import parse_test_config
        from pydantic import ValidationError
        config = {"rules": "not_a_list"}
        config_file = tmp_path / "bad.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")
        with pytest.raises(ValidationError):
            parse_test_config(str(config_file))


# ══════════════════════════════════════════════════════
# Fix 26: Agent 2 richer data (blocks_raw_data + bddefaults)
# ══════════════════════════════════════════════════════


class TestAgent2RicherData:
    def test_blocks_raw_data_in_prompt(self):
        inp = Agent2Input(
            rule_id="R001",
            block_name_xml="Gain", block_name_ui="Gain",
            config_name="SaturateOnIntegerOverflow",
            condition="equal", expected_value="on",
            config_map_analysis="test",
            output_filename="check_rule_R001.py",
            blocks_raw_data='{"name_xml": "Gain", "description": "Gain block info"}',
        )
        prompt = inp.to_prompt()
        assert "BLOCKS_DICTIONARY_ENTRY" in prompt
        assert "name_xml: Gain" in prompt

    def test_bddefaults_in_prompt(self):
        inp = Agent2Input(
            rule_id="R001",
            block_name_xml="Gain", block_name_ui="Gain",
            config_name="SaturateOnIntegerOverflow",
            condition="equal", expected_value="on",
            config_map_analysis="test",
            output_filename="check_rule_R001.py",
            bddefaults_context='{"SaturateOnIntegerOverflow": "off", "Gain": "1"}',
        )
        prompt = inp.to_prompt()
        assert "BLOCK_DEFAULTS" in prompt
        assert "SaturateOnIntegerOverflow" in prompt

    def test_empty_raw_data_not_in_prompt(self):
        """Empty blocks_raw_data and bddefaults should NOT appear in prompt."""
        inp = Agent2Input(
            rule_id="R001",
            block_name_xml="Gain", block_name_ui="Gain",
            config_name="SaturateOnIntegerOverflow",
            condition="equal", expected_value="on",
            config_map_analysis="test",
            output_filename="check_rule_R001.py",
        )
        prompt = inp.to_prompt()
        assert "BLOCKS_DICTIONARY_ENTRY" not in prompt
        assert "BLOCK_DEFAULTS" not in prompt

    def test_from_pipeline_with_extra_data(self):
        rule = MagicMock()
        rule.rule_id = "R001"
        parsed = MagicMock()
        parsed.config_name = "SaturateOnIntegerOverflow"
        parsed.condition = RuleCondition.EQUAL
        parsed.expected_value = "on"
        parsed.additional_configs = []
        parsed.compound_logic = "SINGLE"
        parsed.target_block_types = []
        parsed.scope = "all_instances"
        parsed.scope_filter = ""
        block = BlockMappingData(
            name_ui="Gain", name_xml="Gain",
            config_map_analysis="test",
        )
        inp = Agent2Input.from_pipeline(
            rule, parsed, block,
            blocks_raw_data='{"test": true}',
            bddefaults_context='{"SaturateOnIntegerOverflow": "off"}',
        )
        assert inp.blocks_raw_data == '{"test": true}'
        assert inp.bddefaults_context == '{"SaturateOnIntegerOverflow": "off"}'


# ══════════════════════════════════════════════════════
# Fix 2: blocks.json expansion to 21 entries
# ══════════════════════════════════════════════════════


class TestBlocksJsonExpansion:
    """Fix 2: blocks.json now has 21 entries including TL_* blocks."""

    @pytest.fixture
    def blocks_data(self):
        import json
        import os
        path = os.path.join(os.path.dirname(__file__), "..", "data", "blocks.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_block_count_at_least_21(self, blocks_data):
        assert len(blocks_data) >= 21

    def test_tl_blocks_present(self, blocks_data):
        names_xml = {b["name_xml"] for b in blocks_data}
        for tl in ["TL_Inport", "TL_Outport", "TL_Gain", "TL_Sum", "TL_Abs", "TL_Delay", "TL_Lookup1D", "TL_Lookup2D"]:
            assert tl in names_xml, f"Missing TL block: {tl}"

    def test_common_simulink_blocks_present(self, blocks_data):
        names_xml = {b["name_xml"] for b in blocks_data}
        for block in ["Product", "UnitDelay", "Switch"]:
            assert block in names_xml, f"Missing block: {block}"

    def test_all_entries_have_required_fields(self, blocks_data):
        for entry in blocks_data:
            assert "name_ui" in entry
            assert "name_xml" in entry
            assert "description" in entry
            assert len(entry["description"]) > 10, f"Description too short for {entry['name_xml']}"

    def test_tl_descriptions_mention_masktype(self, blocks_data):
        tl_entries = [b for b in blocks_data if b["name_xml"].startswith("TL_")]
        for entry in tl_entries:
            assert "MaskType" in entry["description"] or "masked" in entry["description"].lower(), \
                f"TL block {entry['name_xml']} description should mention MaskType"


# ══════════════════════════════════════════════════════
# Fix 3: RuleCondition numeric comparisons
# ══════════════════════════════════════════════════════


class TestRuleConditionNumeric:
    """Fix 3: RuleCondition now supports numeric comparisons."""

    def test_new_conditions_exist(self):
        assert RuleCondition.GREATER_THAN.value == "greater_than"
        assert RuleCondition.LESS_THAN.value == "less_than"
        assert RuleCondition.GREATER_EQUAL.value == "greater_equal"
        assert RuleCondition.LESS_EQUAL.value == "less_equal"

    def test_total_condition_count(self):
        assert len(RuleCondition) == 10  # 5 original + 4 numeric + 1 regex_match

    def test_parsed_rule_accepts_numeric_condition(self):
        rule = ParsedRule(
            block_keyword="delay",
            rule_alias="Delay block",
            config_name="DelayLength",
            condition=RuleCondition.GREATER_THAN,
            expected_value="0",
        )
        assert rule.condition == RuleCondition.GREATER_THAN
        assert rule.expected_value == "0"

    def test_additional_config_accepts_numeric_condition(self):
        from schemas.rule_schemas import AdditionalConfig
        cfg = AdditionalConfig(
            config_name="Gain",
            condition=RuleCondition.GREATER_EQUAL,
            expected_value="1",
        )
        assert cfg.condition == RuleCondition.GREATER_EQUAL


# ══════════════════════════════════════════════════════
# Fix A: RuleCondition.REGEX_MATCH
# ══════════════════════════════════════════════════════


class TestRuleConditionRegex:
    """Fix A: REGEX_MATCH condition added to RuleCondition."""

    def test_regex_match_exists(self):
        from schemas.rule_schemas import RuleCondition
        assert RuleCondition.REGEX_MATCH.value == "regex_match"

    def test_regex_brings_count_to_10(self):
        from schemas.rule_schemas import RuleCondition
        assert len(RuleCondition) == 10

    def test_parsed_rule_accepts_regex_condition(self):
        from schemas.rule_schemas import ParsedRule, RuleCondition
        rule = ParsedRule(
            block_keyword="gain",
            rule_alias="Gain block",
            config_name="OutDataTypeStr",
            condition=RuleCondition.REGEX_MATCH,
            expected_value=r"fixdt\(1,\d+,",
        )
        assert rule.condition == RuleCondition.REGEX_MATCH
        assert "fixdt" in rule.expected_value


# ══════════════════════════════════════════════════════
# Fix B: ConfigSet reader
# ══════════════════════════════════════════════════════

import os as _os
MODEL_DIR = _os.path.join(_os.path.dirname(__file__), "..", "data", "model4_CcodeGeneration")


class TestConfigReader:
    """Fix B: config_reader reads simulink/configSet0.xml."""

    def test_import_ok(self):
        from utils.config_reader import read_config_setting, read_all_config_settings, list_config_components
        assert callable(read_config_setting)

    def test_read_system_target_file(self):
        from utils.config_reader import read_config_setting
        val = read_config_setting(MODEL_DIR, "Simulink.RTWCC", "SystemTargetFile")
        assert val == "ert.tlc"

    def test_read_target_lang(self):
        from utils.config_reader import read_config_setting
        val = read_config_setting(MODEL_DIR, "Simulink.RTWCC", "TargetLang")
        assert val == "C"

    def test_read_solver(self):
        from utils.config_reader import read_config_setting
        val = read_config_setting(MODEL_DIR, "Simulink.SolverCC", "Solver")
        assert val is not None
        assert len(val) > 0  # some solver name

    def test_read_all_settings_not_empty(self):
        from utils.config_reader import read_all_config_settings
        settings = read_all_config_settings(MODEL_DIR, "Simulink.SolverCC")
        assert len(settings) > 0
        assert "Solver" in settings

    def test_list_components(self):
        from utils.config_reader import list_config_components
        components = list_config_components(MODEL_DIR)
        assert "Simulink.SolverCC" in components
        assert "Simulink.RTWCC" in components

    def test_nonexistent_setting_returns_none(self):
        from utils.config_reader import read_config_setting
        val = read_config_setting(MODEL_DIR, "Simulink.SolverCC", "NonExistentSetting")
        assert val is None

    def test_nonexistent_model_dir_returns_none(self):
        from utils.config_reader import read_config_setting
        val = read_config_setting("/nonexistent/path", "Simulink.RTWCC", "SystemTargetFile")
        assert val is None

    def test_read_all_returns_empty_for_bad_class(self):
        from utils.config_reader import read_all_config_settings
        result = read_all_config_settings(MODEL_DIR, "Simulink.NonExistentCC")
        assert result == {}


# ══════════════════════════════════════════════════════
# Model-Level Rule Support
# ══════════════════════════════════════════════════════


class TestParsedRuleModelLevel:
    def test_default_rule_type_is_block_level(self):
        from schemas.rule_schemas import ParsedRule, RuleCondition
        rule = ParsedRule(block_keyword="gain", rule_alias="Gain",
                          config_name="SaturateOnIntegerOverflow",
                          condition=RuleCondition.EQUAL, expected_value="on")
        assert rule.rule_type == "block_level"
        assert rule.config_component_class is None

    def test_model_level_rule_accepted(self):
        from schemas.rule_schemas import ParsedRule, RuleCondition
        rule = ParsedRule(block_keyword="", rule_alias="CodeGen target",
                          config_name="SystemTargetFile",
                          condition=RuleCondition.EQUAL, expected_value="ert.tlc",
                          rule_type="model_level",
                          config_component_class="Simulink.RTWCC")
        assert rule.rule_type == "model_level"
        assert rule.config_component_class == "Simulink.RTWCC"

    def test_config_only_rule_accepted(self):
        from schemas.rule_schemas import ParsedRule, RuleCondition
        rule = ParsedRule(block_keyword="", rule_alias="all blocks",
                          config_name="SaturateOnIntegerOverflow",
                          condition=RuleCondition.EQUAL, expected_value="on",
                          rule_type="config_only")
        assert rule.rule_type == "config_only"
        assert rule.config_component_class is None

    def test_solver_model_level_rule(self):
        from schemas.rule_schemas import ParsedRule, RuleCondition
        rule = ParsedRule(block_keyword="", rule_alias="Fixed-step solver",
                          config_name="Solver",
                          condition=RuleCondition.EQUAL, expected_value="FixedStepDiscrete",
                          rule_type="model_level",
                          config_component_class="Simulink.SolverCC")
        assert rule.rule_type == "model_level"
        assert "Solver" in rule.config_component_class


class TestAgent2InputModelLevel:
    def _inp(self, config_component_class="Simulink.RTWCC"):
        from schemas.agent_inputs import Agent2Input
        return Agent2Input(
            rule_id="R010", block_name_xml="", block_name_ui="",
            config_name="SystemTargetFile", condition="equal", expected_value="ert.tlc",
            config_map_analysis="configSet rule", output_filename="check_rule_R010.py",
            rule_type="model_level", config_component_class=config_component_class)

    def test_model_level_prompt_has_header(self):
        assert "MODEL-LEVEL RULE" in self._inp().to_prompt()

    def test_model_level_shows_config_component_class(self):
        assert "Simulink.RTWCC" in self._inp().to_prompt()

    def test_model_level_shows_config_reader(self):
        assert "config_reader" in self._inp().to_prompt()

    def test_model_level_no_block_discovery_tools(self):
        prompt = self._inp().to_prompt()
        # Prompt mentions find_config_locations only in a prohibition ("KHÔNG dùng"),
        # never as a positive instruction. find_blocks must not appear at all.
        assert "find_blocks" not in prompt
        # The prohibition must be present
        assert "KHÔNG dùng" in prompt
        assert "find_config_locations" in prompt  # mentioned as forbidden, not as instruction

    def test_model_level_unknown_class_shows_helper(self):
        prompt = self._inp(config_component_class=None).to_prompt()
        assert "UNKNOWN" in prompt
        assert "list_config_components" in prompt

    def test_block_level_prompt_unaffected(self):
        from schemas.agent_inputs import Agent2Input
        inp = Agent2Input(rule_id="R001", block_name_xml="Gain", block_name_ui="Gain",
                          config_name="SaturateOnIntegerOverflow",
                          condition="equal", expected_value="on",
                          config_map_analysis="test", output_filename="check_rule_R001.py",
                          rule_type="block_level")
        prompt = inp.to_prompt()
        assert "TIER 1" in prompt
        assert "MODEL-LEVEL" not in prompt

    def test_from_pipeline_passes_rule_type(self):
        from unittest.mock import MagicMock
        from schemas.agent_inputs import Agent2Input
        from schemas.rule_schemas import RuleCondition
        rule = MagicMock(); rule.rule_id = "R010"
        parsed = MagicMock()
        parsed.block_keyword = ""; parsed.config_name = "SystemTargetFile"
        parsed.condition = RuleCondition.EQUAL; parsed.expected_value = "ert.tlc"
        parsed.compound_logic = "SINGLE"; parsed.additional_configs = []
        parsed.target_block_types = []; parsed.scope = "all_instances"
        parsed.scope_filter = ""; parsed.complexity_level = 1
        parsed.rule_type = "model_level"
        parsed.config_component_class = "Simulink.RTWCC"
        block = MagicMock()
        block.name_xml = ""; block.name_ui = ""; block.xml_representation = "unknown"
        block.config_map_analysis = "configSet"
        inp = Agent2Input.from_pipeline(rule, parsed, block)
        assert inp.rule_type == "model_level"


# ══════════════════════════════════════════════════════
# Fix: XPath injection safety — model_index, config_reader, hierarchy_utils
# ══════════════════════════════════════════════════════

class TestModelIndexSafeSIDLookup:
    """model_index._find_block_by_sid must use attribute comparison, not XPath f-string."""

    def _make_root(self, sids: list[str]):
        """Build minimal XML root with Block elements for given SIDs."""
        from lxml import etree
        root = etree.fromstring("<System>" + "".join(
            f'<Block SID="{sid}" Name="blk_{sid}" BlockType="Gain"/>' for sid in sids
        ) + "</System>")
        return root

    def test_finds_existing_block(self):
        from utils.model_index import _find_block_by_sid
        root = self._make_root(["10", "20", "30"])
        block = _find_block_by_sid(root, "20")
        assert block is not None
        assert block.get("SID") == "20"

    def test_returns_none_for_missing_sid(self):
        from utils.model_index import _find_block_by_sid
        root = self._make_root(["10", "20"])
        assert _find_block_by_sid(root, "99") is None

    def test_safe_with_special_chars_in_sid(self):
        """SID containing XPath special chars must not crash."""
        from utils.model_index import _find_block_by_sid
        root = self._make_root(["10"])
        # These would crash/inject if using xpath f-string
        for bad_sid in ["1' or '1'='1", "1'] or [@SID='10", "<script>"]:
            result = _find_block_by_sid(root, bad_sid)
            assert result is None  # not found, no crash

    def test_empty_root_returns_none(self):
        from utils.model_index import _find_block_by_sid
        from lxml import etree
        root = etree.fromstring("<System/>")
        assert _find_block_by_sid(root, "1") is None


class TestConfigReaderSafeClassLookup:
    """config_reader must not use f-string XPath for class_name/setting_name."""

    def _make_config_file(self, tmp_path, class_name: str, setting_name: str, value: str) -> str:
        import os
        content = f'''<?xml version="1.0"?>
<ConfigSet>
  <Object ClassName="{class_name}">
    <P Name="{setting_name}">{value}</P>
  </Object>
</ConfigSet>'''
        d = tmp_path / "simulink"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "configSet0.xml"
        f.write_text(content, encoding="utf-8")
        return str(tmp_path)

    def test_reads_existing_setting(self, tmp_path):
        from utils.config_reader import read_config_setting
        model_dir = self._make_config_file(tmp_path, "Simulink.RTWCC", "SystemTargetFile", "ert.tlc")
        val = read_config_setting(model_dir, "Simulink.RTWCC", "SystemTargetFile")
        assert val == "ert.tlc"

    def test_returns_none_for_wrong_class(self, tmp_path):
        from utils.config_reader import read_config_setting
        model_dir = self._make_config_file(tmp_path, "Simulink.RTWCC", "SystemTargetFile", "ert.tlc")
        assert read_config_setting(model_dir, "Simulink.SolverCC", "SystemTargetFile") is None

    def test_safe_with_special_chars_in_class_name(self, tmp_path):
        """XPath injection attempts in class_name must not match anything."""
        from utils.config_reader import read_config_setting
        model_dir = self._make_config_file(tmp_path, "Simulink.RTWCC", "SystemTargetFile", "ert.tlc")
        # Would crash/inject if using f-string findall
        bad_class = "Simulink.RTWCC'] | .//*[@ClassName='Simulink.RTWCC"
        result = read_config_setting(model_dir, bad_class, "SystemTargetFile")
        assert result is None

    def test_safe_with_special_chars_in_setting_name(self, tmp_path):
        from utils.config_reader import read_config_setting
        model_dir = self._make_config_file(tmp_path, "Simulink.RTWCC", "SystemTargetFile", "ert.tlc")
        bad_setting = "SystemTargetFile' or 'x'='x"
        result = read_config_setting(model_dir, "Simulink.RTWCC", bad_setting)
        assert result is None


class TestFindChildSystemFileNormalization:
    """_find_child_system_file must normalize Ref regardless of extension/path format."""

    def _make_root_with_subsystem(self, ref_value: str):
        from lxml import etree
        xml = f'''<System>
  <Block BlockType="SubSystem" SID="42" Name="MySub">
    <System Ref="{ref_value}"/>
  </Block>
</System>'''
        return etree.fromstring(xml)

    def _call(self, root, sid: str):
        """Call the internal helper via hierarchy_utils module."""
        import importlib
        import utils.hierarchy_utils as hu
        return hu._find_child_system_file(root, sid)

    def test_ref_stem_only(self):
        """Ref="system_6" → "simulink/systems/system_6.xml" (no double extension)."""
        root = self._make_root_with_subsystem("system_6")
        result = self._call(root, "42")
        assert result == "simulink/systems/system_6.xml"

    def test_ref_with_xml_extension(self):
        """Ref="system_6.xml" → "simulink/systems/system_6.xml" (not system_6.xml.xml)."""
        root = self._make_root_with_subsystem("system_6.xml")
        result = self._call(root, "42")
        assert result == "simulink/systems/system_6.xml"

    def test_ref_with_full_path(self):
        """Ref="simulink/systems/system_6.xml" → stem extracted correctly."""
        root = self._make_root_with_subsystem("simulink/systems/system_6.xml")
        result = self._call(root, "42")
        assert result == "simulink/systems/system_6.xml"

    def test_wrong_sid_returns_none(self):
        root = self._make_root_with_subsystem("system_6")
        result = self._call(root, "99")
        assert result is None
