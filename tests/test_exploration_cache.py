"""Tests cho pipeline/exploration_cache.py — tất cả 3 chức năng."""

import pytest
from unittest.mock import MagicMock
from pipeline.exploration_cache import (
    ExplorationCache,
    extract_exploration_summary,
    extract_investigation_notes,
    _truncate,
)


# ── Helpers ──────────────────────────────────────────────


def _make_tool(name: str, args: dict = None, result: str = "") -> MagicMock:
    """Tạo mock ToolExecution object."""
    tool = MagicMock()
    tool.tool_name = name
    tool.tool_args = args or {}
    tool.result = result
    return tool


# ── ExplorationCache ─────────────────────────────────────


class TestExplorationCache:

    def test_empty_cache_returns_empty_summary(self):
        cache = ExplorationCache()
        assert cache.get_summary_for_agent("Gain", "SaturateOnIntegerOverflow") == ""

    def test_store_hierarchy_and_get_summary(self):
        cache = ExplorationCache()
        cache.store_hierarchy("Root → SubSystem1 → SubSystem2")
        summary = cache.get_summary_for_agent("Gain", "SaturateOnIntegerOverflow")
        assert "KNOWN FROM PREVIOUS RULES" in summary
        assert "Root → SubSystem1" in summary

    def test_store_blocks_included_in_summary(self):
        cache = ExplorationCache()
        cache.store_hierarchy("Model hierarchy...")
        cache.store_blocks("Gain", "Found 18 Gain blocks")
        summary = cache.get_summary_for_agent("Gain", "SaturateOnIntegerOverflow")
        assert "Found 18 Gain blocks" in summary

    def test_different_block_type_not_included(self):
        cache = ExplorationCache()
        cache.store_hierarchy("Model hierarchy...")
        cache.store_blocks("Gain", "Found 18 Gain blocks")
        summary = cache.get_summary_for_agent("Abs", "SaturateOnIntegerOverflow")
        assert "Gain blocks" not in summary
        # Hierarchy is still included (shared for all)
        assert "Model hierarchy..." in summary

    def test_store_config_included_in_summary(self):
        cache = ExplorationCache()
        cache.store_hierarchy("Model hierarchy...")
        cache.store_config("Gain", "SaturateOnIntegerOverflow", "17 explicit on, 1 default off")
        summary = cache.get_summary_for_agent("Gain", "SaturateOnIntegerOverflow")
        assert "17 explicit on" in summary

    def test_summary_includes_skip_hint(self):
        cache = ExplorationCache()
        cache.store_hierarchy("Model hierarchy...")
        summary = cache.get_summary_for_agent("Gain", "SaturateOnIntegerOverflow")
        assert "SKIP" in summary

    def test_populate_from_tools(self):
        cache = ExplorationCache()
        tools = [
            _make_tool("build_model_hierarchy", result="Root → SubSystem"),
            _make_tool("find_blocks_recursive", {"block_type": "Gain"}, "18 blocks found"),
            _make_tool("query_config", {"block_type": "Gain", "config_name": "Sat"}, "17 on, 1 off"),
        ]
        cache.populate_from_tools(tools, block_type="Gain", config_name="Sat")
        summary = cache.get_summary_for_agent("Gain", "Sat")
        assert "Root → SubSystem" in summary
        assert "18 blocks found" in summary
        assert "17 on, 1 off" in summary

    def test_populate_empty_tools(self):
        cache = ExplorationCache()
        cache.populate_from_tools([], block_type="Gain")
        assert cache.get_summary_for_agent("Gain", "X") == ""

    def test_populate_skips_non_matching_tools(self):
        cache = ExplorationCache()
        tools = [
            _make_tool("write_python_file", {"filename": "test.py"}, "OK"),
            _make_tool("test_xpath_query", {"xpath": "..."}, "match"),
        ]
        cache.populate_from_tools(tools, block_type="Gain", config_name="Sat")
        # Only hierarchy, blocks, config are cached
        assert cache.get_summary_for_agent("Gain", "Sat") == ""

    def test_hierarchy_stored_only_once(self):
        cache = ExplorationCache()
        cache.store_hierarchy("First")
        cache.store_hierarchy("Second")
        summary = cache.get_summary_for_agent("X", "Y")
        assert "First" in summary
        assert "Second" not in summary

    def test_thread_safety(self):
        """Basic thread safety — no crash under concurrent access."""
        import threading
        cache = ExplorationCache()
        errors = []

        def worker(block_type):
            try:
                cache.store_hierarchy(f"Hierarchy from {block_type}")
                cache.store_blocks(block_type, f"Blocks of {block_type}")
                cache.get_summary_for_agent(block_type, "config")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(f"Type{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


# ── extract_exploration_summary ──────────────────────────


class TestExtractExplorationSummary:

    def test_empty_tools(self):
        assert extract_exploration_summary([]) == ""
        assert extract_exploration_summary(None) == ""

    def test_hierarchy_included(self):
        tools = [_make_tool("build_model_hierarchy", result="Root → Sub1 → Sub2")]
        summary = extract_exploration_summary(tools)
        assert "Model Hierarchy" in summary
        assert "Root → Sub1 → Sub2" in summary

    def test_blocks_included(self):
        tools = [
            _make_tool("find_blocks_recursive", {"block_type": "Gain"}, "18 Gain blocks"),
        ]
        summary = extract_exploration_summary(tools)
        assert "Blocks Found (Gain)" in summary

    def test_config_query_included(self):
        tools = [
            _make_tool("query_config", {"block_type": "Gain", "config_name": "Sat"}, "all on"),
        ]
        summary = extract_exploration_summary(tools)
        assert "Config Query (Gain/Sat)" in summary

    def test_xpath_verified_included(self):
        tools = [
            _make_tool("test_xpath_query", {"xpath": ".//Block[@BlockType='Gain']", "xml_file": "system.xml"}, "3 results"),
        ]
        summary = extract_exploration_summary(tools)
        assert "XPath Verified" in summary
        assert "Block[@BlockType='Gain']" in summary

    def test_auto_discover_included(self):
        tools = [_make_tool("auto_discover_blocks", {"block_keyword": "gain"}, "found 20")]
        summary = extract_exploration_summary(tools)
        assert "Auto-discover (gain)" in summary

    def test_write_python_file_excluded(self):
        tools = [_make_tool("write_python_file", {"filename": "test.py"}, "OK")]
        assert extract_exploration_summary(tools) == ""

    def test_truncation_applied(self):
        tools = [_make_tool("build_model_hierarchy", result="X" * 5000)]
        summary = extract_exploration_summary(tools)
        assert "chars omitted" in summary

    def test_full_pipeline_tools(self):
        """Simulate realistic Agent 2 tool history."""
        tools = [
            _make_tool("build_model_hierarchy", result="3 subsystems"),
            _make_tool("find_blocks_recursive", {"block_type": "Gain"}, "18 blocks"),
            _make_tool("query_config", {"block_type": "Gain", "config_name": "Sat"}, "17 on"),
            _make_tool("test_xpath_query", {"xpath": ".//Block", "xml_file": "sys.xml"}, "OK"),
            _make_tool("write_python_file", {"filename": "check.py"}, "done"),
        ]
        summary = extract_exploration_summary(tools)
        assert "Agent 2 Exploration Log" in summary
        assert "Model Hierarchy" in summary
        assert "Blocks Found" in summary
        assert "Config Query" in summary
        assert "XPath Verified" in summary
        # write_python_file NOT included
        assert "check.py" not in summary

    def test_header_present(self):
        tools = [_make_tool("build_model_hierarchy", result="data")]
        summary = extract_exploration_summary(tools)
        assert "KHÔNG cần explore lại" in summary


# ── extract_investigation_notes ──────────────────────────


class TestExtractInvestigationNotes:

    def test_empty_tools(self):
        assert extract_investigation_notes([]) == ""
        assert extract_investigation_notes(None) == ""

    def test_find_blocks_included(self):
        tools = [_make_tool("find_blocks_recursive", {"block_type": "Gain"}, "18 blocks")]
        notes = extract_investigation_notes(tools)
        assert "find_blocks_recursive(Gain)" in notes

    def test_query_config_included(self):
        tools = [_make_tool("query_config", {"block_type": "Gain", "config_name": "X"}, "result")]
        notes = extract_investigation_notes(tools)
        assert "query_config(Gain, X)" in notes

    def test_deep_search_included(self):
        tools = [_make_tool("deep_search_xml_text", {"xml_file": "sys.xml", "regex_pattern": "Gain"}, "3 matches")]
        notes = extract_investigation_notes(tools)
        assert "deep_search(sys.xml, Gain)" in notes

    def test_raw_block_config_included(self):
        tools = [_make_tool("read_raw_block_config", {"block_sid": "42"}, "raw data")]
        notes = extract_investigation_notes(tools)
        assert "read_raw_block_config(SID=42)" in notes

    def test_rewrite_reason_included(self):
        tools = [_make_tool("rewrite_advanced_code", {"reason": "MaskType not BlockType"}, "OK")]
        notes = extract_investigation_notes(tools)
        assert "REWRITE: MaskType not BlockType" in notes

    def test_xpath_test_included(self):
        tools = [_make_tool("test_xpath_query", {"xpath": ".//X", "xml_file": "f.xml"}, "2 results")]
        notes = extract_investigation_notes(tools)
        assert "test_xpath(f.xml, .//X)" in notes

    def test_read_python_file_included(self):
        tools = [_make_tool("read_python_file", {"filename": "check.py"}, "code content")]
        notes = extract_investigation_notes(tools)
        assert "read_python_file(check.py)" in notes

    def test_list_all_configs_included(self):
        tools = [_make_tool("list_all_configs", {"block_sid": "42"}, "configs data")]
        notes = extract_investigation_notes(tools)
        assert "list_all_configs(SID=42)" in notes

    def test_trace_connections_included(self):
        tools = [_make_tool("trace_connections", {"block_sid": "99"}, "connections")]
        notes = extract_investigation_notes(tools)
        assert "trace_connections(SID=99)" in notes

    def test_non_investigation_tools_excluded(self):
        tools = [
            _make_tool("build_model_hierarchy", result="hierarchy"),
            _make_tool("list_xml_files", result="5 files"),
            _make_tool("write_python_file", {"filename": "test.py"}, "done"),
        ]
        assert extract_investigation_notes(tools) == ""

    def test_header_present(self):
        tools = [_make_tool("find_blocks_recursive", {"block_type": "X"}, "data")]
        notes = extract_investigation_notes(tools)
        assert notes.startswith("Đã điều tra:")


# ── _truncate ────────────────────────────────────────────


class TestTruncate:

    def test_short_text_unchanged(self):
        assert _truncate("hello", 100) == "hello"

    def test_long_text_truncated(self):
        result = _truncate("X" * 100, 50)
        assert len(result) < 100
        assert "50 chars omitted" in result

    def test_exact_length_unchanged(self):
        assert _truncate("12345", 5) == "12345"
