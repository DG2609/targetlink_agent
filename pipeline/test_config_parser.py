"""
Parse test_config.json → 4 file paths cần thiết cho run_pipeline().

test_config.json là consolidated input format — user chỉ cần 1 file thay vì 4.
Parser tạo temp files cho rules.json và expected_results.json.
"""

import atexit
import json
import logging
import tempfile
from pathlib import Path

from schemas.test_config_schemas import TestConfig

# Track temp files for cleanup at process exit
_temp_files: list[str] = []


def _cleanup_temp_files() -> None:
    """Remove temp files created by parse_test_config at process exit."""
    for f in _temp_files:
        try:
            Path(f).unlink(missing_ok=True)
        except OSError:
            pass
    _temp_files.clear()


atexit.register(_cleanup_temp_files)

logger = logging.getLogger(__name__)


def parse_test_config(config_path: str) -> dict:
    """Parse test_config.json → dict chứa tất cả params cho pipeline.

    Args:
        config_path: Path tới test_config.json.

    Returns:
        Dict với keys: model, blocks, rules, expected, model_before (optional).
        'rules' và 'expected' trỏ tới temp files được tạo từ config.

    Raises:
        FileNotFoundError: Nếu config_path không tồn tại.
        ValueError: Nếu config không hợp lệ (thiếu rules, thiếu test_cases, etc.).
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"test_config.json không tồn tại: {config_path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    config = TestConfig(**raw)

    if not config.rules:
        raise ValueError("test_config.json phải có ít nhất 1 rule trong 'rules'")

    # ── Extract unique model_path (preserve insertion order) ──
    model_paths = list(dict.fromkeys(
        tc.model_path for rule in config.rules for tc in rule.test_cases
    ))

    if not model_paths:
        raise ValueError("test_config.json: không tìm thấy model_path trong test_cases")

    if len(model_paths) > 1:
        logger.warning(
            f"test_config.json có {len(model_paths)} model paths khác nhau. "
            f"Pipeline sẽ dùng model đầu tiên: {model_paths[0]}"
        )

    model_path = model_paths[0]

    # ── Build rules.json ──
    rules_list = [
        {"rule_id": r.rule_id, "description": r.description}
        for r in config.rules
    ]

    # ── Build expected_results.json ──
    expected_list = []
    for rule in config.rules:
        expected_list.append({
            "rule_id": rule.rule_id,
            "test_cases": [
                {
                    "model_path": tc.model_path,
                    "expected_total_blocks": tc.expected_total_blocks,
                    "expected_pass": tc.expected_pass,
                    "expected_fail": tc.expected_fail,
                }
                for tc in rule.test_cases
            ],
        })

    # ── Write temp files ──
    rules_tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="_rules.json", delete=False, encoding="utf-8",
    )
    json.dump(rules_list, rules_tmp, indent=2, ensure_ascii=False)
    rules_tmp.close()

    expected_tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="_expected.json", delete=False, encoding="utf-8",
    )
    json.dump(expected_list, expected_tmp, indent=2, ensure_ascii=False)
    expected_tmp.close()

    # Register temp files for cleanup at process exit
    _temp_files.extend([rules_tmp.name, expected_tmp.name])

    logger.info(
        f"test_config parsed: {len(config.rules)} rules, "
        f"model={model_path}, blocks={config.blocks_path}"
    )

    return {
        "model": model_path,
        "blocks": config.blocks_path,
        "rules": rules_tmp.name,
        "expected": expected_tmp.name,
        "model_before": config.model_before,
    }
