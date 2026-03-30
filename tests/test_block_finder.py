"""
Tests cho utils/block_finder.py — universal block finder.
Covers: native, Reference, MaskType blocks + config reading.
"""

import pytest
from lxml import etree

from utils.block_finder import (
    find_blocks,
    find_all_blocks,
    get_block_identity,
    list_all_block_types,
    find_blocks_with_config,
    get_block_config,
)


# ── Fixtures ──────────────────────────────────────────


def _make_system(*blocks_xml: str) -> etree._Element:
    """Tạo <System> element từ list block XML strings."""
    xml = "<System>\n" + "\n".join(blocks_xml) + "\n</System>"
    return etree.fromstring(xml)


NATIVE_GAIN = """
<Block BlockType="Gain" Name="Gain1" SID="10">
  <P Name="Position">[100, 200, 130, 230]</P>
  <P Name="Gain">5</P>
  <P Name="SaturateOnIntegerOverflow">on</P>
</Block>
"""

NATIVE_ABS = """
<Block BlockType="Abs" Name="Abs1" SID="20">
  <P Name="SaturateOnIntegerOverflow">off</P>
</Block>
"""

REFERENCE_BLOCK = """
<Block BlockType="Reference" Name="Compare1" SID="30">
  <P Name="SourceBlock">simulink/Logic and Bit Operations/Compare To Constant</P>
  <P Name="SourceType">Compare To Constant</P>
  <InstanceData>
    <P Name="const">42</P>
    <P Name="relop">&gt;=</P>
    <P Name="OutDataTypeStr">boolean</P>
  </InstanceData>
</Block>
"""

MASKED_BLOCK = """
<Block BlockType="SubSystem" Name="TL_Gain1" SID="40">
  <P Name="MaskType">TL_Gain</P>
  <P Name="Ports">[1, 1]</P>
  <InstanceData>
    <P Name="Gain">10</P>
    <P Name="SaturateOnIntegerOverflow">on</P>
  </InstanceData>
</Block>
"""

NATIVE_SUM = """
<Block BlockType="Sum" Name="Sum1" SID="50">
  <P Name="Inputs">++</P>
  <P Name="SaturateOnIntegerOverflow">on</P>
</Block>
"""


# ══════════════════════════════════════════════════════
# Tests: find_blocks
# ══════════════════════════════════════════════════════


class TestFindBlocks:
    def test_find_native_by_block_type(self):
        root = _make_system(NATIVE_GAIN, NATIVE_ABS)
        blocks = find_blocks(root, "Gain")
        assert len(blocks) == 1
        assert blocks[0].get("Name") == "Gain1"

    def test_find_reference_by_source_type(self):
        root = _make_system(REFERENCE_BLOCK, NATIVE_GAIN)
        blocks = find_blocks(root, "Compare To Constant")
        assert len(blocks) == 1
        assert blocks[0].get("Name") == "Compare1"

    def test_find_masked_by_mask_type(self):
        root = _make_system(MASKED_BLOCK, NATIVE_GAIN)
        blocks = find_blocks(root, "TL_Gain")
        assert len(blocks) == 1
        assert blocks[0].get("Name") == "TL_Gain1"

    def test_no_duplicates_by_sid(self):
        root = _make_system(NATIVE_GAIN)
        blocks = find_blocks(root, "Gain")
        assert len(blocks) == 1

    def test_not_found_returns_empty(self):
        root = _make_system(NATIVE_GAIN)
        blocks = find_blocks(root, "Buffer")
        assert blocks == []

    def test_find_multiple_same_type(self):
        gain2 = NATIVE_GAIN.replace('Name="Gain1"', 'Name="Gain2"').replace('SID="10"', 'SID="11"')
        root = _make_system(NATIVE_GAIN, gain2)
        blocks = find_blocks(root, "Gain")
        assert len(blocks) == 2


# ══════════════════════════════════════════════════════
# Tests: get_block_identity
# ══════════════════════════════════════════════════════


