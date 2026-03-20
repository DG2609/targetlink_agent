"""
Quản lý exploration knowledge giữa agents và giữa rules.

Ba chức năng chính:
  1. ExplorationCache: cache cross-rule (cùng model, Agent 2 rule N → Agent 2 rule N+1)
  2. extract_exploration_summary(): Agent 2 → Agent 5 knowledge handoff
  3. extract_investigation_notes(): Agent 5 attempt N → Agent 5 attempt N+1

Pattern từ reference codebase (agentic/agent/subagents.py):
  Knowledge discovered by one phase should be passed to the next.
"""

import threading

from config import settings


class ExplorationCache:
    """Cache exploration results across rules for same model.

    Thread-safe — dùng được cho cả sequential và parallel rule processing.

    Stores:
      - Model hierarchy (shared, same model)
      - Block findings per type
      - Config query results
    """

    MAX_ENTRIES = 50  # Giới hạn tổng số entries (blocks + configs) để tránh memory bloat

    def __init__(self):
        self._lock = threading.Lock()
        self._model_hierarchy: str | None = None
        self._blocks: dict[str, str] = {}
        self._configs: dict[str, str] = {}

    def store_hierarchy(self, result: str) -> None:
        with self._lock:
            if self._model_hierarchy is None:
                self._model_hierarchy = result

    def store_blocks(self, block_type: str, result: str) -> None:
        with self._lock:
            if len(self._blocks) + len(self._configs) < self.MAX_ENTRIES:
                self._blocks[block_type] = result

    def store_config(self, block_type: str, config_name: str, result: str) -> None:
        with self._lock:
            if len(self._blocks) + len(self._configs) < self.MAX_ENTRIES:
                self._configs[f"{block_type}:{config_name}"] = result

    def get_summary_for_agent(self, block_type: str, config_name: str) -> str:
        """Generate condensed cache summary for Agent 2 context.

        Returns empty string if no useful cached data.
        """
        with self._lock:
            if not self._model_hierarchy:
                return ""

            parts = [
                "## KNOWN FROM PREVIOUS RULES (cùng model, đã verified):",
                "",
                "### Model Hierarchy:",
                _truncate(self._model_hierarchy, settings.CACHE_SUMMARY_LIMIT),
            ]

            if block_type in self._blocks:
                parts.append(f"\n### {block_type} Blocks Found:")
                parts.append(_truncate(self._blocks[block_type], settings.CACHE_SUMMARY_LIMIT))

            key = f"{block_type}:{config_name}"
            if key in self._configs:
                parts.append(f"\n### Config '{config_name}' on {block_type}:")
                parts.append(_truncate(self._configs[key], settings.CACHE_SUMMARY_LIMIT))

            parts.append(
                "\n→ SKIP build_model_hierarchy() và find_blocks_recursive() "
                "nếu info trên ĐỦ. Đi thẳng verify XPath + viết code."
            )
            return "\n".join(parts)

    def populate_from_tools(
        self, tools: list, block_type: str = "", config_name: str = "",
    ) -> None:
        """Populate cache from Agent 2's tool execution results.

        Args:
            tools: List of ToolExecution from RunOutput.tools.
            block_type: Block type for this rule.
            config_name: Config name for this rule.
        """
        if not tools:
            return
        for tool in tools:
            name = getattr(tool, "tool_name", "") or ""
            result = getattr(tool, "result", "") or ""
            if not name or not result:
                continue

            if name == "build_model_hierarchy":
                self.store_hierarchy(result)
            elif name == "find_blocks_recursive":
                # Use block_type from args if available, fallback to caller's block_type
                bt = block_type
                args = getattr(tool, "tool_args", {}) or {}
                if args.get("block_type"):
                    bt = args["block_type"]
                if bt:
                    self.store_blocks(bt, result)
            elif name == "query_config":
                args = getattr(tool, "tool_args", {}) or {}
                bt = args.get("block_type", block_type)
                cn = args.get("config_name", config_name)
                if bt and cn:
                    self.store_config(bt, cn, result)


