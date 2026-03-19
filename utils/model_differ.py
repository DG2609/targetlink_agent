"""
So sánh 2 model TargetLink (.slx) sau khi unzip → tìm chính xác config nào thay đổi ở đâu.

Workflow:
  1. User sửa 1 config trong MATLAB → save 2 phiên bản .slx
  2. Hệ thống unzip cả 2 → 2 thư mục XML
  3. ModelDiffer diff 2 thư mục → trả ModelDiff chứa chính xác:
     - Block nào thay đổi (match by SID)
     - Config nào thay đổi (direct_P, InstanceData, MaskValueString, attribute)
     - XPath tới element thay đổi
     - Giá trị cũ/mới

Giải quyết vấn đề: Agent 2 không cần đoán config nằm ở đâu trong XML nữa.
"""

import logging
import re
from pathlib import Path

from lxml import etree

from schemas.diff_schemas import BlockChange, ConfigChange, ModelDiff
from utils.slx_extractor import extract_slx
from utils.defaults_parser import get_default_value

logger = logging.getLogger(__name__)

# Configs visual/positional — bỏ qua khi diff (không liên quan rule checking)
_IGNORE_CONFIGS = frozenset({
    "Position", "ZOrder", "Ports", "Location", "Open", "Port",
    "BlockMirror", "NamePlacement", "ShowName", "HideAutomaticName",
    "IconDisplay", "MaskIconFrame", "MaskIconOpaque", "MaskIconRotate",
    "DropShadow", "Orientation", "ForegroundColor", "BackgroundColor",
    "FontName", "FontSize", "FontWeight", "FontAngle",
})


