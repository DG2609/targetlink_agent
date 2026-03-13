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
from pathlib import Path
from lxml import etree

from schemas.validation_schemas import ValidationResult, ValidationStatus
from schemas.report_schemas import FinalReport, RuleReport
from schemas.rule_schemas import RuleInput

from agents.agent0_rule_analyzer import create_agent0
from agents.agent1_data_reader import create_agent1
from agents.agent2_code_generator import create_agent2
from agents.agent3_validator import create_agent3
from agents.agent4_bug_fixer import create_agent4
from agents.agent5_inspector import create_agent5

from tools.xml_tools import XmlToolkit

from pipeline.router import route_validation
from pipeline.retry import RetryManager

from utils.slx_extractor import extract_slx
from config import settings

logger = logging.getLogger(__name__)


async def run_pipeline(
    model_path: str,
    blocks_path: str,
    rules_path: str,
    expected_path: str,
) -> FinalReport:
    """Chạy toàn bộ pipeline cho tất cả rules — song song nếu concurrency > 1."""

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
            create_agent3(model_dir),
            create_agent4(),
            create_agent5(xml_toolkit=xml_toolkit, output_dir=output_dir),
        )

    # ── Xử lý rules ──────────────────────────────────────
    concurrency = max(1, settings.MAX_CONCURRENT_RULES)

    if concurrency == 1:
        # Tuần tự: dùng 1 bộ agents cho mọi rules (tiết kiệm tài nguyên)
        rule_reports = await _run_sequential(rules, expected_list, _make_agents())
    else:
        # Song song: mỗi task tạo agents riêng (tránh race condition)
        rule_reports = await _run_parallel(rules, expected_list, _make_agents, concurrency)

    return FinalReport(
        model_file=model_path,
        total_rules=len(rules),
        results=rule_reports,
    )


async def _run_sequential(rules, expected_list, agents) -> list[RuleReport]:
    """Chạy tuần tự — 1 bộ agents dùng lại cho mọi rules."""
    rule_reports = []

    for rule in rules:
        logger.info(f"[{rule.rule_id}] Bắt đầu xử lý: {rule.description[:60]}...")
        expected = _find_expected(expected_list, rule.rule_id)

        report = await _process_rule(rule=rule, expected=expected, agents=agents)
        rule_reports.append(report)
        logger.info(f"[{rule.rule_id}] Kết quả: {report.status}")

    return rule_reports


async def _run_parallel(rules, expected_list, make_agents_fn, concurrency: int) -> list[RuleReport]:
    """Chạy song song với semaphore giới hạn concurrency."""
    semaphore = asyncio.Semaphore(concurrency)
    logger.info(f"Parallel mode: {concurrency} rules đồng thời, tổng {len(rules)} rules")

    async def _process_with_limit(rule, expected):
        async with semaphore:
            logger.info(f"[{rule.rule_id}] Bắt đầu xử lý (parallel): {rule.description[:60]}...")
            # Mỗi task tạo agents riêng — agent Agno có internal state
            agents = make_agents_fn()
            report = await _process_rule(rule=rule, expected=expected, agents=agents)
            logger.info(f"[{rule.rule_id}] Kết quả: {report.status}")
            return report

    tasks = [
        _process_with_limit(rule, _find_expected(expected_list, rule.rule_id))
        for rule in rules
    ]
    return list(await asyncio.gather(*tasks))


