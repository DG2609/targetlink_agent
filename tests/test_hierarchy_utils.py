"""
Tests for utils/hierarchy_utils.py — hierarchy-aware block finding.

Covers all 6 public functions with both synthetic XML fixtures (unit tests)
and the real model at data/model4_CcodeGeneration (integration tests).

Real model structure:
    system_root.xml  — Root level (16 blocks: 1 Gain, 2 Abs, 2 Buffer, ...)
    system_6.xml     — Lowpass Filter (25 blocks: 9 Gain, 8 Sum, 4 Delay, ...)
    system_32.xml    — Highpass Filter (25 blocks: 9 Gain, 8 Sum, 4 Delay, ...)
    Total Gain blocks: 1 + 9 + 9 = 19
"""

import os
import tempfile

import pytest
from lxml import etree

from utils.hierarchy_utils import (
    build_subsystem_map,
    get_block_full_path,
    get_connections,
    get_parent_subsystem_info,
    walk_all_blocks,
    walk_blocks,
)

# ──────────────────────────────────────────────────────────────────────
# Real model path
# ──────────────────────────────────────────────────────────────────────

REAL_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "model4_CcodeGeneration",
)


# ──────────────────────────────────────────────────────────────────────
# Synthetic fixture helpers
# ──────────────────────────────────────────────────────────────────────