def extract_exploration_summary(tools: list) -> str:
    """Extract condensed exploration summary from Agent 2's tool history.

    Dùng để truyền knowledge Agent 2 → Agent 5 mà không cần re-explore.

    Args:
        tools: List of ToolExecution from agent2.arun() response.

    Returns:
        Formatted summary string, or empty string if no useful data.
    """
    if not tools:
        return ""

    parts = ["## Agent 2 Exploration Log (verified — KHÔNG cần explore lại):"]

    for tool in tools:
        name = getattr(tool, "tool_name", "") or ""
        args = getattr(tool, "tool_args", {}) or {}
        result = getattr(tool, "result", "") or ""
        if not name or not result:
            continue

        result_short = _truncate(result, settings.CACHE_SUMMARY_LIMIT)

        if name == "build_model_hierarchy":
            parts.append(f"\n### Model Hierarchy:\n{result_short}")
        elif name == "find_blocks_recursive":
            bt = args.get("block_type", "?")
            parts.append(f"\n### Blocks Found ({bt}):\n{result_short}")
        elif name == "query_config":
            bt = args.get("block_type", "?")
            cn = args.get("config_name", "?")
            parts.append(f"\n### Config Query ({bt}/{cn}):\n{result_short}")
        elif name == "test_xpath_query":
            xpath = args.get("xpath", "?")
            xml_f = args.get("xml_file", "?")
            parts.append(f"\n### XPath Verified ({xml_f}):\n`{xpath}`\n{result_short}")
        elif name == "auto_discover_blocks":
            kw = args.get("block_keyword", "?")
            parts.append(f"\n### Auto-discover ({kw}):\n{result_short}")
        elif name == "trace_cross_subsystem":
            sid = args.get("block_sid", "?")
            direction = args.get("direction", "?")
            parts.append(f"\n### Cross-subsystem Trace (SID={sid}, {direction}):\n{result_short}")

    if len(parts) <= 1:
        return ""
    return "\n".join(parts)


def extract_investigation_notes(tools: list) -> str:
    """Extract investigation findings from Agent 5's tool history.

    Dùng để carry forward giữa các lần retry của Agent 5.

    Args:
        tools: List of ToolExecution from agent5.arun() response.

    Returns:
        Condensed investigation notes, or empty string.
    """
    if not tools:
        return ""

    parts: list[str] = []

    for tool in tools:
        name = getattr(tool, "tool_name", "") or ""
        args = getattr(tool, "tool_args", {}) or {}
        result = getattr(tool, "result", "") or ""
        if not name or not result:
            continue

        if name == "find_blocks_recursive":
            bt = args.get("block_type", "?")
            parts.append(f"- find_blocks_recursive({bt}): {_truncate(result, 300)}")
        elif name == "query_config":
            bt = args.get("block_type", "?")
            cn = args.get("config_name", "?")
            parts.append(f"- query_config({bt}, {cn}): {_truncate(result, 300)}")
        elif name == "deep_search_xml_text":
            pattern = args.get("regex_pattern", "?")
            xml_f = args.get("xml_file", "?")
            parts.append(f"- deep_search({xml_f}, {pattern}): {_truncate(result, 300)}")
        elif name == "read_raw_block_config":
            sid = args.get("block_sid", "?")
            parts.append(f"- read_raw_block_config(SID={sid}): {_truncate(result, 500)}")
        elif name == "rewrite_advanced_code":
            reason = args.get("reason", "không rõ")
            parts.append(f"- REWRITE: {reason}")
        elif name == "test_xpath_query":
            xpath = args.get("xpath", "?")
            xml_f = args.get("xml_file", "?")
            parts.append(f"- test_xpath({xml_f}, {xpath}): {_truncate(result, 150)}")
        elif name == "read_python_file":
            fn = args.get("filename", "?")
            parts.append(f"- read_python_file({fn}): {_truncate(result, 200)}")
        elif name == "list_all_configs":
            sid = args.get("block_sid", "?")
            parts.append(f"- list_all_configs(SID={sid}): {_truncate(result, 300)}")
        elif name == "trace_connections":
            sid = args.get("block_sid", "?")
            parts.append(f"- trace_connections(SID={sid}): {_truncate(result, 300)}")
        elif name == "trace_cross_subsystem":
            sid = args.get("block_sid", "?")
            direction = args.get("direction", "?")
            parts.append(f"- trace_cross_subsystem(SID={sid}, {direction}): {_truncate(result, 300)}")

    if not parts:
        return ""
    return "Đã điều tra:\n" + "\n".join(parts)


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text with indicator."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [{len(text) - max_chars} chars omitted]"