class ModelDiffer:
    """So sánh 2 model TargetLink directories (đã unzip).

    Tìm tất cả thay đổi trong simulink/systems/system_*.xml files.
    Match blocks by SID (stable identifier trong Simulink).
    So sánh 4 layers: direct <P>, InstanceData, MaskValueString, attributes.
    """

    def __init__(self, before_dir: str, after_dir: str):
        self.before_dir = before_dir
        self.after_dir = after_dir

    def diff(self) -> ModelDiff:
        """Main entry: diff 2 model directories → ModelDiff."""
        before_files = self._list_system_files(self.before_dir)
        after_files = self._list_system_files(self.after_dir)

        before_set = set(before_files)
        after_set = set(after_files)

        files_only_before = sorted(before_set - after_set)
        files_only_after = sorted(after_set - before_set)
        common_files = sorted(before_set & after_set)

        all_block_changes: list[BlockChange] = []
        all_config_changes: list[ConfigChange] = []

        # Diff common files
        for system_file in common_files:
            try:
                before_tree = etree.parse(str(Path(self.before_dir) / system_file))
                after_tree = etree.parse(str(Path(self.after_dir) / system_file))
            except Exception as e:
                logger.warning(f"Lỗi parse {system_file}: {e}")
                continue

            block_changes = self._diff_file(
                before_tree.getroot(), after_tree.getroot(), system_file,
            )
            all_block_changes.extend(block_changes)
            for bc in block_changes:
                all_config_changes.extend(bc.config_changes)

        # Blocks trong files chỉ có ở 1 bên
        for system_file in files_only_after:
            block_changes = self._collect_blocks_as_added(system_file)
            all_block_changes.extend(block_changes)

        for system_file in files_only_before:
            block_changes = self._collect_blocks_as_removed(system_file)
            all_block_changes.extend(block_changes)

        result = ModelDiff(
            model_before=self.before_dir,
            model_after=self.after_dir,
            block_changes=all_block_changes,
            config_changes=all_config_changes,
            files_only_before=files_only_before,
            files_only_after=files_only_after,
        )

        # Enrich defaults từ bddefaults.xml (after model) — chỉ standard Simulink blocks
        _enrich_defaults(result, self.after_dir)

        return result

    # ──────────────────────────────────────────────
    # File listing
    # ──────────────────────────────────────────────

    @staticmethod
    def _list_system_files(model_dir: str) -> list[str]:
        """Liệt kê tất cả system_*.xml files (relative paths)."""
        systems_dir = Path(model_dir) / "simulink" / "systems"
        if not systems_dir.exists():
            return []
        result = []
        for f in sorted(systems_dir.glob("system_*.xml")):
            rel = str(f.relative_to(Path(model_dir))).replace("\\", "/")
            result.append(rel)
        return result

    # ──────────────────────────────────────────────
    # File-level diff
    # ──────────────────────────────────────────────

    def _diff_file(
        self, before_root: etree._Element, after_root: etree._Element, system_file: str,
    ) -> list[BlockChange]:
        """So sánh blocks trong 1 file XML. Match by SID."""
        before_map, after_map, added_sids, removed_sids, common_sids = (
            self._match_blocks_by_sid(before_root, after_root)
        )

        block_changes: list[BlockChange] = []

        # Modified blocks
        for sid in sorted(common_sids):
            before_block = before_map[sid]
            after_block = after_map[sid]
            # Extract mask_type 1 lần per block (tránh iterate <P> nhiều lần)
            mask_type = self._get_mask_type(after_block)
            config_changes = self._diff_block_configs(
                before_block, after_block, system_file, sid, mask_type=mask_type,
            )
            if config_changes:
                block_changes.append(BlockChange(
                    block_sid=sid,
                    block_name=after_block.get("Name", "Unknown"),
                    block_type=after_block.get("BlockType", "Unknown"),
                    mask_type=mask_type,
                    system_file=system_file,
                    change_type="modified",
                    config_changes=config_changes,
                ))

        # Added blocks
        for sid in sorted(added_sids):
            block = after_map[sid]
            block_changes.append(BlockChange(
                block_sid=sid,
                block_name=block.get("Name", "Unknown"),
                block_type=block.get("BlockType", "Unknown"),
                mask_type=self._get_mask_type(block),
                system_file=system_file,
                change_type="added",
            ))

        # Removed blocks
        for sid in sorted(removed_sids):
            block = before_map[sid]
            block_changes.append(BlockChange(
                block_sid=sid,
                block_name=block.get("Name", "Unknown"),
                block_type=block.get("BlockType", "Unknown"),
                mask_type=self._get_mask_type(block),
                system_file=system_file,
                change_type="removed",
            ))

        return block_changes

    @staticmethod
    def _match_blocks_by_sid(
        before_root: etree._Element, after_root: etree._Element,
    ) -> tuple[dict, dict, set, set, set]:
        """Match blocks by SID. Returns (before_map, after_map, added, removed, common)."""
        before_map: dict[str, etree._Element] = {}
        for block in before_root.findall("Block"):
            sid = block.get("SID", "")
            if sid:
                before_map[sid] = block

        after_map: dict[str, etree._Element] = {}
        for block in after_root.findall("Block"):
            sid = block.get("SID", "")
            if sid:
                after_map[sid] = block

        before_sids = set(before_map.keys())
        after_sids = set(after_map.keys())

        return (
            before_map,
            after_map,
            after_sids - before_sids,   # added
            before_sids - after_sids,   # removed
            before_sids & after_sids,   # common
        )

    # ──────────────────────────────────────────────
    # Block-level config diff (4 layers)
    # ──────────────────────────────────────────────

    def _diff_block_configs(
        self,
        before_block: etree._Element,
        after_block: etree._Element,
        system_file: str,
        block_sid: str,
        mask_type: str = "",
    ) -> list[ConfigChange]:
        """So sánh tất cả configs giữa 2 versions của cùng 1 block."""
        block_name = after_block.get("Name", "Unknown")
        block_type = after_block.get("BlockType", "Unknown")
        if not mask_type:
            mask_type = self._get_mask_type(after_block)

        base_info = {
            "block_sid": block_sid,
            "block_name": block_name,
            "block_type": block_type,
            "mask_type": mask_type,
            "system_file": system_file,
        }

        changes: list[ConfigChange] = []
        changes.extend(self._diff_direct_p(before_block, after_block, base_info))
        changes.extend(self._diff_instance_data(before_block, after_block, base_info))
        changes.extend(self._diff_mask_value_string(before_block, after_block, base_info))
        changes.extend(self._diff_attributes(before_block, after_block, base_info))
        return changes

    def _diff_direct_p(
        self,
        before_block: etree._Element,
        after_block: etree._Element,
        base_info: dict,
    ) -> list[ConfigChange]:
        """So sánh <P> elements trực tiếp trong block (KHÔNG nằm trong InstanceData)."""
        before_configs = self._extract_direct_p(before_block)
        after_configs = self._extract_direct_p(after_block)
        return self._compare_config_dicts(
            before_configs, after_configs, base_info, "direct_P",
            xpath_template=".//Block[@SID='{sid}']/P[@Name='{name}']",
        )

    def _diff_instance_data(
        self,
        before_block: etree._Element,
        after_block: etree._Element,
        base_info: dict,
    ) -> list[ConfigChange]:
        """So sánh <InstanceData>/<P> elements."""
        before_inst = before_block.find("InstanceData")
        after_inst = after_block.find("InstanceData")

        before_configs = self._extract_p_elements(before_inst) if before_inst is not None else {}
        after_configs = self._extract_p_elements(after_inst) if after_inst is not None else {}

        return self._compare_config_dicts(
            before_configs, after_configs, base_info, "InstanceData",
            xpath_template=".//Block[@SID='{sid}']/InstanceData/P[@Name='{name}']",
        )

    def _diff_mask_value_string(
        self,
        before_block: etree._Element,
        after_block: etree._Element,
        base_info: dict,
    ) -> list[ConfigChange]:
        """So sánh MaskValueString (pipe-separated) với MaskNames mapping."""
        before_mvs = self._get_p_value(before_block, "MaskValueString")
        after_mvs = self._get_p_value(after_block, "MaskValueString")

        if before_mvs is None and after_mvs is None:
            return []

        # Parse MaskNames để map position → config name
        mask_names_str = self._get_p_value(after_block, "MaskNames") or self._get_p_value(before_block, "MaskNames")
        mask_names = mask_names_str.split("|") if mask_names_str else []

        # Split by "|" — nếu MaskValueString = "||" thì split tạo ["", "", ""]
        # Các empty strings sẽ được .strip() và so sánh đúng ở dưới
        before_values = (before_mvs or "").split("|")
        after_values = (after_mvs or "").split("|")

        # Pad to same length
        max_len = max(len(before_values), len(after_values))
        before_values.extend([""] * (max_len - len(before_values)))
        after_values.extend([""] * (max_len - len(after_values)))
        mask_names.extend([f"MaskParam_{i}" for i in range(len(mask_names), max_len)])

        changes: list[ConfigChange] = []
        sid = base_info["block_sid"]

        for i, (bv, av) in enumerate(zip(before_values, after_values)):
            if bv.strip() == av.strip():
                continue
            param_name = mask_names[i].strip() if i < len(mask_names) else f"MaskParam_{i}"
            changes.append(ConfigChange(
                **base_info,
                config_name=f"MaskValueString.{param_name}",
                old_value=bv.strip() or None,
                new_value=av.strip() or None,
                location_type="MaskValueString",
                xpath=f".//Block[@SID='{sid}']/P[@Name='MaskValueString']",
                change_type="modified" if bv and av else ("added" if av else "removed"),
            ))

        return changes

    def _diff_attributes(
        self,
        before_block: etree._Element,
        after_block: etree._Element,
        base_info: dict,
    ) -> list[ConfigChange]:
        """So sánh attributes trên Block element (Name, BlockType, etc.)."""
        # Chỉ check thay đổi, bỏ qua SID (stable ID)
        ignore_attrs = {"SID"}
        changes: list[ConfigChange] = []
        sid = base_info["block_sid"]

        all_attrs = set(before_block.attrib.keys()) | set(after_block.attrib.keys())
        for attr in sorted(all_attrs - ignore_attrs):
            bv = before_block.get(attr)
            av = after_block.get(attr)
            if bv == av:
                continue
            changes.append(ConfigChange(
                **base_info,
                config_name=f"@{attr}",
                old_value=bv,
                new_value=av,
                location_type="attribute",
                xpath=f".//Block[@SID='{sid}']/@{attr}",
                change_type="modified" if bv and av else ("added" if av else "removed"),
            ))

        return changes

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _extract_direct_p(block: etree._Element) -> dict[str, str]:
        """Extract tất cả <P> trực tiếp (không trong InstanceData)."""
        configs: dict[str, str] = {}
        for p in block.findall("P"):
            name = p.get("Name")
            if name and name not in _IGNORE_CONFIGS:
                configs[name] = (p.text or "").strip()
        return configs

    @staticmethod
    def _extract_p_elements(parent: etree._Element) -> dict[str, str]:
        """Extract tất cả <P> trong 1 parent element."""
        configs: dict[str, str] = {}
        for p in parent.findall("P"):
            name = p.get("Name")
            if name:
                configs[name] = (p.text or "").strip()
        return configs

    @staticmethod
    def _get_p_value(block: etree._Element, p_name: str) -> str | None:
        """Lấy giá trị <P Name="..."> từ block, None nếu không tìm thấy."""
        for p in block.findall("P"):
            if p.get("Name") == p_name:
                return (p.text or "").strip()
        return None

    @staticmethod
    def _get_mask_type(block: etree._Element) -> str:
        """Lấy MaskType từ block, empty string nếu không có."""
        for p in block.findall("P"):
            if p.get("Name") == "MaskType":
                return (p.text or "").strip()
        return ""

    def _compare_config_dicts(
        self,
        before: dict[str, str],
        after: dict[str, str],
        base_info: dict,
        location_type: str,
        xpath_template: str,
    ) -> list[ConfigChange]:
        """So sánh 2 dicts config → list ConfigChange."""
        sid = base_info["block_sid"]
        changes: list[ConfigChange] = []
        all_keys = set(before.keys()) | set(after.keys())

        for key in sorted(all_keys):
            bv = before.get(key)
            av = after.get(key)
            if bv == av:
                continue

            xpath = xpath_template.format(sid=sid, name=key)
            if bv is None:
                change_type = "added"
            elif av is None:
                change_type = "removed"
            else:
                change_type = "modified"

            changes.append(ConfigChange(
                **base_info,
                config_name=key,
                old_value=bv,
                new_value=av,
                location_type=location_type,
                xpath=xpath,
                change_type=change_type,
            ))

        return changes

    def _collect_blocks_as_added(self, system_file: str) -> list[BlockChange]:
        """Tất cả blocks trong file chỉ có ở after → marked as added."""
        try:
            tree = etree.parse(str(Path(self.after_dir) / system_file))
        except Exception as e:
            logger.warning(f"Không parse được {system_file} (after): {e}")
            return []
        result = []
        for block in tree.getroot().findall("Block"):
            sid = block.get("SID", "")
            if sid:
                result.append(BlockChange(
                    block_sid=sid,
                    block_name=block.get("Name", "Unknown"),
                    block_type=block.get("BlockType", "Unknown"),
                    mask_type=self._get_mask_type(block),
                    system_file=system_file,
                    change_type="added",
                ))
        return result

    def _collect_blocks_as_removed(self, system_file: str) -> list[BlockChange]:
        """Tất cả blocks trong file chỉ có ở before → marked as removed."""
        try:
            tree = etree.parse(str(Path(self.before_dir) / system_file))
        except Exception as e:
            logger.warning(f"Không parse được {system_file} (before): {e}")
            return []
        result = []
        for block in tree.getroot().findall("Block"):
            sid = block.get("SID", "")
            if sid:
                result.append(BlockChange(
                    block_sid=sid,
                    block_name=block.get("Name", "Unknown"),
                    block_type=block.get("BlockType", "Unknown"),
                    mask_type=self._get_mask_type(block),
                    system_file=system_file,
                    change_type="removed",
                ))
        return result


