"""
Pipeline chính: Điều phối 6-7 agents chạy song song theo từng rule.

Features:
  - State machine retry loop: luồng rõ ràng, routing tập trung 1 chỗ
  - Parallel rule processing: asyncio.gather + Semaphore (configurable concurrency)
  - Shared XML cache: Agent 2 & 5 chia sẻ parsed XML tree (tránh parse lại)
  - Error handling: Agent 4/5 LLM fail không crash rule, tự escalate
  - Diff-based discovery: Agent 1.5 phân tích model diff → ground truth cho Agent 2/5
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from lxml import etree

from schemas.validation_schemas import TestCase, ValidationResult, ValidationStatus
from schemas.block_schemas import BlockMappingData
from schemas.diff_schemas import ConfigDiscovery, ModelDiff
from schemas.report_schemas import FinalReport, PipelineStep, RuleReport
from schemas.rule_schemas import ParsedRule, RuleInput
from schemas.agent_inputs import Agent1Input, Agent1_5Input, Agent2Input

from agno.agent import Agent

from agents.agent0_rule_analyzer import create_agent0
from agents.agent1_data_reader import create_agent1
from agents.agent1_5_diff_analyzer import create_agent1_5
from agents.agent2_code_generator import create_agent2
from agents.agent3_validator import Validator, create_agent3
from agents.agent4_bug_fixer import create_agent4
from agents.agent5_inspector import create_agent5

from tools.xml_tools import XmlToolkit

from pipeline.state_machine import RetryStateMachine, RetryState
from pipeline.exploration_cache import (
    ExplorationCache,
    extract_exploration_summary,
    extract_investigation_notes,
)

from utils.slx_extractor import extract_slx
from utils.model_differ import build_agent_context
from utils.input_validator import validate_rule_input, has_blocking_errors
from config import settings

logger = logging.getLogger(__name__)


async def run_pipeline(
    model_path: str,
    blocks_path: str,
    rules_path: str,
    expected_path: str,
    diff_result: ModelDiff | None = None,
) -> FinalReport:
    """Chạy toàn bộ pipeline cho tất cả rules — song song nếu concurrency > 1.

    Args:
        diff_result: Kết quả diff từ model_differ (nếu user cung cấp --model-before).
                     Được dùng bởi Agent 1.5 để phân tích config locations.
    """
    pipeline_start = time.monotonic()

    # ── Chuẩn bị ──────────────────────────────────────
    model_dir = extract_slx(model_path)
    rules = [RuleInput(**r) for r in json.loads(Path(rules_path).read_text(encoding="utf-8"))]
    expected_list = json.loads(Path(expected_path).read_text(encoding="utf-8"))

    # ── Shared XML cache (tất cả agents chia sẻ parsed trees) ──
    shared_xml_cache: dict[str, etree._ElementTree] = {}
    output_dir = str(settings.GENERATED_CHECKS_DIR)

    # ── Cross-rule exploration cache (Fix D) ──
    exploration_cache = ExplorationCache()

    # ── Agent factory: mỗi concurrent task cần agent set riêng ──
    def _make_agents() -> tuple[tuple, Agent | None]:
        xml_toolkit = XmlToolkit(model_dir=model_dir, shared_cache=shared_xml_cache)
        agents = (
            create_agent0(),
            create_agent1(blocks_path),
            create_agent2(xml_toolkit=xml_toolkit, output_dir=output_dir),
            create_agent3(timeout=settings.SANDBOX_TIMEOUT),
            create_agent4(),
            create_agent5(xml_toolkit=xml_toolkit, output_dir=output_dir),
        )
        has_diff_changes = diff_result and diff_result.config_changes
        agent1_5 = create_agent1_5() if has_diff_changes else None
        return agents, agent1_5

    # ── Xử lý rules ──────────────────────────────────
    concurrency = max(1, settings.MAX_CONCURRENT_RULES)

    if concurrency == 1:
        agents, agent1_5 = _make_agents()
        rule_reports = await _run_sequential(
            rules, expected_list, agents, model_dir,
            diff_result=diff_result, agent1_5=agent1_5,
            exploration_cache=exploration_cache,
        )
    else:
        # Pre-populate hierarchy vào cache trước khi spawn parallel tasks
        # → tất cả tasks dùng chung hierarchy (tránh N lần parse lại)
        if exploration_cache:
            from utils.model_index import ModelIndex
            idx = ModelIndex(model_dir, shared_xml_cache)
            hierarchy = idx.build_hierarchy()
            exploration_cache.store_hierarchy(json.dumps(hierarchy, indent=2, ensure_ascii=False))

        rule_reports = await _run_parallel(
            rules, expected_list, _make_agents, concurrency, model_dir,
            diff_result=diff_result,
            exploration_cache=exploration_cache,
        )

    pipeline_duration = time.monotonic() - pipeline_start
    return FinalReport(
        model_file=model_path,
        total_rules=len(rules),
        results=rule_reports,
        total_duration_seconds=round(pipeline_duration, 2),
    )


async def _run_sequential(
    rules, expected_list, agents, model_dir: str = "",
    diff_result: ModelDiff | None = None, agent1_5=None,
    exploration_cache: ExplorationCache | None = None,
) -> list[RuleReport]:
    """Chạy tuần tự — 1 bộ agents dùng lại cho mọi rules."""
    rule_reports = []

    for rule in rules:
        logger.info(f"[{rule.rule_id}] Bắt đầu xử lý: {rule.description[:60]}...")
        test_cases = _find_test_cases(expected_list, rule.rule_id)

        report = await _process_rule(
            rule=rule, test_cases=test_cases, agents=agents, model_dir=model_dir,
            diff_result=diff_result, agent1_5=agent1_5,
            exploration_cache=exploration_cache,
        )
        rule_reports.append(report)
        logger.info(f"[{rule.rule_id}] Kết quả: {report.status}")

    return rule_reports


async def _run_parallel(
    rules, expected_list, make_agents_fn, concurrency: int, model_dir: str = "",
    diff_result: ModelDiff | None = None,
    exploration_cache: ExplorationCache | None = None,
) -> list[RuleReport]:
    """Chạy song song với semaphore giới hạn concurrency.

    Features:
      - Per-rule error isolation: 1 rule crash không kill rules khác
      - Progress reporting: log completion count
      - Semaphore throttle: giới hạn concurrent rules
    """
    semaphore = asyncio.Semaphore(concurrency)
    completed = 0
    total = len(rules)
    logger.info(f"Parallel mode: {concurrency} rules đồng thời, tổng {total} rules")

    async def _process_with_limit(rule, test_cases):
        nonlocal completed
        async with semaphore:
            logger.info(f"[{rule.rule_id}] Bắt đầu xử lý (parallel)")
            try:
                agents, agent1_5 = make_agents_fn()
                report = await _process_rule(
                    rule=rule, test_cases=test_cases, agents=agents, model_dir=model_dir,
                    diff_result=diff_result, agent1_5=agent1_5,
                    exploration_cache=exploration_cache,
                )
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                logger.error(f"[{rule.rule_id}] Unexpected error in parallel task: {e}\n{tb}")
                validation = ValidationResult(
                    rule_id=rule.rule_id,
                    status=ValidationStatus.SCHEMA_ERROR,
                    stderr=f"Parallel task error: {e}\n{tb}",
                    code_file_path="",
                )
                report = RuleReport.from_validation(rule.rule_id, validation, [])
            completed += 1
            logger.info(f"[{rule.rule_id}] Kết quả: {report.status} ({completed}/{total} done)")
            return report

    tasks = [
        _process_with_limit(rule, _find_test_cases(expected_list, rule.rule_id))
        for rule in rules
    ]
    return list(await asyncio.gather(*tasks))


async def _process_rule(
    rule, test_cases: list[TestCase], agents, model_dir: str = "",
    diff_result: ModelDiff | None = None, agent1_5=None,
    exploration_cache: ExplorationCache | None = None,
) -> RuleReport:
    """Xử lý 1 rule qua pipeline 6-7 agents.

    Luồng chính:
      Agent 0 → Agent 1 → [Agent 1.5] → Agent 2 → Agent 3
      → Retry loop (State Machine): Agent 4 / Agent 5 ↔ Agent 3
    """
    agent0, agent1, agent2, agent3, agent4, agent5 = agents
    steps: list[PipelineStep] = []
    rule_start = time.monotonic()
    config_discovery: ConfigDiscovery | None = None

    # Khởi tạo state machine TRƯỚC try block → luôn có trace dù pipeline crash
    sm = RetryStateMachine(
        max_agent4=settings.MAX_RETRY_AGENT4,
        max_agent5=settings.MAX_RETRY_AGENT5,
    )

    try:
        # ── Agent 0: Parse rule text ──────────────────────
        t0 = time.monotonic()
        response0 = await agent0.arun(rule.description)
        parsed_rule = _extract_content(response0, "Agent 0", ParsedRule)
        parsed_rule.rule_id = rule.rule_id
        steps.append(_step("Agent 0 (Rule Analyzer)", t0, output_summary=f"block_keyword={parsed_rule.block_keyword}"))
        logger.debug(f"[{rule.rule_id}] Agent 0: block_keyword={parsed_rule.block_keyword}")

        # ── Input validation (non-blocking warnings, blocking errors) ──
        if model_dir:
            validation_msgs = validate_rule_input(parsed_rule, model_dir)
            if has_blocking_errors(validation_msgs):
                raise ValueError(
                    f"Input validation failed: {'; '.join(m for m in validation_msgs if m.startswith('ERROR:'))}"
                )

        # ── Agent 1: Search block dictionary ─────────────
        # Skip Agent 1 khi block_keyword rỗng (config-only rule)
        if parsed_rule.block_keyword:
            t1 = time.monotonic()
            agent1_input = Agent1Input(
                block_keyword=parsed_rule.block_keyword,
                config_name=parsed_rule.config_name,
            )
            response1 = await agent1.arun(agent1_input.to_prompt())
            block_data = _extract_content(response1, "Agent 1", BlockMappingData)
            steps.append(_step("Agent 1 (Data Reader)", t1, output_summary=f"name_xml={block_data.name_xml}"))
            logger.debug(f"[{rule.rule_id}] Agent 1: name_xml={block_data.name_xml}")
        else:
            # Config-only rule: skip Agent 1, tạo BlockMappingData rỗng
            # Agent 2 sẽ tự dùng find_config_locations() để xác định block types
            block_data = BlockMappingData(
                name_ui="",
                name_xml="",
                xml_representation="unknown",
                search_confidence=0,
                config_map_analysis=(
                    f"Rule không chỉ định block type. Config '{parsed_rule.config_name}' "
                    f"cần được tìm bằng find_config_locations('{parsed_rule.config_name}') "
                    f"để xác định tất cả block types có config này."
                ),
            )
            steps.append(_step("Agent 1 (SKIPPED — config-only rule)", time.monotonic()))
            logger.info(f"[{rule.rule_id}] Agent 1 skipped — block_keyword rỗng, config-only rule")

        # ── Agent 1.5: Diff Analyzer (chỉ khi có diff_result) ──
        if diff_result and agent1_5 and diff_result.config_changes:
            # Nếu config-only rule (block_data.name_xml rỗng), thử infer block_type từ diff
            agent1_5_block_type = block_data.name_xml
            if not agent1_5_block_type:
                for change in diff_result.config_changes:
                    if change.config_name == parsed_rule.config_name:
                        agent1_5_block_type = change.mask_type or change.block_type
                        break

            diff_context = build_agent_context(
                diff_result,
                block_type=agent1_5_block_type,
                config_name=parsed_rule.config_name,
                model_dir=model_dir,
            )
            t1_5 = time.monotonic()
            logger.info(f"[{rule.rule_id}] Agent 1.5: phân tích diff ({len(diff_result.config_changes)} changes)")
            agent1_5_input = Agent1_5Input(
                block_type=agent1_5_block_type,
                config_name=parsed_rule.config_name,
                name_ui=block_data.name_ui,
                config_map_analysis=block_data.config_map_analysis,
                diff_context=diff_context,
            )
            response1_5 = await agent1_5.arun(agent1_5_input.to_prompt())
            config_discovery = _extract_content(response1_5, "Agent 1.5", ConfigDiscovery)
            steps.append(_step(
                "Agent 1.5 (Diff Analyzer)", t1_5,
                output_summary=f"location={config_discovery.location_type}, xpath={config_discovery.xpath_pattern}",
            ))
            logger.debug(
                f"[{rule.rule_id}] Agent 1.5: location_type={config_discovery.location_type}, "
                f"xpath_pattern={config_discovery.xpath_pattern}",
            )

        # ── Agent 2: Generate check code ─────────────────
        t2 = time.monotonic()
        agent2_input = Agent2Input.from_pipeline(rule, parsed_rule, block_data, config_discovery)

        # Fix D: Inject cross-rule cache summary (nếu có từ rules trước)
        if exploration_cache:
            cache_summary = exploration_cache.get_summary_for_agent(
                block_data.name_xml, parsed_rule.config_name,
            )
            if cache_summary:
                agent2_input.cache_summary = cache_summary
                logger.debug(f"[{rule.rule_id}] Agent 2: injected cross-rule cache")

        response2 = await agent2.arun(agent2_input.to_prompt())

        # Fix A: Extract exploration summary cho Agent 5 + Fix D: populate cache
        exploration_summary = ""
        agent2_tools = getattr(response2, "tools", None) or []
        if agent2_tools:
            exploration_summary = extract_exploration_summary(agent2_tools)
            if exploration_cache:
                exploration_cache.populate_from_tools(
                    agent2_tools,
                    block_type=block_data.name_xml,
                    config_name=parsed_rule.config_name,
                )

        # Fix I: Append config_discovery info to exploration_summary (so Agent 5 sees it)
        if config_discovery and exploration_summary:
            exploration_summary += (
                f"\n\n### Config Discovery (Agent 1.5 ground truth):\n"
                f"- location_type: {config_discovery.location_type}\n"
                f"- xpath_pattern: {config_discovery.xpath_pattern}\n"
                f"- default_value: {config_discovery.default_value}\n"
                f"- notes: {config_discovery.notes}"
            )
        elif config_discovery and not exploration_summary:
            exploration_summary = (
                f"## Config Discovery (Agent 1.5 ground truth):\n"
                f"- location_type: {config_discovery.location_type}\n"
                f"- xpath_pattern: {config_discovery.xpath_pattern}\n"
                f"- default_value: {config_discovery.default_value}\n"
                f"- notes: {config_discovery.notes}"
            )

        code_file = str(settings.GENERATED_CHECKS_DIR / f"check_rule_{rule.rule_id}.py")
        steps.append(_step("Agent 2 (Code Generator)", t2, output_summary=f"file={code_file}"))
        logger.debug(f"[{rule.rule_id}] Agent 2: generated {code_file}")

        # ── Verify file tồn tại sau Agent 2 ──────────────
        if not Path(code_file).exists():
            raise FileNotFoundError(
                f"Agent 2 không tạo được file: {code_file}. "
                f"Kiểm tra Agent 2 có gọi write_python_file() đúng filename không."
            )

        # ── Agent 3: Validate lần đầu ────────────────────
        t3 = time.monotonic()
        validation = await asyncio.to_thread(_run_validation, agent3, code_file, test_cases, rule.rule_id)
        steps.append(_step(
            "Agent 3 (Validator)", t3,
            status="success" if validation.status == ValidationStatus.PASS else "error",
            output_summary=f"status={validation.status.value}, passed={validation.test_cases_passed}/{validation.test_cases_total}",
        ))

        # ── Retry loop (State Machine) ────────────────────
        #
        # State machine quyết định TOÀN BỘ routing:
        #   PASS        → DONE (break)
        #   CODE_ERROR  → BUG_FIX hoặc INSPECT (adaptive escalation)
        #   WRONG_RESULT, PARTIAL_PASS → INSPECT
        #   Hết budget  → FAILED (break)
        #
        # Fix B: Track Agent 5 investigation findings across retries
        agent5_findings: list[str] = []

        while True:
            state = sm.next_state(validation)
            if state in (RetryState.DONE, RetryState.FAILED):
                break

            sm.record_error(validation)

            if state == RetryState.BUG_FIX:
                sm.increment("agent4")
                context = sm.build_agent4_context(validation)
                logger.info(f"[{rule.rule_id}] Agent 4 fix (attempt {sm.agent4_count}/{sm.max_agent4})")
                t = time.monotonic()
                try:
                    await agent4.arun(context)
                    steps.append(_step(f"Agent 4 (Bug Fixer) #{sm.agent4_count}", t))
                except Exception as e:
                    logger.warning(f"[{rule.rule_id}] Agent 4 LLM error, will escalate: {e}")
                    steps.append(_step(f"Agent 4 #{sm.agent4_count} (LLM error)", t, status="error"))
                    # Code unchanged → same validation → state machine sẽ escalate
                    continue

            elif state == RetryState.INSPECT:
                sm.increment("agent5")
                # Fix A: pass exploration_summary, Fix B: pass previous_findings
                context = sm.build_agent5_context(
                    validation, block_data, config_discovery,
                    exploration_summary=exploration_summary,
                    previous_findings=agent5_findings,
                )
                _reset_xml_toolkit(agents)
                logger.info(f"[{rule.rule_id}] Agent 5 inspect (attempt {sm.agent5_count}/{sm.max_agent5})")
                t = time.monotonic()
                try:
                    response5 = await agent5.arun(context)
                    steps.append(_step(f"Agent 5 (Inspector) #{sm.agent5_count}", t))
                    # Fix B: Extract investigation notes for next retry
                    agent5_tools = getattr(response5, "tools", None) or []
                    if agent5_tools:
                        notes = extract_investigation_notes(agent5_tools)
                        if notes:
                            # Cap per-note length + keep only 3 most recent
                            if len(notes) > 1500:
                                notes = notes[:1500] + "\n... [truncated]"
                            agent5_findings.append(notes)
                            if len(agent5_findings) > 3:
                                agent5_findings = agent5_findings[-3:]
                except Exception as e:
                    logger.warning(f"[{rule.rule_id}] Agent 5 LLM error: {e}")
                    steps.append(_step(f"Agent 5 #{sm.agent5_count} (LLM error)", t, status="error"))
                    # Code unchanged → same validation → state machine sẽ đánh FAILED
                    continue

            # Re-validate sau khi fix/inspect
            tv = time.monotonic()
            validation = await asyncio.to_thread(_run_validation, agent3, code_file, test_cases, rule.rule_id)
            steps.append(_step(
                "Agent 3 (Re-validate)", tv,
                status="success" if validation.status == ValidationStatus.PASS else "error",
                output_summary=f"status={validation.status.value}",
            ))

        # Nếu hết retry → đánh dấu FAILED_*
        if sm.state == RetryState.FAILED:
            sm.mark_final_status(validation)

    except Exception as e:
        logger.error(f"[{rule.rule_id}] Pipeline error: {e}")
        validation = ValidationResult(
            rule_id=rule.rule_id,
            status=ValidationStatus.SCHEMA_ERROR,
            stderr=str(e),
            code_file_path="",
        )

    rule_duration = time.monotonic() - rule_start
    report = RuleReport.from_validation(rule.rule_id, validation, sm.get_trace())
    report.pipeline_steps = steps
    report.rule_duration_seconds = round(rule_duration, 2)
    return report


# ── Helpers ──────────────────────────────────────────────


def _reset_xml_toolkit(agents) -> None:
    """Reset loop detector trên shared XmlToolkit khi chuyển agent.

    Iterates all agents looking for XmlToolkit — robust against index changes.
    Shared toolkit → reset 1 lần là đủ.
    """
    for agent in agents:
        if hasattr(agent, "tools"):
            for tool in getattr(agent, "tools", []) or []:
                if hasattr(tool, "reset_loop_detector"):
                    tool.reset_loop_detector()
                    return


def _run_validation(
    agent3: Validator, code_file: str, test_cases: list[TestCase], rule_id: str,
) -> ValidationResult:
    """Chạy Agent 3 validate — pure Python, không LLM."""
    return agent3.validate(code_file, test_cases, rule_id)


def _extract_content(response, agent_name: str, expected_type: type):
    """Extract .content từ RunResponse với null-check và type validation."""
    content = response.content
    if content is None:
        # Include response text (nếu có) để debug
        resp_text = ""
        if hasattr(response, "messages") and response.messages:
            last_msg = response.messages[-1]
            resp_text = str(getattr(last_msg, "content", ""))[:300]
        raise ValueError(
            f"{agent_name} trả về content=None (expected {expected_type.__name__}). "
            f"LLM có thể đã fail structured output. "
            f"Response text: {resp_text or '(empty)'}"
        )
    if not isinstance(content, expected_type):
        raise TypeError(
            f"{agent_name} trả về {type(content).__name__} thay vì {expected_type.__name__}. "
            f"Content: {str(content)[:300]}"
        )
    return content


def _step(
    agent_name: str, start_time: float,
    status: str = "success", output_summary: str = "",
) -> PipelineStep:
    """Tạo PipelineStep với timing chính xác hơn.

    Dùng monotonic duration + wall clock finished_at để tính ngược started_at.
    """
    duration = time.monotonic() - start_time
    finished = datetime.now(timezone.utc)
    started = finished - timedelta(seconds=duration)
    return PipelineStep(
        agent_name=agent_name,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        duration_seconds=round(duration, 2),
        status=status,
        output_summary=output_summary,
    )


def _find_test_cases(expected_list: list, rule_id: str) -> list[TestCase]:
    """Tìm test cases cho rule_id từ expected_results.json."""
    for item in expected_list:
        if item.get("rule_id") == rule_id:
            return [TestCase(**tc) for tc in item.get("test_cases", [])]
    return []
