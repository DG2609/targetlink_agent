"""
Pipeline chính: Điều phối 6 agents chạy song song theo từng rule.

Features:
  - Parallel rule processing: asyncio.gather + Semaphore (configurable concurrency)
  - Shared XML cache: Agent 2 & 5 chia sẻ parsed XML tree (tránh parse lại)
  - Loop detection & output truncation: tích hợp trong XmlToolkit
  - Extract .content từ RunResponse cho agents có response_model
  - Error history: agent biết lỗi trước đó, không lặp approach cũ
  - File verification: kiểm tra file tồn tại sau Agent 2
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from lxml import etree

from schemas.validation_schemas import TestCase, ValidationResult, ValidationStatus
from schemas.block_schemas import BlockMappingData
from schemas.report_schemas import FinalReport, PipelineStep, RuleReport
from schemas.rule_schemas import ParsedRule, RuleInput

from agents.agent0_rule_analyzer import create_agent0
from agents.agent1_data_reader import create_agent1
from agents.agent2_code_generator import create_agent2
from agents.agent3_validator import Validator, create_agent3
from agents.agent4_bug_fixer import create_agent4
from agents.agent5_inspector import create_agent5

from tools.xml_tools import XmlToolkit

from pipeline.router import route_validation
from pipeline.retry import RetryManager, classify_error

from utils.slx_extractor import extract_slx
from utils.input_validator import validate_rule_input, has_blocking_errors
from config import settings

logger = logging.getLogger(__name__)


async def run_pipeline(
    model_path: str,
    blocks_path: str,
    rules_path: str,
    expected_path: str,
) -> FinalReport:
    """Chạy toàn bộ pipeline cho tất cả rules — song song nếu concurrency > 1."""
    pipeline_start = time.monotonic()

    # ── Chuẩn bị ──────────────────────────────────────────
    model_dir = extract_slx(model_path)
    rules = [RuleInput(**r) for r in json.loads(Path(rules_path).read_text(encoding="utf-8"))]
    expected_list = json.loads(Path(expected_path).read_text(encoding="utf-8"))

    # ── Shared XML cache (tất cả agents chia sẻ parsed trees) ──
    shared_xml_cache: dict[str, etree._ElementTree] = {}
    output_dir = str(settings.GENERATED_CHECKS_DIR)

    # ── Agent factory: mỗi concurrent task cần agent set riêng ──
    def _make_agents():
        # Mỗi task tạo XmlToolkit riêng (loop detector riêng)
        # nhưng chia sẻ shared_xml_cache (tránh parse XML lại)
        xml_toolkit = XmlToolkit(model_dir=model_dir, shared_cache=shared_xml_cache)
        return (
            create_agent0(),
            create_agent1(blocks_path),
            create_agent2(xml_toolkit=xml_toolkit, output_dir=output_dir),
            create_agent3(timeout=settings.SANDBOX_TIMEOUT),
            create_agent4(),
            create_agent5(xml_toolkit=xml_toolkit, output_dir=output_dir),
        )

    # ── Xử lý rules ──────────────────────────────────────
    concurrency = max(1, settings.MAX_CONCURRENT_RULES)

    if concurrency == 1:
        # Tuần tự: dùng 1 bộ agents cho mọi rules (tiết kiệm tài nguyên)
        rule_reports = await _run_sequential(rules, expected_list, _make_agents(), model_dir)
    else:
        # Song song: mỗi task tạo agents riêng (tránh race condition)
        rule_reports = await _run_parallel(rules, expected_list, _make_agents, concurrency, model_dir)

    pipeline_duration = time.monotonic() - pipeline_start
    return FinalReport(
        model_file=model_path,
        total_rules=len(rules),
        results=rule_reports,
        total_duration_seconds=round(pipeline_duration, 2),
    )


async def _run_sequential(rules, expected_list, agents, model_dir: str = "") -> list[RuleReport]:
    """Chạy tuần tự — 1 bộ agents dùng lại cho mọi rules."""
    rule_reports = []

    for rule in rules:
        logger.info(f"[{rule.rule_id}] Bắt đầu xử lý: {rule.description[:60]}...")
        test_cases = _find_test_cases(expected_list, rule.rule_id)

        report = await _process_rule(rule=rule, test_cases=test_cases, agents=agents, model_dir=model_dir)
        rule_reports.append(report)
        logger.info(f"[{rule.rule_id}] Kết quả: {report.status}")

    return rule_reports


async def _run_parallel(rules, expected_list, make_agents_fn, concurrency: int, model_dir: str = "") -> list[RuleReport]:
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
            logger.info(f"[{rule.rule_id}] Bắt đầu xử lý (parallel): {rule.description[:60]}...")
            try:
                # Mỗi task tạo agents riêng — agent Agno có internal state
                agents = make_agents_fn()
                report = await _process_rule(rule=rule, test_cases=test_cases, agents=agents, model_dir=model_dir)
            except Exception as e:
                # Per-rule isolation: catch unexpected errors, không crash toàn bộ gather
                logger.error(f"[{rule.rule_id}] Unexpected error in parallel task: {e}")
                validation = ValidationResult(
                    rule_id=rule.rule_id,
                    status=ValidationStatus.SCHEMA_ERROR,
                    stderr=f"Parallel task error: {e}",
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


async def _process_rule(rule, test_cases: list[TestCase], agents, model_dir: str = "") -> RuleReport:
    """Xử lý 1 rule qua pipeline 6 agents với retry logic + timing."""
    agent0, agent1, agent2, agent3, agent4, agent5 = agents
    retry = RetryManager(
        max_retries_agent4=settings.MAX_RETRY_AGENT4,
        max_retries_agent5=settings.MAX_RETRY_AGENT5,
    )
    steps: list[PipelineStep] = []
    rule_start = time.monotonic()

    try:
        # ── Agent 0: Parse rule text ──────────────────────
        t0 = time.monotonic()
        response0 = await agent0.arun(rule.description)
        parsed_rule = _extract_content(response0, "Agent 0", ParsedRule)
        parsed_rule.rule_id = rule.rule_id
        steps.append(_make_step("Agent 0 (Rule Analyzer)", t0, output_summary=f"block_keyword={parsed_rule.block_keyword}"))
        logger.debug(f"[{rule.rule_id}] Agent 0: block_keyword={parsed_rule.block_keyword}")

        # ── Input validation (non-blocking warnings, blocking errors) ──
        if model_dir:
            validation_msgs = validate_rule_input(parsed_rule, model_dir)
            if has_blocking_errors(validation_msgs):
                raise ValueError(
                    f"Input validation failed: {'; '.join(m for m in validation_msgs if m.startswith('ERROR:'))}"
                )

        # ── Agent 1: Search block dictionary ─────────────
        t1 = time.monotonic()
        response1 = await agent1.arun(
            f"block_keyword: {parsed_rule.block_keyword}\n"
            f"config_name: {parsed_rule.config_name}"
        )
        block_data = _extract_content(response1, "Agent 1", BlockMappingData)
        steps.append(_make_step("Agent 1 (Data Reader)", t1, output_summary=f"name_xml={block_data.name_xml}"))
        logger.debug(f"[{rule.rule_id}] Agent 1: name_xml={block_data.name_xml}")

        # ── Agent 2: Generate check code ─────────────────
        t2 = time.monotonic()
        await agent2.arun(
            f"rule_id: {rule.rule_id}\n"
            f"block: name_xml={block_data.name_xml}, name_ui={block_data.name_ui}\n"
            f"config_name: {parsed_rule.config_name}\n"
            f"condition: {parsed_rule.condition}\n"
            f"expected_value: {parsed_rule.expected_value}\n"
            f"config_map_analysis: {block_data.config_map_analysis}\n"
            f"output_filename: check_rule_{rule.rule_id}.py"
        )
        code_file = str(settings.GENERATED_CHECKS_DIR / f"check_rule_{rule.rule_id}.py")
        steps.append(_make_step("Agent 2 (Code Generator)", t2, output_summary=f"file={code_file}"))
        logger.debug(f"[{rule.rule_id}] Agent 2: generated {code_file}")

        # ── Verify file tồn tại sau Agent 2 ──────────────
        if not Path(code_file).exists():
            raise FileNotFoundError(
                f"Agent 2 không tạo được file expected: {code_file}. "
                f"Kiểm tra Agent 2 có gọi write_python_file() đúng filename không."
            )

        # ── Agent 3: Validate → retry loop ────────────────
        t3 = time.monotonic()
        validation = await asyncio.to_thread(_run_validation, agent3, code_file, test_cases, rule.rule_id)
        steps.append(_make_step(
            "Agent 3 (Validator)", t3,
            status="success" if validation.status == ValidationStatus.PASS else "error",
            output_summary=f"status={validation.status.value}, passed={validation.test_cases_passed}/{validation.test_cases_total}",
        ))

        while retry.can_retry(validation):
            # Ghi lại lỗi trước khi retry (để agent biết đã thử gì)
            _record_error(retry, validation)

            next_agent, context = route_validation(
                validation,
                block_data,
                retry_counts=retry.counts,
                max_retries=retry.max_retries,
                error_history=retry.get_error_history(),
                retry_manager=retry,
            )

            if next_agent == "agent4":
                retry.increment("agent4")
                logger.info(f"[{rule.rule_id}] Agent 4 fix (attempt {retry.counts['agent4']}/{retry.max_retries['agent4']})")
                tr = time.monotonic()
                await agent4.arun(context)
                steps.append(_make_step(f"Agent 4 (Bug Fixer) #{retry.counts['agent4']}", tr))

            elif next_agent == "agent5":
                retry.increment("agent5")
                logger.info(f"[{rule.rule_id}] Agent 5 inspect (attempt {retry.counts['agent5']}/{retry.max_retries['agent5']})")
                # Reset loop detector trước khi Agent 5 dùng shared XmlToolkit
                _reset_xml_toolkit(agents)
                tr = time.monotonic()
                await agent5.arun(context)
                steps.append(_make_step(f"Agent 5 (Inspector) #{retry.counts['agent5']}", tr))

            else:
                break

            # Re-validate sau khi fix/inspect
            tv = time.monotonic()
            validation = await asyncio.to_thread(_run_validation, agent3, code_file, test_cases, rule.rule_id)
            steps.append(_make_step(
                f"Agent 3 (Re-validate)", tv,
                status="success" if validation.status == ValidationStatus.PASS else "error",
                output_summary=f"status={validation.status.value}",
            ))

        # Nếu vẫn fail sau hết retry → đánh dấu FAILED
        if validation.status == ValidationStatus.CODE_ERROR:
            validation.status = ValidationStatus.FAILED_CODE_ERROR
        elif validation.status == ValidationStatus.WRONG_RESULT:
            validation.status = ValidationStatus.FAILED_WRONG_RESULT
        elif validation.status == ValidationStatus.PARTIAL_PASS:
            validation.status = ValidationStatus.FAILED_PARTIAL_PASS

    except Exception as e:
        logger.error(f"[{rule.rule_id}] Pipeline error: {e}")
        validation = ValidationResult(
            rule_id=rule.rule_id,
            status=ValidationStatus.SCHEMA_ERROR,
            stderr=str(e),
            code_file_path="",
        )

    rule_duration = time.monotonic() - rule_start
    report = RuleReport.from_validation(rule.rule_id, validation, retry.get_trace())
    report.pipeline_steps = steps
    report.rule_duration_seconds = round(rule_duration, 2)
    return report


def _reset_xml_toolkit(agents) -> None:
    """Reset loop detector trên shared XmlToolkit khi chuyển agent."""
    # agents[2] = Agent 2, agents[5] = Agent 5 — cả hai dùng cùng XmlToolkit
    for agent in (agents[2], agents[5]):
        if hasattr(agent, "tools"):
            for tool in agent.tools:
                if hasattr(tool, "reset_loop_detector"):
                    tool.reset_loop_detector()
                    return  # Shared toolkit — reset 1 lần là đủ


def _run_validation(
    agent3: Validator, code_file: str, test_cases: list[TestCase], rule_id: str,
) -> ValidationResult:
    """Chạy Agent 3 validate — pure Python, không LLM."""
    return agent3.validate(code_file, test_cases, rule_id)


def _extract_content(response, agent_name: str, expected_type: type):
    """Extract .content từ RunResponse với null-check và type validation.

    Args:
        response: RunResponse từ agent.arun().
        agent_name: Tên agent (cho error message).
        expected_type: Pydantic model class expected (VD: ParsedRule).
    """
    content = response.content
    if content is None:
        raise ValueError(
            f"{agent_name} trả về content=None (expected {expected_type.__name__}). "
            f"LLM có thể đã fail structured output. Kiểm tra response_model configuration."
        )
    if not isinstance(content, expected_type):
        raise TypeError(
            f"{agent_name} trả về {type(content).__name__} thay vì {expected_type.__name__}. "
            f"Structured output có thể đã fail — content: {str(content)[:300]}"
        )
    return content


def _record_error(retry: RetryManager, validation: ValidationResult) -> None:
    """Ghi nhận lỗi hiện tại vào error history trước khi retry."""
    tc_info = f" [test_case={validation.failed_test_case}]" if validation.failed_test_case else ""
    error_cat = classify_error(validation)

    if validation.status == ValidationStatus.CODE_ERROR:
        stderr_short = (validation.stderr or "")[:300]
        retry.add_error(f"CODE_ERROR({error_cat}){tc_info}: {stderr_short}", category=error_cat)
    elif validation.status in (ValidationStatus.WRONG_RESULT, ValidationStatus.PARTIAL_PASS):
        actual_short = json.dumps(validation.actual_result)[:200] if validation.actual_result else "None"
        expected_short = json.dumps(validation.expected_result)[:200] if validation.expected_result else "None"
        pass_info = f" [{validation.test_cases_passed}/{validation.test_cases_total} passed]"
        retry.add_error(
            f"{validation.status.value}({error_cat}){tc_info}{pass_info}: actual={actual_short}, expected={expected_short}",
            category=error_cat,
        )


def _make_step(
    agent_name: str, start_time: float,
    status: str = "success", output_summary: str = "",
) -> PipelineStep:
    """Tạo PipelineStep từ start_time (monotonic)."""
    duration = time.monotonic() - start_time
    return PipelineStep(
        agent_name=agent_name,
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
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