def diff_models(before_path: str, after_path: str) -> ModelDiff:
    """So sánh 2 file .slx → ModelDiff.

    Convenience function: extract cả 2, diff, trả kết quả.
    Temp dirs được quản lý bởi slx_extractor (auto-cleanup).

    Args:
        before_path: Đường dẫn file .slx TRƯỚC khi sửa config.
        after_path: Đường dẫn file .slx SAU khi sửa config.

    Returns:
        ModelDiff chứa tất cả thay đổi giữa 2 versions.

    Raises:
        FileNotFoundError: Nếu file .slx không tồn tại.
        ValueError: Nếu extract thất bại hoặc thư mục không hợp lệ.
    """
    before_dir = extract_slx(before_path)
    after_dir = extract_slx(after_path)

    # Validate extracted directories có chứa simulink/systems/
    for label, model_dir in [("before", before_dir), ("after", after_dir)]:
        systems_dir = Path(model_dir) / "simulink" / "systems"
        if not systems_dir.exists():
            raise ValueError(
                f"Model {label} không có thư mục simulink/systems/: {model_dir}. "
                f"File .slx có thể không phải Simulink model hợp lệ."
            )

    logger.info(f"Diff models: {before_path} vs {after_path}")
    differ = ModelDiffer(before_dir, after_dir)
    result = differ.diff()  # _enrich_defaults() đã chạy trong diff()

    logger.info(
        f"Diff complete: {len(result.block_changes)} block changes, "
        f"{len(result.config_changes)} config changes",
    )
    return result


