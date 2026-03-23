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


