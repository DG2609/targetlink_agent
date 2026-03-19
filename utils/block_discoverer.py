"""
Auto-discover blocks: scan toàn bộ model XML → tìm blocks matching keyword.
Trả về dict {block_sid: {info}} cho code generator biết model có gì.

Dùng block_finder.get_block_identity() để xác định identity thật —
hỗ trợ cả 3 loại: native (BlockType), masked (MaskType), reference (SourceType).
"""

import logging
from pathlib import Path
from lxml import etree

logger = logging.getLogger(__name__)

from utils.defaults_parser import parse_bddefaults
from utils.block_finder import get_block_identity


def discover_blocks(model_dir: str, block_keyword: str) -> dict[str, dict]:
    """Scan tất cả system_*.xml, tìm blocks matching keyword.

    Match keyword against identity thật (MaskType > SourceType > BlockType).
    Case-insensitive substring match.

    Args:
        model_dir: Đường dẫn tới model tree (sau extract .slx).
        block_keyword: Keyword tìm kiếm (case-insensitive).
                       VD: "Gain", "Inport", "TL_Inport", "Compare To Constant"

    Returns:
        Dict keyed by SID:
        {sid: {name, block_type, identity, mask_type, source_type,
               system_file, path, explicit_configs_count, default_configs_count,
               sample_configs}}
    """
    systems_dir = Path(model_dir) / "simulink" / "systems"
    if not systems_dir.exists():
        return {}

    keyword_lower = block_keyword.lower()
    results: dict[str, dict] = {}
    defaults_map = parse_bddefaults(model_dir)

    for xml_file in sorted(systems_dir.glob("system_*.xml")):
        try:
            tree = etree.parse(str(xml_file))
            root = tree.getroot()
        except Exception as e:
            logger.warning(f"Không parse được {xml_file.name}: {e}")
            continue

        rel_path = str(xml_file.relative_to(Path(model_dir))).replace("\\", "/")

        for block in root.findall("Block"):
            bt = block.get("BlockType", "")
            name = block.get("Name", "Unknown")
            sid = block.get("SID", "")

            # Identity thật: MaskType > SourceType > BlockType
            identity = get_block_identity(block)

            # MaskType
            mask_type = ""
            mask_node = block.find("P[@Name='MaskType']")
            if mask_node is not None and mask_node.text:
                mask_type = mask_node.text.strip()

            # SourceType (Reference blocks)
            source_type = ""
            if bt == "Reference":
                source_node = block.find("P[@Name='SourceType']")
                if source_node is not None and source_node.text:
                    source_type = source_node.text.strip()

            # Match keyword against identity, BlockType, MaskType, SourceType
            matchable = [identity.lower(), bt.lower(), mask_type.lower(), source_type.lower()]
            if not any(keyword_lower in m for m in matchable):
                continue

            # Count explicit configs
            explicit_configs: dict[str, str] = {}
            for p in block.findall("P"):
                p_name = p.get("Name")
                if p_name:
                    explicit_configs[p_name] = (p.text or "").strip()

            # InstanceData configs
            instance_data = block.find("InstanceData")
            if instance_data is not None:
                for p in instance_data.findall("P"):
                    p_name = p.get("Name")
                    if p_name:
                        explicit_configs[f"InstanceData.{p_name}"] = (p.text or "").strip()

            # Count defaults
            default_count = len(defaults_map.get(bt, {}))

            results[sid] = {
                "name": name,
                "block_type": bt,
                "identity": identity,
                "mask_type": mask_type,
                "source_type": source_type,
                "system_file": rel_path,
                "path": f"{xml_file.stem}/{name}",
                "explicit_configs_count": len(explicit_configs),
                "default_configs_count": default_count,
                "sample_configs": dict(list(explicit_configs.items())[:5]),
            }

    return results