def _enrich_defaults(diff: ModelDiff, model_dir: str) -> None:
    """Bổ sung default_value cho mỗi ConfigChange từ bddefaults.xml.

    LƯU Ý QUAN TRỌNG:
    - bddefaults.xml chỉ chứa defaults cho **standard Simulink blocks** (Gain, Abs, Sum...)
    - **TargetLink blocks** (MaskType=TL_*) là SubSystem masked → bddefaults.xml KHÔNG có
      defaults cho TL-specific configs (MaskValueString params, InstanceData)
    - TL defaults nằm trong TL library (.mdl) ở dSPACE installation, không trong model
    - Agent 1.5 sẽ tự suy luận TL defaults từ diff context (unchanged blocks = default)

    Chỉ áp dụng cho:
    - direct_P configs trên standard Simulink blocks (có trong BlockParameterDefaults)
    - KHÔNG áp dụng cho InstanceData, MaskValueString, hay TL blocks
    """
    for change in diff.config_changes:
        # Chỉ enrich direct_P trên standard blocks (không phải TL masked blocks)
        if change.location_type != "direct_P":
            continue
        if change.mask_type:
            # TL block (có MaskType) → bddefaults.xml không có defaults liên quan
            continue
        default = get_default_value(model_dir, change.block_type, change.config_name)
        if default is not None:
            change.default_value = default