def _make_synthetic_model(files: dict[str, str]) -> str:
    """Create a temporary model directory with the given system XML files.

    Args:
        files: Mapping of filename (e.g. "system_root.xml") to XML content.

    Returns:
        Path to the temporary model directory.
    """
    tmpdir = tempfile.mkdtemp(prefix="test_hierarchy_")
    systems_dir = os.path.join(tmpdir, "simulink", "systems")
    os.makedirs(systems_dir, exist_ok=True)

    for filename, content in files.items():
        filepath = os.path.join(systems_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    return tmpdir


# ── Minimal root-only model (no subsystems) ──

ROOT_ONLY_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<System>
  <Block BlockType="Inport" Name="In1" SID="1">
    <P Name="Position">[100, 100, 130, 130]</P>
  </Block>
  <Block BlockType="Gain" Name="Gain1" SID="2">
    <P Name="Gain">5</P>
    <P Name="SaturateOnIntegerOverflow">on</P>
  </Block>
  <Block BlockType="Outport" Name="Out1" SID="3">
    <P Name="Position">[300, 100, 330, 130]</P>
  </Block>
  <Line>
    <P Name="Src">1#out:1</P>
    <P Name="Dst">2#in:1</P>
  </Line>
  <Line>
    <P Name="Src">2#out:1</P>
    <P Name="Dst">3#in:1</P>
  </Line>
</System>
"""

# ── 2-level model: root with one SubSystem child ──

TWO_LEVEL_ROOT_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<System>
  <Block BlockType="Inport" Name="In1" SID="1">
    <P Name="Position">[100, 100, 130, 130]</P>
  </Block>
  <Block BlockType="Gain" Name="RootGain" SID="2">
    <P Name="Gain">10</P>
    <P Name="SaturateOnIntegerOverflow">on</P>
  </Block>
  <Block BlockType="SubSystem" Name="MySubsystem" SID="5">
    <P Name="Ports">[1, 1]</P>
    <P Name="Tag">FilterSubSystem</P>
    <P Name="ContentPreviewEnabled">on</P>
    <System Ref="system_5"/>
  </Block>
  <Block BlockType="Outport" Name="Out1" SID="3">
    <P Name="Position">[300, 100, 330, 130]</P>
  </Block>
  <Line>
    <P Name="Src">1#out:1</P>
    <P Name="Dst">2#in:1</P>
  </Line>
  <Line>
    <P Name="Src">2#out:1</P>
    <P Name="Dst">5#in:1</P>
  </Line>
  <Line>
    <P Name="Src">5#out:1</P>
    <P Name="Dst">3#in:1</P>
  </Line>
</System>
"""

TWO_LEVEL_CHILD_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<System>
  <Block BlockType="Inport" Name="SubIn" SID="6">
    <P Name="Position">[100, 100, 130, 130]</P>
  </Block>
  <Block BlockType="Gain" Name="ChildGain1" SID="7">
    <P Name="Gain">3</P>
    <P Name="SaturateOnIntegerOverflow">off</P>
  </Block>
  <Block BlockType="Gain" Name="ChildGain2" SID="8">
    <P Name="Gain">7</P>
    <P Name="SaturateOnIntegerOverflow">on</P>
  </Block>
  <Block BlockType="Sum" Name="ChildSum" SID="9">
    <P Name="Inputs">++</P>
    <P Name="SaturateOnIntegerOverflow">on</P>
  </Block>
  <Block BlockType="Outport" Name="SubOut" SID="10">
    <P Name="Position">[400, 100, 430, 130]</P>
  </Block>
  <Line>
    <P Name="Src">6#out:1</P>
    <Branch>
      <P Name="Dst">7#in:1</P>
    </Branch>
    <Branch>
      <P Name="Dst">8#in:1</P>
    </Branch>
  </Line>
  <Line>
    <P Name="Src">7#out:1</P>
    <P Name="Dst">9#in:1</P>
  </Line>
  <Line>
    <P Name="Src">8#out:1</P>
    <P Name="Dst">9#in:2</P>
  </Line>
  <Line>
    <P Name="Src">9#out:1</P>
    <P Name="Dst">10#in:1</P>
  </Line>
</System>
"""

# ── 3-level model: root → SubSysA → SubSysB ──

THREE_LEVEL_ROOT_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<System>
  <Block BlockType="Gain" Name="TopGain" SID="1">
    <P Name="Gain">1</P>
  </Block>
  <Block BlockType="SubSystem" Name="LevelA" SID="10">
    <P Name="Ports">[1, 1]</P>
    <System Ref="system_10"/>
  </Block>
</System>
"""

THREE_LEVEL_A_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<System>
  <Block BlockType="Gain" Name="MidGain" SID="11">
    <P Name="Gain">2</P>
  </Block>
  <Block BlockType="SubSystem" Name="LevelB" SID="20">
    <P Name="Ports">[1, 1]</P>
    <System Ref="system_20"/>
  </Block>
</System>
"""

THREE_LEVEL_B_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<System>
  <Block BlockType="Gain" Name="DeepGain" SID="21">
    <P Name="Gain">3</P>
  </Block>
</System>
"""

# ── Model with connections (for get_connections tests) ──

CONNECTIONS_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<System>
  <Block BlockType="Inport" Name="In1" SID="1"/>
  <Block BlockType="Gain" Name="G1" SID="2">
    <P Name="Gain">5</P>
  </Block>
  <Block BlockType="Abs" Name="A1" SID="3"/>
  <Block BlockType="Outport" Name="Out1" SID="4"/>
  <Block BlockType="Gain" Name="Isolated" SID="99"/>
  <Line>
    <P Name="Src">1#out:1</P>
    <P Name="Dst">2#in:1</P>
  </Line>
  <Line>
    <P Name="Src">2#out:1</P>
    <P Name="Dst">3#in:1</P>
  </Line>
  <Line>
    <P Name="Src">3#out:1</P>
    <P Name="Dst">4#in:1</P>
  </Line>
</System>
"""

# ── Model with fan-out (branch connections) ──

FANOUT_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<System>
  <Block BlockType="Inport" Name="In1" SID="1"/>
  <Block BlockType="Gain" Name="G1" SID="2"/>
  <Block BlockType="Abs" Name="A1" SID="3"/>
  <Block BlockType="Abs" Name="A2" SID="4"/>
  <Line>
    <P Name="Src">1#out:1</P>
    <P Name="Dst">2#in:1</P>
  </Line>
  <Line>
    <P Name="Src">2#out:1</P>
    <Branch>
      <P Name="Dst">3#in:1</P>
    </Branch>
    <Branch>
      <P Name="Dst">4#in:1</P>
    </Branch>
  </Line>
</System>
"""


# ══════════════════════════════════════════════════════════════════════
# 1. Tests: build_subsystem_map
# ══════════════════════════════════════════════════════════════════════


class TestBuildSubsystemMap:
    """Tests for build_subsystem_map()."""

    def test_root_only_model(self):
        """Root-only model produces a single entry at depth 0."""
        model_dir = _make_synthetic_model({"system_root.xml": ROOT_ONLY_XML})
        result = build_subsystem_map(model_dir)

        assert len(result) == 1
        root_key = "simulink/systems/system_root.xml"
        assert root_key in result

        meta = result[root_key]
        assert meta["name"] == "Root"
        assert meta["depth"] == 0
        assert meta["parent_path"] == ""
        assert meta["full_path"] == "Root"
        assert meta["sid"] == ""

    def test_two_level_model(self):
        """2-level model: root + 1 child subsystem."""
        model_dir = _make_synthetic_model({
            "system_root.xml": TWO_LEVEL_ROOT_XML,
            "system_5.xml": TWO_LEVEL_CHILD_XML,
        })
        result = build_subsystem_map(model_dir)

        assert len(result) == 2

        root_meta = result["simulink/systems/system_root.xml"]
        assert root_meta["depth"] == 0
        assert root_meta["full_path"] == "Root"

        child_meta = result["simulink/systems/system_5.xml"]
        assert child_meta["name"] == "MySubsystem"
        assert child_meta["depth"] == 1
        assert child_meta["parent_path"] == "Root"
        assert child_meta["full_path"] == "Root/MySubsystem"
        assert child_meta["sid"] == "5"

    def test_three_level_model(self):
        """3-level model: root -> LevelA -> LevelB."""
        model_dir = _make_synthetic_model({
            "system_root.xml": THREE_LEVEL_ROOT_XML,
            "system_10.xml": THREE_LEVEL_A_XML,
            "system_20.xml": THREE_LEVEL_B_XML,
        })
        result = build_subsystem_map(model_dir)

        assert len(result) == 3

        assert result["simulink/systems/system_root.xml"]["depth"] == 0
        assert result["simulink/systems/system_10.xml"]["depth"] == 1
        assert result["simulink/systems/system_10.xml"]["full_path"] == "Root/LevelA"
        assert result["simulink/systems/system_20.xml"]["depth"] == 2
        assert result["simulink/systems/system_20.xml"]["full_path"] == "Root/LevelA/LevelB"
        assert result["simulink/systems/system_20.xml"]["parent_path"] == "Root/LevelA"

    def test_missing_child_file_still_records_entry(self):
        """If a SubSystem references a missing file, it is still recorded in the map."""
        model_dir = _make_synthetic_model({
            "system_root.xml": TWO_LEVEL_ROOT_XML,
            # system_5.xml intentionally missing
        })
        result = build_subsystem_map(model_dir)

        # Root + the missing child (entry created even though file is absent)
        assert len(result) == 2
        child_meta = result["simulink/systems/system_5.xml"]
        assert child_meta["name"] == "MySubsystem"
        assert child_meta["depth"] == 1

    def test_real_model(self):
        """Real model has 3 system files: root + system_6 + system_32."""
        result = build_subsystem_map(REAL_MODEL_DIR)

        assert len(result) == 3

        root_meta = result["simulink/systems/system_root.xml"]
        assert root_meta["depth"] == 0
        assert root_meta["full_path"] == "Root"

        lp_meta = result["simulink/systems/system_6.xml"]
        assert lp_meta["name"] == "Lowpass Filter"
        assert lp_meta["depth"] == 1
        assert lp_meta["sid"] == "6"
        assert lp_meta["full_path"] == "Root/Lowpass Filter"

        hp_meta = result["simulink/systems/system_32.xml"]
        assert hp_meta["name"] == "Highpass Filter"
        assert hp_meta["depth"] == 1
        assert hp_meta["sid"] == "32"
        assert hp_meta["full_path"] == "Root/Highpass Filter"

    def test_nonexistent_model_dir(self):
        """A model_dir that does not exist produces only the root entry (file not found)."""
        result = build_subsystem_map("/nonexistent/path/model")
        assert len(result) == 1
        root_meta = result["simulink/systems/system_root.xml"]
        assert root_meta["name"] == "Root"
        assert root_meta["depth"] == 0


# ══════════════════════════════════════════════════════════════════════
# 2. Tests: walk_blocks
# ══════════════════════════════════════════════════════════════════════


class TestWalkBlocks:
    """Tests for walk_blocks()."""

    def test_root_only_finds_gain(self):
        """Root-only model: find Gain blocks at depth 0."""
        model_dir = _make_synthetic_model({"system_root.xml": ROOT_ONLY_XML})
        blocks = walk_blocks(model_dir, "Gain")

        assert len(blocks) == 1
        b = blocks[0]
        assert b["name"] == "Gain1"
        assert b["sid"] == "2"
        assert b["block_type"] == "Gain"
        assert b["block_path"] == "Root/Gain1"
        assert b["system_file"] == "simulink/systems/system_root.xml"
        assert b["depth"] == 0
        assert b["parent_subsystem"] == "Root"

    def test_two_level_finds_gains_at_both_levels(self):
        """2-level model: Gain blocks found at root and child."""
        model_dir = _make_synthetic_model({
            "system_root.xml": TWO_LEVEL_ROOT_XML,
            "system_5.xml": TWO_LEVEL_CHILD_XML,
        })
        blocks = walk_blocks(model_dir, "Gain")

        assert len(blocks) == 3  # 1 root + 2 child

        root_gains = [b for b in blocks if b["depth"] == 0]
        child_gains = [b for b in blocks if b["depth"] == 1]
        assert len(root_gains) == 1
        assert len(child_gains) == 2

        assert root_gains[0]["block_path"] == "Root/RootGain"
        child_paths = {b["block_path"] for b in child_gains}
        assert "Root/MySubsystem/ChildGain1" in child_paths
        assert "Root/MySubsystem/ChildGain2" in child_paths

    def test_three_level_finds_gains_at_all_depths(self):
        """3-level model: Gain blocks found at depths 0, 1, and 2."""
        model_dir = _make_synthetic_model({
            "system_root.xml": THREE_LEVEL_ROOT_XML,
            "system_10.xml": THREE_LEVEL_A_XML,
            "system_20.xml": THREE_LEVEL_B_XML,
        })
        blocks = walk_blocks(model_dir, "Gain")

        assert len(blocks) == 3
        paths = {b["block_path"] for b in blocks}
        assert "Root/TopGain" in paths
        assert "Root/LevelA/MidGain" in paths
        assert "Root/LevelA/LevelB/DeepGain" in paths

        depths = {b["name"]: b["depth"] for b in blocks}
        assert depths["TopGain"] == 0
        assert depths["MidGain"] == 1
        assert depths["DeepGain"] == 2

    def test_nonexistent_type_returns_empty(self):
        """Searching for a block type that does not exist returns empty list."""
        model_dir = _make_synthetic_model({"system_root.xml": ROOT_ONLY_XML})
        blocks = walk_blocks(model_dir, "Buffer")
        assert blocks == []

    def test_real_model_gain_count_19(self):
        """Real model: 19 Gain blocks across all subsystem levels (1 + 9 + 9)."""
        blocks = walk_blocks(REAL_MODEL_DIR, "Gain")
        assert len(blocks) == 19

    def test_real_model_gain_distribution(self):
        """Real model: 1 Gain in root, 9 in Lowpass Filter, 9 in Highpass Filter."""
        blocks = walk_blocks(REAL_MODEL_DIR, "Gain")

        root_gains = [b for b in blocks if b["parent_subsystem"] == "Root"]
        lp_gains = [b for b in blocks if b["parent_subsystem"] == "Lowpass Filter"]
        hp_gains = [b for b in blocks if b["parent_subsystem"] == "Highpass Filter"]

        assert len(root_gains) == 1
        assert len(lp_gains) == 9
        assert len(hp_gains) == 9

    def test_real_model_gain_paths_include_hierarchy(self):
        """Real model: Gain paths include the subsystem hierarchy prefix."""
        blocks = walk_blocks(REAL_MODEL_DIR, "Gain")
        paths = {b["block_path"] for b in blocks}

        assert "Root/Gain" in paths
        assert "Root/Lowpass Filter/s(1)" in paths
        assert "Root/Highpass Filter/s(1)" in paths

    def test_real_model_nonexistent_type_returns_empty(self):
        """Real model: searching for a type that does not exist returns empty."""
        blocks = walk_blocks(REAL_MODEL_DIR, "ZeroOrderHold")
        assert blocks == []

    def test_real_model_abs_blocks(self):
        """Real model: Abs blocks exist only at root level."""
        blocks = walk_blocks(REAL_MODEL_DIR, "Abs")
        assert len(blocks) == 2
        for b in blocks:
            assert b["depth"] == 0
            assert b["parent_subsystem"] == "Root"

    def test_real_model_sum_blocks(self):
        """Real model: Sum blocks exist at root and in child subsystems."""
        blocks = walk_blocks(REAL_MODEL_DIR, "Sum")
        # Root: 2 Sum, system_6: 8 Sum, system_32: 8 Sum = 18
        assert len(blocks) == 18

    def test_block_dict_keys(self):
        """Each returned block dict has all required keys."""
        model_dir = _make_synthetic_model({"system_root.xml": ROOT_ONLY_XML})
        blocks = walk_blocks(model_dir, "Gain")
        assert len(blocks) >= 1
        expected_keys = {"name", "sid", "block_type", "block_path", "system_file", "depth", "parent_subsystem"}
        assert set(blocks[0].keys()) == expected_keys


# ══════════════════════════════════════════════════════════════════════
# 3. Tests: walk_all_blocks
# ══════════════════════════════════════════════════════════════════════


class TestWalkAllBlocks:
    """Tests for walk_all_blocks()."""

    def test_root_only_all_blocks(self):
        """Root-only model: returns all 3 blocks (Inport, Gain, Outport)."""
        model_dir = _make_synthetic_model({"system_root.xml": ROOT_ONLY_XML})
        blocks = walk_all_blocks(model_dir)
        assert len(blocks) == 3
        types = {b["block_type"] for b in blocks}
        assert "Inport" in types
        assert "Gain" in types
        assert "Outport" in types

    def test_two_level_all_blocks(self):
        """2-level model: all blocks from root and child combined."""
        model_dir = _make_synthetic_model({
            "system_root.xml": TWO_LEVEL_ROOT_XML,
            "system_5.xml": TWO_LEVEL_CHILD_XML,
        })
        blocks = walk_all_blocks(model_dir)
        # Root: Inport, Gain, SubSystem, Outport = 4
        # Child: Inport, Gain x2, Sum, Outport = 5
        assert len(blocks) == 9

    def test_real_model_total_block_count(self):
        """Real model: total block count across all 3 system files.

        Root: 16 blocks (Inport, 2 Abs, 2 Buffer, 2 Compare To Constant,
              1 Delay, 1 Product, 1 Gain, 2 SubSystem, 1 Logic, 2 Sum, 1 Outport)
        system_6 (Lowpass Filter): 25 blocks (Inport, 9 Gain, 8 Sum,
                                    4 Delay, From, Goto, Outport)
        system_32 (Highpass Filter): 25 blocks (same structure as system_6)
        Total = 16 + 25 + 25 = 66
        """
        blocks = walk_all_blocks(REAL_MODEL_DIR)
        assert len(blocks) == 66

    def test_real_model_all_blocks_have_paths(self):
        """Real model: every block has a non-empty block_path."""
        blocks = walk_all_blocks(REAL_MODEL_DIR)
        for b in blocks:
            assert b["block_path"]
            assert "/" in b["block_path"]  # At minimum "Root/BlockName"

    def test_empty_model(self):
        """Model with an empty <System> returns no blocks."""
        empty_xml = '<?xml version="1.0" encoding="utf-8"?>\n<System></System>'
        model_dir = _make_synthetic_model({"system_root.xml": empty_xml})
        blocks = walk_all_blocks(model_dir)
        assert blocks == []

    def test_walk_all_blocks_dict_keys(self):
        """Each returned block dict has the same keys as walk_blocks."""
        model_dir = _make_synthetic_model({"system_root.xml": ROOT_ONLY_XML})
        blocks = walk_all_blocks(model_dir)
        expected_keys = {"name", "sid", "block_type", "block_path", "system_file", "depth", "parent_subsystem"}
        for b in blocks:
            assert set(b.keys()) == expected_keys


# ══════════════════════════════════════════════════════════════════════
# 4. Tests: get_block_full_path
# ══════════════════════════════════════════════════════════════════════


class TestGetBlockFullPath:
    """Tests for get_block_full_path()."""

    def test_root_level_block(self):
        """Block in root system file gets 'Root/BlockName' path."""
        subsystem_map = {
            "simulink/systems/system_root.xml": {
                "name": "Root",
                "depth": 0,
                "parent_path": "",
                "full_path": "Root",
                "sid": "",
            },
        }
        result = get_block_full_path(
            subsystem_map, "simulink/systems/system_root.xml", "Gain1"
        )
        assert result == "Root/Gain1"

    def test_child_level_block(self):
        """Block in child system file gets full hierarchy path."""
        subsystem_map = {
            "simulink/systems/system_root.xml": {
                "name": "Root",
                "depth": 0,
                "parent_path": "",
                "full_path": "Root",
                "sid": "",
            },
            "simulink/systems/system_6.xml": {
                "name": "Lowpass Filter",
                "depth": 1,
                "parent_path": "Root",
                "full_path": "Root/Lowpass Filter",
                "sid": "6",
            },
        }
        result = get_block_full_path(
            subsystem_map, "simulink/systems/system_6.xml", "s(1)"
        )
        assert result == "Root/Lowpass Filter/s(1)"

    def test_unknown_system_file(self):
        """Unknown system file returns '<unknown>/BlockName'."""
        subsystem_map = {
            "simulink/systems/system_root.xml": {
                "name": "Root",
                "depth": 0,
                "parent_path": "",
                "full_path": "Root",
                "sid": "",
            },
        }
        result = get_block_full_path(
            subsystem_map, "simulink/systems/system_999.xml", "MyBlock"
        )
        assert result == "<unknown>/MyBlock"

    def test_empty_map(self):
        """Empty subsystem map always returns '<unknown>/BlockName'."""
        result = get_block_full_path({}, "any_file.xml", "AnyBlock")
        assert result == "<unknown>/AnyBlock"

    def test_deep_nested_block(self):
        """Deeply nested block resolves full path through multiple levels."""
        subsystem_map = {
            "simulink/systems/system_20.xml": {
                "name": "LevelB",
                "depth": 2,
                "parent_path": "Root/LevelA",
                "full_path": "Root/LevelA/LevelB",
                "sid": "20",
            },
        }
        result = get_block_full_path(
            subsystem_map, "simulink/systems/system_20.xml", "DeepGain"
        )
        assert result == "Root/LevelA/LevelB/DeepGain"

    def test_with_real_model_map(self):
        """Using the real model's subsystem map to resolve a known block."""
        subsystem_map = build_subsystem_map(REAL_MODEL_DIR)
        result = get_block_full_path(
            subsystem_map, "simulink/systems/system_6.xml", "s(1)"
        )
        assert result == "Root/Lowpass Filter/s(1)"


# ══════════════════════════════════════════════════════════════════════
# 5. Tests: get_connections
# ══════════════════════════════════════════════════════════════════════


class TestGetConnections:
    """Tests for get_connections()."""

    def test_block_with_incoming_and_outgoing(self):
        """Block G1 (SID=2) has 1 incoming from In1, 1 outgoing to A1."""
        model_dir = _make_synthetic_model({"system_root.xml": CONNECTIONS_XML})
        conns = get_connections(model_dir, "simulink/systems/system_root.xml", "2")

        assert len(conns["incoming"]) == 1
        assert conns["incoming"][0]["sid"] == "1"
        assert conns["incoming"][0]["name"] == "In1"
        assert conns["incoming"][0]["type"] == "Inport"
        assert conns["incoming"][0]["port"] == "out:1"

        assert len(conns["outgoing"]) == 1
        assert conns["outgoing"][0]["sid"] == "3"
        assert conns["outgoing"][0]["name"] == "A1"
        assert conns["outgoing"][0]["type"] == "Abs"
        assert conns["outgoing"][0]["port"] == "in:1"

    def test_block_with_no_connections(self):
        """Isolated block (SID=99) has no connections."""
        model_dir = _make_synthetic_model({"system_root.xml": CONNECTIONS_XML})
        conns = get_connections(model_dir, "simulink/systems/system_root.xml", "99")

        assert conns["incoming"] == []
        assert conns["outgoing"] == []

    def test_source_block(self):
        """Inport (SID=1) is source only — no incoming, 1 outgoing."""
        model_dir = _make_synthetic_model({"system_root.xml": CONNECTIONS_XML})
        conns = get_connections(model_dir, "simulink/systems/system_root.xml", "1")

        assert conns["incoming"] == []
        assert len(conns["outgoing"]) == 1
        assert conns["outgoing"][0]["sid"] == "2"

    def test_sink_block(self):
        """Outport (SID=4) is sink only — 1 incoming, no outgoing."""
        model_dir = _make_synthetic_model({"system_root.xml": CONNECTIONS_XML})
        conns = get_connections(model_dir, "simulink/systems/system_root.xml", "4")

        assert len(conns["incoming"]) == 1
        assert conns["incoming"][0]["sid"] == "3"
        assert conns["outgoing"] == []

    def test_fan_out_connections(self):
        """Block with fan-out: G1 (SID=2) outputs to both A1 (SID=3) and A2 (SID=4) via branches."""
        model_dir = _make_synthetic_model({"system_root.xml": FANOUT_XML})
        conns = get_connections(model_dir, "simulink/systems/system_root.xml", "2")

        assert len(conns["incoming"]) == 1
        assert len(conns["outgoing"]) == 2
        outgoing_sids = {c["sid"] for c in conns["outgoing"]}
        assert outgoing_sids == {"3", "4"}

    def test_fan_out_destination_incoming(self):
        """Each fan-out destination sees the source as its incoming connection."""
        model_dir = _make_synthetic_model({"system_root.xml": FANOUT_XML})

        conns_a1 = get_connections(model_dir, "simulink/systems/system_root.xml", "3")
        assert len(conns_a1["incoming"]) == 1
        assert conns_a1["incoming"][0]["sid"] == "2"

        conns_a2 = get_connections(model_dir, "simulink/systems/system_root.xml", "4")
        assert len(conns_a2["incoming"]) == 1
        assert conns_a2["incoming"][0]["sid"] == "2"

    def test_nonexistent_file(self):
        """Non-existent system file returns empty connection lists."""
        model_dir = _make_synthetic_model({"system_root.xml": ROOT_ONLY_XML})
        conns = get_connections(
            model_dir, "simulink/systems/system_999.xml", "1"
        )
        assert conns == {"incoming": [], "outgoing": []}

    def test_nonexistent_sid(self):
        """SID that does not exist in the file returns empty lists."""
        model_dir = _make_synthetic_model({"system_root.xml": CONNECTIONS_XML})
        conns = get_connections(
            model_dir, "simulink/systems/system_root.xml", "777"
        )
        assert conns == {"incoming": [], "outgoing": []}

    def test_real_model_root_gain_connections(self):
        """Real model: Gain block (SID=68) in root has connections."""
        conns = get_connections(
            REAL_MODEL_DIR, "simulink/systems/system_root.xml", "68"
        )
        # Gain (SID=68) has 1 incoming from Logic Operator (SID=70)
        # and 1 outgoing to Outport (SID=71)
        assert len(conns["incoming"]) == 1
        assert conns["incoming"][0]["sid"] == "70"

        assert len(conns["outgoing"]) == 1
        assert conns["outgoing"][0]["sid"] == "71"

    def test_real_model_inport_connections(self):
        """Real model: Inport Power (SID=1) fans out to two SubSystems via branches."""
        conns = get_connections(
            REAL_MODEL_DIR, "simulink/systems/system_root.xml", "1"
        )
        assert conns["incoming"] == []
        # SID=1 fans out to SID=32 (Highpass Filter) and SID=6 (Lowpass Filter)
        assert len(conns["outgoing"]) == 2
        outgoing_sids = {c["sid"] for c in conns["outgoing"]}
        assert "32" in outgoing_sids
        assert "6" in outgoing_sids

    def test_connection_port_format(self):
        """Connection port strings follow the 'out:N' or 'in:N' format."""
        model_dir = _make_synthetic_model({"system_root.xml": CONNECTIONS_XML})
        conns = get_connections(model_dir, "simulink/systems/system_root.xml", "2")

        # Incoming port is "out:1" (from SID=1's output)
        assert conns["incoming"][0]["port"] == "out:1"
        # Outgoing port is "in:1" (to SID=3's input)
        assert conns["outgoing"][0]["port"] == "in:1"


# ══════════════════════════════════════════════════════════════════════
# 6. Tests: get_parent_subsystem_info
# ══════════════════════════════════════════════════════════════════════


class TestGetParentSubsystemInfo:
    """Tests for get_parent_subsystem_info()."""

    def test_root_file_returns_none(self):
        """Root system file has no parent, returns None."""
        model_dir = _make_synthetic_model({
            "system_root.xml": TWO_LEVEL_ROOT_XML,
            "system_5.xml": TWO_LEVEL_CHILD_XML,
        })
        result = get_parent_subsystem_info(
            model_dir, "simulink/systems/system_root.xml"
        )
        assert result is None

    def test_child_file_returns_parent_info(self):
        """Child system file returns info about its parent SubSystem block."""
        model_dir = _make_synthetic_model({
            "system_root.xml": TWO_LEVEL_ROOT_XML,
            "system_5.xml": TWO_LEVEL_CHILD_XML,
        })
        result = get_parent_subsystem_info(
            model_dir, "simulink/systems/system_5.xml"
        )

        assert result is not None
        assert result["name"] == "MySubsystem"
        assert result["sid"] == "5"
        assert result["depth"] == 0  # Parent is at root level (depth 0)
        assert isinstance(result["properties"], dict)

    def test_child_properties_populated(self):
        """Parent SubSystem block's <P> properties are extracted."""
        model_dir = _make_synthetic_model({
            "system_root.xml": TWO_LEVEL_ROOT_XML,
            "system_5.xml": TWO_LEVEL_CHILD_XML,
        })
        result = get_parent_subsystem_info(
            model_dir, "simulink/systems/system_5.xml"
        )

        assert result is not None
        props = result["properties"]
        assert "Ports" in props
        assert props["Ports"] == "[1, 1]"
        assert "Tag" in props
        assert props["Tag"] == "FilterSubSystem"
        assert "ContentPreviewEnabled" in props
        assert props["ContentPreviewEnabled"] == "on"

    def test_three_level_mid_child(self):
        """Mid-level child returns parent info pointing to root."""
        model_dir = _make_synthetic_model({
            "system_root.xml": THREE_LEVEL_ROOT_XML,
            "system_10.xml": THREE_LEVEL_A_XML,
            "system_20.xml": THREE_LEVEL_B_XML,
        })
        result = get_parent_subsystem_info(
            model_dir, "simulink/systems/system_10.xml"
        )

        assert result is not None
        assert result["name"] == "LevelA"
        assert result["sid"] == "10"
        assert result["depth"] == 0  # Parent is at root level

    def test_three_level_deepest_child(self):
        """Deepest child returns parent info pointing to mid-level."""
        model_dir = _make_synthetic_model({
            "system_root.xml": THREE_LEVEL_ROOT_XML,
            "system_10.xml": THREE_LEVEL_A_XML,
            "system_20.xml": THREE_LEVEL_B_XML,
        })
        result = get_parent_subsystem_info(
            model_dir, "simulink/systems/system_20.xml"
        )

        assert result is not None
        assert result["name"] == "LevelB"
        assert result["sid"] == "20"
        assert result["depth"] == 1  # Parent is at depth 1

    def test_unknown_file_returns_none(self):
        """Non-existent system file returns None."""
        model_dir = _make_synthetic_model({"system_root.xml": ROOT_ONLY_XML})
        result = get_parent_subsystem_info(
            model_dir, "simulink/systems/system_999.xml"
        )
        assert result is None

    def test_real_model_root_returns_none(self):
        """Real model: root has no parent."""
        result = get_parent_subsystem_info(
            REAL_MODEL_DIR, "simulink/systems/system_root.xml"
        )
        assert result is None

    def test_real_model_lowpass_filter_parent(self):
        """Real model: Lowpass Filter (system_6.xml) parent is the SubSystem block in root."""
        result = get_parent_subsystem_info(
            REAL_MODEL_DIR, "simulink/systems/system_6.xml"
        )

        assert result is not None
        assert result["name"] == "Lowpass Filter"
        assert result["sid"] == "6"
        assert result["depth"] == 0  # Parent block is at root level
        assert "Tag" in result["properties"]
        assert result["properties"]["Tag"] == "FilterWizardSubSystem"

    def test_real_model_highpass_filter_parent(self):
        """Real model: Highpass Filter (system_32.xml) parent is the SubSystem block in root."""
        result = get_parent_subsystem_info(
            REAL_MODEL_DIR, "simulink/systems/system_32.xml"
        )

        assert result is not None
        assert result["name"] == "Highpass Filter"
        assert result["sid"] == "32"
        assert result["depth"] == 0
        assert isinstance(result["properties"], dict)
        assert "Ports" in result["properties"]

    def test_real_model_parent_has_ref_properties(self):
        """Real model: SubSystem with Ref attributes in <P> preserves the ref value."""
        result = get_parent_subsystem_info(
            REAL_MODEL_DIR, "simulink/systems/system_6.xml"
        )
        assert result is not None
        # "UserData" has a Ref attribute — should be stored as the ref value
        if "UserData" in result["properties"]:
            assert result["properties"]["UserData"].startswith("bdmxdata:")