class TestGetBlockIdentity:
    def test_native_identity(self):
        root = _make_system(NATIVE_GAIN)
        block = root.findall("Block")[0]
        assert get_block_identity(block) == "Gain"

    def test_reference_identity(self):
        root = _make_system(REFERENCE_BLOCK)
        block = root.findall("Block")[0]
        assert get_block_identity(block) == "Compare To Constant"

    def test_masked_identity(self):
        root = _make_system(MASKED_BLOCK)
        block = root.findall("Block")[0]
        assert get_block_identity(block) == "TL_Gain"

    def test_masked_takes_priority_over_block_type(self):
        """MaskType ưu tiên cao hơn BlockType."""
        root = _make_system(MASKED_BLOCK)
        block = root.findall("Block")[0]
        assert block.get("BlockType") == "SubSystem"
        assert get_block_identity(block) == "TL_Gain"


# ══════════════════════════════════════════════════════
# Tests: list_all_block_types
# ══════════════════════════════════════════════════════


class TestListAllBlockTypes:
    def test_counts_all_types(self):
        root = _make_system(NATIVE_GAIN, NATIVE_ABS, REFERENCE_BLOCK, MASKED_BLOCK)
        types = list_all_block_types(root)
        assert types["Gain"] == 1
        assert types["Abs"] == 1
        assert types["Compare To Constant"] == 1
        assert types["TL_Gain"] == 1
        assert len(types) == 4

    def test_empty_system(self):
        root = _make_system()
        types = list_all_block_types(root)
        assert types == {}


# ══════════════════════════════════════════════════════
# Tests: find_blocks_with_config
# ══════════════════════════════════════════════════════


class TestFindBlocksWithConfig:
    def test_find_direct_p_config(self):
        root = _make_system(NATIVE_GAIN, NATIVE_ABS, REFERENCE_BLOCK)
        blocks = find_blocks_with_config(root, "SaturateOnIntegerOverflow")
        names = {b.get("Name") for b in blocks}
        assert "Gain1" in names
        assert "Abs1" in names

    def test_find_instance_data_config(self):
        root = _make_system(REFERENCE_BLOCK)
        blocks = find_blocks_with_config(root, "const")
        assert len(blocks) == 1
        assert blocks[0].get("Name") == "Compare1"

    def test_not_found(self):
        root = _make_system(NATIVE_GAIN)
        blocks = find_blocks_with_config(root, "NonExistentConfig")
        assert blocks == []

    def test_finds_in_both_direct_and_instance(self):
        root = _make_system(NATIVE_GAIN, MASKED_BLOCK)
        blocks = find_blocks_with_config(root, "SaturateOnIntegerOverflow")
        names = {b.get("Name") for b in blocks}
        assert "Gain1" in names
        assert "TL_Gain1" in names


# ══════════════════════════════════════════════════════
# Tests: get_block_config
# ══════════════════════════════════════════════════════


class TestGetBlockConfig:
    def test_direct_p(self):
        root = _make_system(NATIVE_GAIN)
        block = root.findall("Block")[0]
        assert get_block_config(block, "SaturateOnIntegerOverflow") == "on"
        assert get_block_config(block, "Gain") == "5"

    def test_instance_data(self):
        root = _make_system(REFERENCE_BLOCK)
        block = root.findall("Block")[0]
        assert get_block_config(block, "const") == "42"
        assert get_block_config(block, "OutDataTypeStr") == "boolean"

    def test_fallback_to_default(self):
        root = _make_system(NATIVE_GAIN)
        block = root.findall("Block")[0]
        assert get_block_config(block, "NonExistent", "default_val") == "default_val"

    def test_none_when_not_found_no_default(self):
        root = _make_system(NATIVE_GAIN)
        block = root.findall("Block")[0]
        assert get_block_config(block, "NonExistent") is None

    def test_direct_p_overrides_instance_data(self):
        """Nếu config có ở cả direct <P> lẫn InstanceData, direct <P> ưu tiên."""
        root = _make_system(MASKED_BLOCK)
        block = root.findall("Block")[0]
        # MaskType nằm ở direct <P>
        assert get_block_config(block, "MaskType") == "TL_Gain"


# ══════════════════════════════════════════════════════
# Tests: find_all_blocks
# ══════════════════════════════════════════════════════


class TestFindAllBlocks:
    def test_returns_all(self):
        root = _make_system(NATIVE_GAIN, NATIVE_ABS, REFERENCE_BLOCK, MASKED_BLOCK)
        blocks = find_all_blocks(root)
        assert len(blocks) == 4

    def test_empty_system(self):
        root = _make_system()
        blocks = find_all_blocks(root)
        assert blocks == []


# ══════════════════════════════════════════════════════
# Tests: Integration with real model
# ══════════════════════════════════════════════════════