def format_diff_for_agent(diff_result: ModelDiff, block_type: str = "", config_name: str = "") -> str:
    """Format ModelDiff thành text dễ đọc cho người dùng / debug.

    Nếu block_type/config_name được chỉ định → chỉ hiển thị changes liên quan.
    Dùng cho --diff-only output, logging, debug. KHÔNG dùng cho LLM input
    (LLM dùng build_agent_context() để nhận raw JSON).
    """
    changes = diff_result.config_changes

    # Filter
    if block_type:
        bt_lower = block_type.lower()
        changes = [
            c for c in changes
            if c.block_type.lower() == bt_lower or c.mask_type.lower() == bt_lower
        ]
    if config_name:
        cn_lower = config_name.lower()
        changes = [c for c in changes if cn_lower in c.config_name.lower()]

    if not changes:
        return ""

    lines = ["RAW DIFF RESULTS (từ so sánh 2 model versions):"]
    lines.append(f"Total changes: {len(changes)}")
    lines.append("")

    # Group by block
    by_block: dict[str, list[ConfigChange]] = {}
    for c in changes:
        key = f"{c.block_name} (SID={c.block_sid}, {c.system_file})"
        by_block.setdefault(key, []).append(c)

    for block_key, block_changes in by_block.items():
        first = block_changes[0]
        type_info = first.block_type
        if first.mask_type:
            type_info += f" (MaskType={first.mask_type})"
        lines.append(f"Block: {block_key}")
        lines.append(f"  Type: {type_info}")

        for c in block_changes:
            arrow = f'"{c.old_value}" → "{c.new_value}"'
            lines.append(f"  [{c.location_type}] {c.config_name}: {arrow}")
            lines.append(f"    XPath: {c.xpath}")
            lines.append(f"    Change: {c.change_type}")
            if c.default_value:
                lines.append(f"    Default (from bddefaults.xml): {c.default_value}")
        lines.append("")

    return "\n".join(lines)


