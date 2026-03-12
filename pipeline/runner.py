"""
Pipeline chính: Điều phối 6 agents chạy tuần tự theo từng rule.
"""

import json
import logging
from pathlib import Path

from schemas.validation_schemas import ValidationResult, ValidationStatus
from schemas.report_schemas import FinalReport, RuleReport
from schemas.rule_schemas import RuleInput

from agents.agent0_rule_analyzer import create_agent0
from agents.agent1_data_reader import create_agent1
from agents.agent2_code_generator import create_agent2
from agents.agent3_validator import create_agent3
from agents.agent4_bug_fixer import create_agent4
from agents.agent5_inspector import create_agent5

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
    """Chạy toàn bộ pipeline cho tất cả rules trong rules.json."""

    # ── Chuẩn bị ──────────────────────────────────────────
    model_dir = extract_slx(model_path)  # Trả về thư mục gốc chứa XML tree
    rules = [RuleInput(**r) for r in json.loads(Path(rules_path).read_text(encoding="utf-8"))]
    expected_list = json.loads(Path(expected_path).read_text(encoding="utf-8"))

    # ── Tạo agents (1 lần, dùng lại cho mọi rules) ────────
    agent0 = create_agent0()
    agent1 = create_agent1(blocks_path)
    agent2 = create_agent2(model_dir)
    agent3 = create_agent3(model_dir)
    agent4 = create_agent4()
    agent5 = create_agent5(model_dir)

    # ── Chạy từng rule ────────────────────────────────────
    rule_reports: list[RuleReport] = []

    for rule in rules:
        logger.info(f"[{rule.rule_id}] Bắt đầu xử lý: {rule.description[:60]}...")
        expected = _find_expected(expected_list, rule.rule_id)

        report = await _process_rule(
            rule=rule,
            expected=expected,
            agents=(agent0, agent1, agent2, agent3, agent4, agent5),
        )
        rule_reports.append(report)
        logger.info(f"[{rule.rule_id}] Kết quả: {report.status}")

    return FinalReport(
        model_file=model_path,
        total_rules=len(rules),
        results=rule_reports,
    )


async def _process_rule(rule, expected, agents) -> RuleReport:
    """Xử lý 1 rule qua pipeline 6 agents với retry logic."""
    agent0, agent1, agent2, agent3, agent4, agent5 = agents
    retry = RetryManager(max_retries=settings.MAX_RETRY_AGENT4)

    try:
        # ── Agent 0: Parse rule text ──────────────────────
        parsed_rule = await agent0.arun(rule.description)
        parsed_rule.rule_id = rule.rule_id
        logger.debug(f"[{rule.rule_id}] Agent 0: block_keyword={parsed_rule.block_keyword}")

        # ── Agent 1: Search block dictionary ─────────────
        block_data = await agent1.arun(
            f"block_keyword: {parsed_rule.block_keyword}\n"
            f"config_name: {parsed_rule.config_name}"
        )
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

        # ── Agent 3 → retry loop ──────────────────────────
        validation = await agent3.arun(
            f"file_path: {code_file}\n"
            f"expected_json: {json.dumps(expected)}"
        )
        validation.rule_id = rule.rule_id
        validation.code_file_path = code_file

        while retry.can_retry(validation):
            next_agent, context = route_validation(validation, block_data)

            if next_agent == "agent4":
                retry.increment("agent4")
                logger.info(f"[{rule.rule_id}] Agent 4 fix (attempt {retry.counts['agent4']})")
                await agent4.arun(context)

            elif next_agent == "agent5":
                retry.increment("agent5")
                logger.info(f"[{rule.rule_id}] Agent 5 inspect (attempt {retry.counts['agent5']})")
                await agent5.arun(context)

            else:
                break

            # Re-validate sau khi fix/inspect
            validation = await agent3.arun(
                f"file_path: {code_file}\n"
                f"expected_json: {json.dumps(expected)}"
            )
            validation.rule_id = rule.rule_id
            validation.code_file_path = code_file

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


def _find_expected(expected_list: list, rule_id: str) -> dict:
    for item in expected_list:
        if item.get("rule_id") == rule_id:
            return item
    return {}
