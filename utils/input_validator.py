"""
Validate ParsedRule input trước khi chạy pipeline.
Kiểm tra: block_keyword có tồn tại trong model không, config_name có hợp lệ không.
Non-blocking: trả về warnings (log) + errors (ngăn pipeline chạy).
"""

import logging
from pathlib import Path

from schemas.rule_schemas import ParsedRule
from utils.defaults_parser import parse_bddefaults

logger = logging.getLogger(__name__)


def validate_rule_input(rule: ParsedRule, model_dir: str) -> list[str]:
    """Validate rule input trước khi pipeline xử lý.

    Args:
        rule: ParsedRule đã parse từ Agent 0.
        model_dir: Đường dẫn tới model tree (sau extract .slx).

    Returns:
        List warning/error messages. Rỗng = OK.
        Messages bắt đầu bằng "ERROR:" sẽ ngăn pipeline chạy.
        Messages bắt đầu bằng "WARNING:" chỉ log, không ngăn.
    """
    messages: list[str] = []

    # Check 1: model_dir tồn tại
    systems_dir = Path(model_dir) / "simulink" / "systems"
    if not systems_dir.exists():
        messages.append(f"ERROR: Thư mục systems không tồn tại: {systems_dir}")

    # Check 2: Có file system_*.xml nào không
    system_files: list = []
    if systems_dir.exists():
        system_files = list(systems_dir.glob("system_*.xml"))
        if not system_files:
            messages.append(f"ERROR: Không tìm thấy file system_*.xml trong {systems_dir}")

    # Check 3: block_keyword có map tới BlockType/MaskType thực tế không
    # Skip check nếu block_keyword rỗng (config-only rule — hợp lệ)
    # Skip check nếu system_files chưa có (check 1/2 đã fail)
    if system_files and rule.block_keyword and rule.block_keyword.strip():
        from lxml import etree

        found_block_types: set[str] = set()
        found_mask_types: set[str] = set()

        for sf in system_files:
            try:
                tree = etree.parse(str(sf))
                root = tree.getroot()
                for block in root.findall("Block"):
                    bt = block.get("BlockType", "")
                    if bt:
                        found_block_types.add(bt)
                    for p in block.findall("P"):
                        if p.get("Name") == "MaskType":
                            mt = (p.text or "").strip()
                            if mt:
                                found_mask_types.add(mt)
            except Exception as e:
                logger.warning(f"Không parse được {sf.name}: {e}")
                continue

        all_types = found_block_types | found_mask_types
        keyword = rule.block_keyword.lower()

        # Tìm block type nào match keyword
        matched = [t for t in all_types if keyword in t.lower()]
        if not matched:
            messages.append(
                f"WARNING: block_keyword '{rule.block_keyword}' không khớp BlockType/MaskType nào "
                f"trong model. Có thể Agent 1 sẽ tìm được qua blocks.json."
            )

    # Check 4: config_name có tồn tại trong bddefaults.xml hoặc block XML không
    defaults_map = parse_bddefaults(model_dir)
    config_found = False

    for bt, configs in defaults_map.items():
        if rule.config_name in configs:
            config_found = True
            break

    if not config_found:
        messages.append(
            f"WARNING: config_name '{rule.config_name}' không tìm thấy trong bddefaults.xml. "
            f"Có thể là config explicit-only hoặc InstanceData config."
        )

    # Check 5: compound logic consistency
    if rule.compound_logic != "SINGLE" and not rule.additional_configs:
        messages.append(
            f"WARNING: compound_logic='{rule.compound_logic}' nhưng additional_configs rỗng. "
            f"Sẽ fallback về SINGLE config check."
        )

    # Log warnings
    for msg in messages:
        if msg.startswith("ERROR:"):
            logger.error(f"[{rule.rule_id}] {msg}")
        else:
            logger.warning(f"[{rule.rule_id}] {msg}")

    return messages


def has_blocking_errors(messages: list[str]) -> bool:
    """Kiểm tra xem có lỗi nào ngăn pipeline chạy không."""
    return any(msg.startswith("ERROR:") for msg in messages)