async def _process_rule(rule, expected, agents) -> RuleReport:
    """Xử lý 1 rule qua pipeline 6 agents với retry logic."""
    agent0, agent1, agent2, agent3, agent4, agent5 = agents
    retry = RetryManager(
        max_retries_agent4=settings.MAX_RETRY_AGENT4,
        max_retries_agent5=settings.MAX_RETRY_AGENT5,
    )

    try:
        # ── Agent 0: Parse rule text ──────────────────────
        response0 = await agent0.arun(rule.description)
        parsed_rule = _extract_content(response0, "Agent 0", "ParsedRule")
        parsed_rule.rule_id = rule.rule_id
        logger.debug(f"[{rule.rule_id}] Agent 0: block_keyword={parsed_rule.block_keyword}")

        # ── Agent 1: Search block dictionary ─────────────
        response1 = await agent1.arun(
            f"block_keyword: {parsed_rule.block_keyword}\n"
            f"config_name: {parsed_rule.config_name}"
        )
        block_data = _extract_content(response1, "Agent 1", "BlockMappingData")
        logger.debug(f"[{rule.rule_id}] Agent 1: name_xml={block_data.name_xml}")

        # ── Agent 2: Generate check code ─────────────────
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
        logger.debug(f"[{rule.rule_id}] Agent 2: generated {code_file}")

        # ── Verify file tồn tại sau Agent 2 ──────────────
        if not Path(code_file).exists():
            raise FileNotFoundError(
                f"Agent 2 không tạo được file expected: {code_file}. "
                f"Kiểm tra Agent 2 có gọi write_python_file() đúng filename không."
            )

        # ── Agent 3: Validate → retry loop ────────────────
        validation = await _run_validation(agent3, code_file, expected, rule.rule_id)

        while retry.can_retry(validation):
            # Ghi lại lỗi trước khi retry (để agent biết đã thử gì)
            _record_error(retry, validation)

            next_agent, context = route_validation(
                validation,
                block_data,
                retry_counts=retry.counts,
                max_retries=retry.max_retries,
                error_history=retry.get_error_history(),
            )

            if next_agent == "agent4":
                retry.increment("agent4")
                logger.info(f"[{rule.rule_id}] Agent 4 fix (attempt {retry.counts['agent4']}/{retry.max_retries['agent4']})")
                await agent4.arun(context)

            elif next_agent == "agent5":
                retry.increment("agent5")
                logger.info(f"[{rule.rule_id}] Agent 5 inspect (attempt {retry.counts['agent5']}/{retry.max_retries['agent5']})")
                await agent5.arun(context)

            else:
                break

            # Re-validate sau khi fix/inspect
            validation = await _run_validation(agent3, code_file, expected, rule.rule_id)

        # Nếu vẫn fail sau hết retry → đánh dấu FAILED
        if validation.status == ValidationStatus.CODE_ERROR:
            validation.status = ValidationStatus.FAILED_CODE_ERROR
        elif validation.status == ValidationStatus.WRONG_RESULT:
            validation.status = ValidationStatus.FAILED_WRONG_RESULT

    except Exception as e:
        logger.error(f"[{rule.rule_id}] Pipeline error: {e}")
        validation = ValidationResult(
            rule_id=rule.rule_id,
            status=ValidationStatus.SCHEMA_ERROR,
            stderr=str(e),
            code_file_path="",
        )

    return RuleReport.from_validation(rule.rule_id, validation, retry.get_trace())


async def _run_validation(agent3, code_file: str, expected: dict, rule_id: str) -> ValidationResult:
    """Chạy Agent 3 validate và extract ValidationResult từ RunResponse."""
    response3 = await agent3.arun(
        f"file_path: {code_file}\n"
        f"expected_json: {json.dumps(expected)}"
    )
    validation = _extract_content(response3, "Agent 3", "ValidationResult")
    validation.rule_id = rule_id
    validation.code_file_path = code_file
    return validation


def _extract_content(response, agent_name: str, expected_type: str):
    """Extract .content từ RunResponse với null-check."""
    content = response.content
    if content is None:
        raise ValueError(
            f"{agent_name} trả về content=None (expected {expected_type}). "
            f"LLM có thể đã fail structured output. Kiểm tra response_model configuration."
        )
    return content


def _record_error(retry: RetryManager, validation: ValidationResult) -> None:
    """Ghi nhận lỗi hiện tại vào error history trước khi retry."""
    if validation.status == ValidationStatus.CODE_ERROR:
        stderr_short = (validation.stderr or "")[:300]
        retry.add_error(f"CODE_ERROR: {stderr_short}")
    elif validation.status == ValidationStatus.WRONG_RESULT:
        actual_short = json.dumps(validation.actual_result)[:200] if validation.actual_result else "None"
        expected_short = json.dumps(validation.expected_result)[:200] if validation.expected_result else "None"
        retry.add_error(f"WRONG_RESULT: actual={actual_short}, expected={expected_short}")


def _find_expected(expected_list: list, rule_id: str) -> dict:
    for item in expected_list:
        if item.get("rule_id") == rule_id:
            return item
    return {}
