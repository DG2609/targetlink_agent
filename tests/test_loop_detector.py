"""Tests cho utils/loop_detector.py — loop detection + classification."""

import pytest
from utils.loop_detector import LoopDetector, LoopType


class TestLoopDetectorBasics:

    def test_no_loop_single_call(self):
        ld = LoopDetector(max_repeats=3)
        result = ld.check("test_xpath_query", xml_file="f.xml", xpath=".//Block")
        assert result is None

    def test_no_loop_different_args(self):
        ld = LoopDetector(max_repeats=3)
        ld.check("test_xpath_query", xml_file="a.xml", xpath=".//Block")
        ld.check("test_xpath_query", xml_file="b.xml", xpath=".//Block")
        result = ld.check("test_xpath_query", xml_file="c.xml", xpath=".//Block")
        assert result is None

    def test_loop_detected_after_threshold(self):
        ld = LoopDetector(max_repeats=3)
        ld.check("test_xpath_query", xml_file="f.xml", xpath=".//Block")
        ld.check("test_xpath_query", xml_file="f.xml", xpath=".//Block")
        result = ld.check("test_xpath_query", xml_file="f.xml", xpath=".//Block")
        assert result is not None
        assert "LOOP DETECTED" in result

    def test_no_loop_below_threshold(self):
        ld = LoopDetector(max_repeats=3)
        ld.check("test_xpath_query", xml_file="f.xml", xpath=".//Block")
        result = ld.check("test_xpath_query", xml_file="f.xml", xpath=".//Block")
        assert result is None

    def test_reset_clears_history(self):
        ld = LoopDetector(max_repeats=3)
        ld.check("tool", arg="val")
        ld.check("tool", arg="val")
        ld.reset()
        result = ld.check("tool", arg="val")
        assert result is None  # Only 1 after reset


class TestLoopDetectorClassification:

    def test_xpath_no_result(self):
        ld = LoopDetector(max_repeats=2)
        ld.check("test_xpath_query", xpath=".//X")
        result = ld.check("test_xpath_query", xpath=".//X")
        assert "XPath" in result
        assert "deep_search_xml_text" in result

    def test_read_xml_structure_same_category(self):
        ld = LoopDetector(max_repeats=2)
        ld.check("read_xml_structure", xpath=".//X")
        result = ld.check("read_xml_structure", xpath=".//X")
        assert "XPath" in result

    def test_block_not_found(self):
        ld = LoopDetector(max_repeats=2)
        ld.check("find_blocks_recursive", block_type="TL_Magic")
        result = ld.check("find_blocks_recursive", block_type="TL_Magic")
        assert "Block type" in result
        assert "auto_discover_blocks" in result

    def test_regex_no_match(self):
        ld = LoopDetector(max_repeats=2)
        ld.check("deep_search_xml_text", regex_pattern="nonexistent")
        result = ld.check("deep_search_xml_text", regex_pattern="nonexistent")
        assert "Regex" in result

    def test_config_not_found(self):
        ld = LoopDetector(max_repeats=2)
        ld.check("query_config", block_type="Gain", config_name="X")
        result = ld.check("query_config", block_type="Gain", config_name="X")
        assert "Config" in result
        assert "list_all_configs" in result

    def test_generic_fallback(self):
        ld = LoopDetector(max_repeats=2)
        ld.check("some_unknown_tool", arg="val")
        result = ld.check("some_unknown_tool", arg="val")
        assert "approach khác" in result

    def test_auto_discover_blocks_classified(self):
        ld = LoopDetector(max_repeats=2)
        ld.check("auto_discover_blocks", block_keyword="xyz")
        result = ld.check("auto_discover_blocks", block_keyword="xyz")
        assert "Block type" in result

    def test_list_all_configs_classified(self):
        ld = LoopDetector(max_repeats=2)
        ld.check("list_all_configs", block_sid="99")
        result = ld.check("list_all_configs", block_sid="99")
        assert "Config" in result

    def test_read_raw_block_config_classified(self):
        ld = LoopDetector(max_repeats=2)
        ld.check("read_raw_block_config", block_sid="42")
        result = ld.check("read_raw_block_config", block_sid="42")
        assert "Config" in result

    def test_trace_connections_classified(self):
        ld = LoopDetector(max_repeats=2)
        ld.check("trace_connections", block_sid="10")
        result = ld.check("trace_connections", block_sid="10")
        assert "LOOP DETECTED" in result
        assert "approach khác" in result

    def test_build_model_hierarchy_classified(self):
        ld = LoopDetector(max_repeats=2)
        ld.check("build_model_hierarchy")
        result = ld.check("build_model_hierarchy")
        assert "LOOP DETECTED" in result


class TestLoopDetectorInterleaved:

    def test_interleaved_calls_no_loop(self):
        """Different tools interleaved don't trigger loop."""
        ld = LoopDetector(max_repeats=3)
        for _ in range(5):
            assert ld.check("tool_a", x=1) is None
            assert ld.check("tool_b", x=1) is None

    def test_loop_resets_with_different_call(self):
        """Consecutive count resets when a different call intervenes."""
        ld = LoopDetector(max_repeats=3)
        ld.check("test_xpath_query", xpath=".//X")
        ld.check("test_xpath_query", xpath=".//X")
        ld.check("deep_search_xml_text", regex_pattern="break")  # Intervene
        ld.check("test_xpath_query", xpath=".//X")
        result = ld.check("test_xpath_query", xpath=".//X")
        assert result is None  # Only 2 consecutive, not 3
