"""
Unit tests cho utils/model_differ.py — XML diff algorithm.

Dùng demo data tại:
  - data/model4_CcodeGeneration/ (after)
  - data/model4_before/ (before — modified Abs SID=62, Gain SID=68, Reference SID=69)

Thay đổi giữa before vs after:
  - Abs SID=62: SaturateOnIntegerOverflow "on" → "off" (direct_P, modified)
  - Gain SID=68: SaturateOnIntegerOverflow removed (direct_P, "on" → absent=default)
  - Reference SID=69: InstanceData const "5" → "3" (InstanceData, modified)
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from utils.model_differ import ModelDiffer
from schemas.diff_schemas import ModelDiff


# ── Fixtures ──────────────────────────────────────────────

BEFORE_DIR = str(PROJECT_ROOT / "data" / "model4_before")
AFTER_DIR = str(PROJECT_ROOT / "data" / "model4_CcodeGeneration")


@pytest.fixture
def differ():
    return ModelDiffer(BEFORE_DIR, AFTER_DIR)


@pytest.fixture
def diff_result(differ):
    return differ.diff()


# ── Test: Basic diff structure ────────────────────────────

class TestDiffBasics:
    def test_diff_returns_model_diff(self, diff_result):
        assert isinstance(diff_result, ModelDiff)

    def test_diff_has_paths(self, diff_result):
        assert diff_result.model_before == BEFORE_DIR
        assert diff_result.model_after == AFTER_DIR

    def test_no_files_only_differences(self, diff_result):
        """Both models have same set of system_*.xml files."""
        assert diff_result.files_only_before == []
        assert diff_result.files_only_after == []

    def test_has_config_changes(self, diff_result):
        """There should be at least 2 config changes (Abs + Reference)."""
        assert len(diff_result.config_changes) >= 2

    def test_has_block_changes(self, diff_result):
        """At least 2 blocks were modified."""
        assert len(diff_result.block_changes) >= 2


# ── Test: SID-based block matching ────────────────────────

class TestSIDMatching:
    def test_common_blocks_matched(self, diff_result):
        """Modified blocks should be detected, not treated as added/removed."""
        change_types = {bc.change_type for bc in diff_result.block_changes}
        assert "modified" in change_types
        # No blocks were truly added or removed
        assert "added" not in change_types
        assert "removed" not in change_types

    def test_specific_sids_detected(self, diff_result):
        """Abs SID=62 and Reference SID=69 should be in block changes."""
        changed_sids = {bc.block_sid for bc in diff_result.block_changes}
        assert "62" in changed_sids  # Abs — SaturateOnIntegerOverflow changed
        assert "69" in changed_sids  # Reference — InstanceData const changed


# ── Test: 4-layer diff detection ──────────────────────────

class TestDirectPDiff:
    def test_abs_saturate_changed(self, diff_result):
        """Abs SID=62: SaturateOnIntegerOverflow "on" → "off"."""
        abs_changes = [
            c for c in diff_result.config_changes
            if c.block_sid == "62" and c.config_name == "SaturateOnIntegerOverflow"
        ]
        assert len(abs_changes) == 1
        change = abs_changes[0]
        assert change.location_type == "direct_P"
        assert change.old_value == "on"
        assert change.new_value == "off"
        assert change.change_type == "modified"
        assert change.block_type == "Abs"

    def test_gain_saturate_removed(self, diff_result):
        """Gain SID=68: SaturateOnIntegerOverflow "on" → removed (absent in after)."""
        gain_changes = [
            c for c in diff_result.config_changes
            if c.block_sid == "68" and c.config_name == "SaturateOnIntegerOverflow"
        ]
        assert len(gain_changes) == 1
        change = gain_changes[0]
        assert change.location_type == "direct_P"
        assert change.old_value == "on"
        assert change.new_value is None
        assert change.change_type == "removed"

    def test_visual_configs_ignored(self, diff_result):
        """Position, ZOrder, etc. should NOT appear in config changes."""
        visual_names = {"Position", "ZOrder", "Ports", "Location", "Open"}
        for c in diff_result.config_changes:
            assert c.config_name not in visual_names, f"Visual config {c.config_name} not filtered"


class TestInstanceDataDiff:
    def test_reference_const_changed(self, diff_result):
        """Reference SID=69: InstanceData const "5" → "3"."""
        ref_changes = [
            c for c in diff_result.config_changes
            if c.block_sid == "69" and c.config_name == "const"
        ]
        assert len(ref_changes) == 1
        change = ref_changes[0]
        assert change.location_type == "InstanceData"
        assert change.old_value == "5"
        assert change.new_value == "3"
        assert change.change_type == "modified"


class TestXPathGeneration:
    def test_direct_p_xpath(self, diff_result):
        """XPath for direct_P should contain Block[@SID] and P[@Name]."""
        abs_change = next(
            c for c in diff_result.config_changes
            if c.block_sid == "62" and c.config_name == "SaturateOnIntegerOverflow"
        )
        assert "Block[@SID='62']" in abs_change.xpath
        assert "P[@Name='SaturateOnIntegerOverflow']" in abs_change.xpath

    def test_instance_data_xpath(self, diff_result):
        """XPath for InstanceData should include InstanceData path."""
        ref_change = next(
            c for c in diff_result.config_changes
            if c.block_sid == "69" and c.config_name == "const"
        )
        assert "InstanceData" in ref_change.xpath
        assert "P[@Name='const']" in ref_change.xpath


# ── Test: IGNORE_CONFIGS ──────────────────────────────────

class TestIgnoreConfigs:
    def test_no_position_in_changes(self, diff_result):
        for c in diff_result.config_changes:
            assert c.config_name != "Position"

    def test_no_zorder_in_changes(self, diff_result):
        for c in diff_result.config_changes:
            assert c.config_name != "ZOrder"


# ── Test: MaskValueString parsing ─────────────────────────

class TestMaskValueString:
    def test_empty_mvs_returns_empty(self):
        """If both blocks have no MaskValueString, no changes."""
        from lxml import etree
        before = etree.fromstring('<Block BlockType="Gain" Name="G" SID="1"></Block>')
        after = etree.fromstring('<Block BlockType="Gain" Name="G" SID="1"></Block>')
        differ = ModelDiffer("", "")
        changes = differ._diff_mask_value_string(before, after, {"block_sid": "1", "block_name": "G", "block_type": "Gain", "mask_type": "", "system_file": "test.xml"})
        assert changes == []

    def test_mvs_detects_change(self):
        """MaskValueString change should be detected with param name from MaskNames."""
        from lxml import etree
        before_xml = '''<Block BlockType="SubSystem" Name="TL" SID="1">
            <P Name="MaskNames">ScalingMode|DataType|InitValue</P>
            <P Name="MaskValueString">1|fixdt(1,16,4)|0</P>
        </Block>'''
        after_xml = '''<Block BlockType="SubSystem" Name="TL" SID="1">
            <P Name="MaskNames">ScalingMode|DataType|InitValue</P>
            <P Name="MaskValueString">1|fixdt(1,32,8)|0</P>
        </Block>'''
        before = etree.fromstring(before_xml)
        after = etree.fromstring(after_xml)
        differ = ModelDiffer("", "")
        base_info = {"block_sid": "1", "block_name": "TL", "block_type": "SubSystem", "mask_type": "", "system_file": "test.xml"}
        changes = differ._diff_mask_value_string(before, after, base_info)
        assert len(changes) == 1
        assert changes[0].config_name == "MaskValueString.DataType"
        assert changes[0].old_value == "fixdt(1,16,4)"
        assert changes[0].new_value == "fixdt(1,32,8)"
        assert changes[0].location_type == "MaskValueString"

    def test_mvs_pipe_only(self):
        """MaskValueString = '||' edge case — empty params."""
        from lxml import etree
        before_xml = '<Block BlockType="SubSystem" Name="TL" SID="1"><P Name="MaskValueString">||</P></Block>'
        after_xml = '<Block BlockType="SubSystem" Name="TL" SID="1"><P Name="MaskValueString">|x|</P></Block>'
        before = etree.fromstring(before_xml)
        after = etree.fromstring(after_xml)
        differ = ModelDiffer("", "")
        base_info = {"block_sid": "1", "block_name": "TL", "block_type": "SubSystem", "mask_type": "", "system_file": "test.xml"}
        changes = differ._diff_mask_value_string(before, after, base_info)
        assert len(changes) == 1
        assert changes[0].new_value == "x"


# ── Test: Attribute diff ──────────────────────────────────

class TestAttributeDiff:
    def test_attribute_change_detected(self):
        """Block attribute changes (except SID) should be detected."""
        from lxml import etree
        before = etree.fromstring('<Block BlockType="Gain" Name="G1" SID="1"></Block>')
        after = etree.fromstring('<Block BlockType="Gain" Name="G2" SID="1"></Block>')
        differ = ModelDiffer("", "")
        base_info = {"block_sid": "1", "block_name": "G2", "block_type": "Gain", "mask_type": "", "system_file": "test.xml"}
        changes = differ._diff_attributes(before, after, base_info)
        name_changes = [c for c in changes if c.config_name == "@Name"]
        assert len(name_changes) == 1
        assert name_changes[0].old_value == "G1"
        assert name_changes[0].new_value == "G2"


# ── Test: Directory validation ────────────────────────────

class TestDirectoryValidation:
    def test_list_system_files(self):
        files = ModelDiffer._list_system_files(AFTER_DIR)
        assert len(files) == 3
        assert all("system_" in f for f in files)

    def test_list_system_files_nonexistent(self):
        """Non-existent dir returns empty list (no crash)."""
        files = ModelDiffer._list_system_files("/nonexistent/path")
        assert files == []

    def test_diff_identical_models(self):
        """Diffing a model against itself → no changes."""
        differ = ModelDiffer(AFTER_DIR, AFTER_DIR)
        result = differ.diff()
        assert len(result.config_changes) == 0
        assert len(result.block_changes) == 0


# ── Test: Default value enrichment ────────────────────────

class TestDefaultValues:
    def test_default_value_enriched(self, diff_result):
        """ConfigChange for Abs/SaturateOnIntegerOverflow should have default_value set."""
        abs_changes = [
            c for c in diff_result.config_changes
            if c.block_type == "Abs" and c.config_name == "SaturateOnIntegerOverflow"
        ]
        # bddefaults.xml might not exist in before model, but should work with after model
        # If bddefaults has Abs defaults, it should be populated
        for c in abs_changes:
            # Just verify the field exists and is a string
            assert isinstance(c.default_value, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
