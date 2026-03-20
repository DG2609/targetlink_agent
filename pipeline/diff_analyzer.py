"""
Pure Python replacement cho Agent 1.5 (Diff Analyzer).

Thay vì dùng LLM để interpret diff results, trực tiếp:
  1. Filter config_changes by config_name + block_type
  2. Pick best match (priority: InstanceData > direct_P > MaskValueString > attribute)
  3. Generalize xpath → pattern cho tất cả blocks cùng type
  4. Trả ConfigDiscovery (không tốn LLM token)
"""

import logging
import re

from schemas.diff_schemas import ConfigChange, ConfigDiscovery, ModelDiff

logger = logging.getLogger(__name__)

# Priority: location_type → ưu tiên khi có nhiều matches
_LOCATION_PRIORITY = {
    "InstanceData": 0,
    "direct_P": 1,
    "MaskValueString": 2,
    "attribute": 3,
}


def _infer_value_format(old_value: str | None, new_value: str | None) -> str:
    """Infer format từ old/new values."""
    sample = new_value or old_value or ""
    if not sample:
        return "unknown"
    if sample.lower() in ("on", "off"):
        return "on/off"
    if sample.isdigit() or (sample.startswith("-") and sample[1:].isdigit()):
        return "integer"
    try:
        float(sample)
        return "float"
    except ValueError:
        pass
    if sample.startswith("fixdt("):
        return "fixdt(...)"
    if sample.startswith("Inherit"):
        return "Inherit:*"
    return "string"


def _generalize_xpath(xpath: str, block_type: str, mask_type: str) -> str:
    """Generalize xpath: thay SID cụ thể bằng BlockType pattern.

    VD: ".//Block[@SID='5']/P[@Name='Gain']"
    → ".//Block[@BlockType='Gain']/P[@Name='Gain']"
    """
    # Replace SID filter with BlockType filter
    result = re.sub(
        r"@SID='[^']*'",
        f"@BlockType='{block_type}'",
        xpath,
    )
    # If mask_type is present, add MaskType predicate for specificity
    if mask_type and "@MaskType" not in result:
        result = result.replace(
            f"@BlockType='{block_type}'",
            f"@BlockType='{block_type}' and @MaskType='{mask_type}'",
        )
    return result


def analyze_diff_for_config(
    diff_result: ModelDiff,
    block_type: str,
    config_name: str,
    model_dir: str = "",
) -> ConfigDiscovery | None:
    """Phân tích diff results → ConfigDiscovery cho 1 config cụ thể.

    Pure Python — không LLM. Filter, pick best match, generalize xpath.

    Args:
        diff_result: ModelDiff từ model_differ.
        block_type: BlockType hoặc MaskType cần filter (từ Agent 1 / BlockMappingData.name_xml).
        config_name: Config cần tìm (từ ParsedRule.config_name).
        model_dir: Model directory (unused in current implementation, reserved).

    Returns:
        ConfigDiscovery nếu tìm thấy matching config change.
        None nếu không tìm thấy.
    """
    if not diff_result or not diff_result.config_changes:
        return None

    # ── Step 1: Filter by config_name ──
    matches: list[ConfigChange] = []
    for change in diff_result.config_changes:
        if change.config_name == config_name:
            matches.append(change)

    if not matches:
        logger.debug(f"Diff: không tìm thấy config_change cho '{config_name}'")
        return None

    # ── Step 2: Filter by block_type (nếu có) ──
    if block_type:
        typed_matches = [
            m for m in matches
            if m.block_type == block_type or m.mask_type == block_type
        ]
        if typed_matches:
            matches = typed_matches
        # Nếu không match block_type → dùng tất cả matches (best effort)

    # ── Step 3: Pick best match (priority by location_type) ──
    matches.sort(
        key=lambda m: _LOCATION_PRIORITY.get(m.location_type, 99)
    )
    best = matches[0]

    # ── Step 4: Generalize xpath ──
    effective_block_type = best.block_type
    effective_mask_type = best.mask_type
    xpath_pattern = _generalize_xpath(best.xpath, effective_block_type, effective_mask_type)

    # ── Step 5: Build notes ──
    unique_files = {m.system_file for m in matches}
    unique_blocks = {m.block_name for m in matches}
    notes_parts = [
        f"Found {len(matches)} config changes across {len(unique_blocks)} blocks in {len(unique_files)} files.",
    ]
    if best.mask_type:
        notes_parts.append(
            f"Block uses MaskType='{best.mask_type}' — config may be in InstanceData or MaskValueString."
        )
    if best.default_value:
        notes_parts.append(f"Default value from bddefaults: '{best.default_value}'.")

    logger.info(
        f"Diff analysis: config='{config_name}', location={best.location_type}, "
        f"xpath={xpath_pattern}, {len(matches)} matches"
    )

    return ConfigDiscovery(
        block_type=effective_block_type,
        mask_type=effective_mask_type,
        config_name=config_name,
        location_type=best.location_type,
        xpath_pattern=xpath_pattern,
        default_value=best.default_value,
        value_format=_infer_value_format(best.old_value, best.new_value),
        notes=" ".join(notes_parts),
    )
