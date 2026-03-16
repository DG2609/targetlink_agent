"""
Auto-discover blocks: scan toàn bộ model XML → tìm blocks matching keyword.
Trả về dict {block_sid: {info}} cho code generator biết model có gì.
"""

from pathlib import Path
from lxml import etree

from utils.defaults_parser import parse_bddefaults


def discover_blocks(model_dir: str, block_keyword: str) -> dict[str, dict]:
    """Scan tất cả system_*.xml, tìm blocks matching keyword (BlockType hoặc MaskType).

    Args:
        model_dir: Đường dẫn tới model tree (sau extract .slx).
        block_keyword: Keyword tìm kiếm (case-insensitive).
                       VD: "Gain", "Inport", "TL_Inport"

    Returns:
        Dict keyed by SID:
        {sid: {name, block_type, mask_type, system_file, path, configs_count, sample_configs}}
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
        except Exception:
            continue

        rel_path = str(xml_file.relative_to(Path(model_dir))).replace("\\", "/")

        for block in root.findall("Block"):
            bt = block.get("BlockType", "")
            name = block.get("Name", "Unknown")
            sid = block.get("SID", "")

            # MaskType (TargetLink custom blocks)
            mask_type = ""
            for p in block.findall("P"):
                if p.get("Name") == "MaskType":
                    mask_type = (p.text or "").strip()
                    break

            # Match keyword against BlockType or MaskType
            if keyword_lower not in bt.lower() and keyword_lower not in mask_type.lower():
                continue

            # Count explicit configs
            explicit_configs: dict[str, str] = {}
            for p in block.findall("P"):
                p_name = p.get("Name")
                if p_name:
                    explicit_configs[p_name] = (p.text or "").strip()

            # Count defaults
            default_count = len(defaults_map.get(bt, {}))

            results[sid] = {
                "name": name,
                "block_type": bt,
                "mask_type": mask_type,
                "system_file": rel_path,
                "path": f"{xml_file.stem}/{name}",
                "explicit_configs_count": len(explicit_configs),
                "default_configs_count": default_count,
                "sample_configs": dict(list(explicit_configs.items())[:5]),
            }

    return results