class TestRealModel:
    """Tests dùng model XML thật (data/model4_CcodeGeneration)."""

    @pytest.fixture
    def root(self):
        tree = etree.parse("data/model4_CcodeGeneration/simulink/systems/system_root.xml")
        return tree.getroot()

    def test_find_gain_in_real_model(self, root):
        blocks = find_blocks(root, "Gain")
        assert len(blocks) == 1

    def test_find_reference_blocks_in_real_model(self, root):
        blocks = find_blocks(root, "Compare To Constant")
        assert len(blocks) == 2

    def test_identity_of_reference_block(self, root):
        blocks = find_blocks(root, "Compare To Constant")
        for b in blocks:
            assert get_block_identity(b) == "Compare To Constant"
            assert b.get("BlockType") == "Reference"

    def test_reference_config_via_instance_data(self, root):
        blocks = find_blocks(root, "Compare To Constant")
        for b in blocks:
            val = get_block_config(b, "const")
            assert val is not None
            assert val.isdigit()

    def test_list_all_types_in_real_model(self, root):
        types = list_all_block_types(root)
        assert "Gain" in types
        assert "Abs" in types
        assert "Compare To Constant" in types
        assert "Reference" not in types  # Should show SourceType, not "Reference"

    def test_find_config_across_block_types(self, root):
        blocks = find_blocks_with_config(root, "SaturateOnIntegerOverflow")
        types = {get_block_identity(b) for b in blocks}
        assert "Abs" in types


# ══════════════════════════════════════════════════════
# Tests: get_block_config with Array child elements (Fix 1)
# ══════════════════════════════════════════════════════


class TestGetBlockConfigArray:
    """Fix 1: get_block_config handles <Array> child elements."""

    def _make_block_with_array_p(self, config_name: str, values: list):
        """Helper: build XML block with Array-type parameter."""
        block = etree.Element("Block", BlockType="Gain")
        p = etree.SubElement(block, "P", Name=config_name)
        array = etree.SubElement(p, "Array", Type="Matrix", size=str(len(values)))
        for v in values:
            d = etree.SubElement(array, "D")
            d.text = v
        return block

    def _make_block_with_instance_array_p(self, config_name: str, values: list):
        """Helper: build block with Array in InstanceData."""
        block = etree.Element("Block", BlockType="Reference")
        instance = etree.SubElement(block, "InstanceData")
        p = etree.SubElement(instance, "P", Name=config_name)
        array = etree.SubElement(p, "Array", Type="Matrix", size=str(len(values)))
        for v in values:
            d = etree.SubElement(array, "D")
            d.text = v
        return block

    def test_single_array_value(self):
        block = self._make_block_with_array_p("OutDataTypeStr", ["fixdt(1,16,12)"])
        result = get_block_config(block, "OutDataTypeStr")
        assert result == "fixdt(1,16,12)"

    def test_multi_array_values_pipe_joined(self):
        block = self._make_block_with_array_p("BreakpointsX", ["0", "1", "2", "3"])
        result = get_block_config(block, "BreakpointsX")
        assert result == "0|1|2|3"

    def test_array_in_instance_data(self):
        block = self._make_block_with_instance_array_p("OutDataTypeStr", ["fixdt(0,8,0)"])
        result = get_block_config(block, "OutDataTypeStr")
        assert result == "fixdt(0,8,0)"

    def test_plain_text_p_still_works(self):
        """Non-Array <P> must still return text value normally."""
        block = etree.Element("Block", BlockType="Gain")
        p = etree.SubElement(block, "P", Name="SaturateOnIntegerOverflow")
        p.text = "on"
        result = get_block_config(block, "SaturateOnIntegerOverflow")
        assert result == "on"

    def test_missing_config_returns_default(self):
        """Config not found → returns default_value."""
        block = etree.Element("Block", BlockType="Gain")
        result = get_block_config(block, "NonExistent", "off")
        assert result == "off"

    def test_empty_array_returns_none(self):
        """<Array> with no <D> elements → falls through to default."""
        block = etree.Element("Block", BlockType="Gain")
        p = etree.SubElement(block, "P", Name="OutDataTypeStr")
        etree.SubElement(p, "Array", Type="Matrix", size="0")
        result = get_block_config(block, "OutDataTypeStr", default_value="fallback")
        assert result == "fallback"