def build_agent_context(
    diff_result: ModelDiff,
    block_type: str,
    config_name: str,
    model_dir: str = "",
) -> str:
    """Build raw structured context cho Agent 1.5 (LLM input).

    Chia thành 2 phần rõ ràng:
      PART 1 — CODE GENERATION: thông tin để sinh code check script
        (config nằm ở đâu, XPath, default, cách đọc)
      PART 2 — VALIDATION: thông tin để verify kết quả
        (block nào đổi, giá trị cũ/mới, bao nhiêu block bị ảnh hưởng)

    Args:
        diff_result: ModelDiff từ diff_models() hoặc ModelDiffer.diff().
        block_type: BlockType cần focus (VD: "Gain").
        config_name: Config name cần check (VD: "SaturateOnIntegerOverflow").
        model_dir: Đường dẫn model after (để tra bddefaults.xml).
    """
    import json
    from utils.defaults_parser import parse_bddefaults

    sections: list[str] = []

    # ═══════════════════════════════════════════════════════
    # PART 1 — CODE GENERATION DATA
    # Agent 2 dùng để viết check script: đọc config ở đâu, XPath gì, default gì
    # ═══════════════════════════════════════════════════════
    sections.append("=" * 60)
    sections.append("PART 1 — CODE GENERATION DATA")
    sections.append("(Dùng để sinh check script: config nằm ở đâu, cách đọc)")
    sections.append("=" * 60)

    # 1a. Config locations — chỉ lấy fields liên quan code gen
    code_gen_data: list[dict] = []
    for c in diff_result.config_changes:
        code_gen_data.append({
            "block_type": c.block_type,
            "mask_type": c.mask_type,
            "config_name": c.config_name,
            "location_type": c.location_type,
            "xpath": c.xpath,
            "default_value": c.default_value,
        })

    # Deduplicate: group by (block_type, config_name, location_type) → 1 entry
    seen: set[str] = set()
    unique_locations: list[dict] = []
    for item in code_gen_data:
        key = f"{item['block_type']}|{item['mask_type']}|{item['config_name']}|{item['location_type']}"
        if key not in seen:
            seen.add(key)
            # Generalize xpath: thay SID cụ thể bằng pattern
            xpath = item["xpath"]
            # .//Block[@SID='68']/P[...] → .//Block[@BlockType='Gain']/P[...]
            xpath_general = re.sub(
                r"@SID='[^']*'",
                f"@BlockType='{item['block_type']}'",
                xpath,
            )
            unique_locations.append({
                **item,
                "xpath_pattern": xpath_general,
            })

    sections.append("")
    sections.append("CONFIG_LOCATIONS (unique per block_type + config_name):")
    sections.append(json.dumps(unique_locations, indent=2, ensure_ascii=False))

    # 1b. Defaults dictionary (từ bddefaults.xml)
    if model_dir:
        all_defaults = parse_bddefaults(model_dir)
        relevant_defaults: dict[str, dict[str, str]] = {}
        for bt in {block_type, "SubSystem"}:
            if bt in all_defaults:
                relevant_defaults[bt] = all_defaults[bt]
        if relevant_defaults:
            sections.append("")
            sections.append("BLOCK_DEFAULTS_DICTIONARY (from bddefaults.xml):")
            sections.append(json.dumps(relevant_defaults, indent=2, ensure_ascii=False))
        else:
            sections.append("")
            sections.append(
                f"BLOCK_DEFAULTS_DICTIONARY: không có defaults cho {block_type} trong bddefaults.xml. "
                f"Nếu là TargetLink block (MaskType=TL_*), defaults nằm ở TL library. "
                f"Suy luận default từ diff context (unchanged blocks = default)."
            )

    # ═══════════════════════════════════════════════════════
    # PART 2 — VALIDATION DATA
    # Dùng để verify kết quả: block nào đổi, giá trị cũ/mới, expected behavior
    # ═══════════════════════════════════════════════════════
    sections.append("")
    sections.append("=" * 60)
    sections.append("PART 2 — VALIDATION DATA")
    sections.append("(Dùng để verify kết quả: block nào đổi, giá trị expected)")
    sections.append("=" * 60)

    # 2a. Changed blocks — chi tiết giá trị cũ/mới cho từng block
    validation_data: list[dict] = []
    for c in diff_result.config_changes:
        validation_data.append({
            "block_sid": c.block_sid,
            "block_name": c.block_name,
            "block_type": c.block_type,
            "system_file": c.system_file,
            "config_name": c.config_name,
            "old_value": c.old_value,
            "new_value": c.new_value,
            "change_type": c.change_type,
        })

    sections.append("")
    sections.append("CHANGED_BLOCKS (giá trị cũ → mới cho từng block):")
    sections.append(json.dumps(validation_data, indent=2, ensure_ascii=False))

    # 2b. Summary statistics
    bt_lower = block_type.lower()
    relevant_changes = [
        c for c in diff_result.config_changes
        if (c.block_type.lower() == bt_lower or c.mask_type.lower() == bt_lower)
        and config_name.lower() in c.config_name.lower()
    ]
    sections.append("")
    sections.append(f"DIFF_SUMMARY for {block_type}/{config_name}:")
    sections.append(f"  blocks_with_changes: {len(relevant_changes)}")
    for rc in relevant_changes:
        sections.append(f"  - {rc.block_name} (SID={rc.block_sid}): \"{rc.old_value}\" → \"{rc.new_value}\"")

    # 2c. File changes (nếu có)
    if diff_result.files_only_before or diff_result.files_only_after:
        sections.append("")
        if diff_result.files_only_before:
            sections.append(f"FILES_ONLY_BEFORE (deleted): {diff_result.files_only_before}")
        if diff_result.files_only_after:
            sections.append(f"FILES_ONLY_AFTER (new): {diff_result.files_only_after}")

    return "\n".join(sections)
