"""
Universal block finder — tìm block trong XML tree bằng NHIỀU cách.

Vấn đề: Cùng 1 "block" có thể nằm ở 3 dạng khác nhau trong XML:
  1. Native:    BlockType="Gain"
  2. Reference: BlockType="Reference" + SourceType="Compare To Constant"
  3. Masked/TL: BlockType="SubSystem" + MaskType="TL_Gain"

Module này cung cấp 1 hàm duy nhất `find_blocks()` mà generated scripts
import để tìm block — thay vì tự viết xpath mỗi lần (dễ sai, dễ thiếu).

Dùng trong generated_checks/:
    from utils.block_finder import find_blocks
    blocks = find_blocks(root, "Gain")           # tìm native Gain
    blocks = find_blocks(root, "Compare To Constant")  # tìm Reference block
    blocks = find_blocks(root, "TL_Gain")        # tìm masked TL block
"""

from lxml import etree


def find_blocks(root: etree._Element, block_identifier: str) -> list[etree._Element]:
    """Tìm tất cả blocks matching identifier trong 1 system XML root.

    Tìm theo thứ tự ưu tiên:
      1. BlockType attribute (native blocks: Gain, Abs, Sum, ...)
      2. MaskType property  (masked/TL blocks: TL_Gain, TL_Abs, ...)
      3. SourceType property (reference blocks: Compare To Constant, ...)

    Kết quả được deduplicate by SID — 1 block chỉ xuất hiện 1 lần.

    Args:
        root: Root element của 1 system_*.xml file (đã parse).
        block_identifier: Tên block cần tìm — có thể là BlockType,
                          MaskType, hoặc SourceType.
                          VD: "Gain", "TL_Gain", "Compare To Constant"

    Returns:
        List các <Block> elements tìm thấy (không trùng SID).
    """
    seen_sids: set[str] = set()
    results: list[etree._Element] = []

    def _add(block: etree._Element) -> None:
        sid = block.get("SID", "")
        if sid and sid in seen_sids:
            return
        seen_sids.add(sid)
        results.append(block)

    # 1. Native BlockType match
    for block in root.findall(f"Block[@BlockType='{block_identifier}']"):
        _add(block)

    # 2. MaskType match (TargetLink / custom masked blocks)
    #    BlockType thường là "SubSystem" nhưng MaskType mới là identity thật
    for block in root.findall("Block"):
        mask_node = block.find("P[@Name='MaskType']")
        if mask_node is not None and mask_node.text is not None:
            if mask_node.text.strip() == block_identifier:
                _add(block)

    # 3. SourceType match (Reference blocks từ library)
    #    BlockType="Reference" + SourceType="Compare To Constant"
    for block in root.findall("Block[@BlockType='Reference']"):
        source_node = block.find("P[@Name='SourceType']")
        if source_node is not None and source_node.text is not None:
            if source_node.text.strip() == block_identifier:
                _add(block)

    return results


def find_all_blocks(root: etree._Element) -> list[etree._Element]:
    """Trả về TẤT CẢ blocks trong 1 system XML root (direct children).

    Dùng cho rules kiểu "liệt kê tất cả block, check cái nào bị cấm".

    Args:
        root: Root element của 1 system_*.xml file.

    Returns:
        List tất cả <Block> elements.
    """
    return root.findall("Block")


def get_block_identity(block: etree._Element) -> str:
    """Xác định identity thật của block — ưu tiên MaskType > SourceType > BlockType.

    Trong XML, block có thể là:
      - Native: BlockType="Gain" → identity = "Gain"
      - Masked: BlockType="SubSystem" + MaskType="TL_Gain" → identity = "TL_Gain"
      - Reference: BlockType="Reference" + SourceType="Compare To Constant"
                   → identity = "Compare To Constant"

    Args:
        block: <Block> element.

    Returns:
        Identity string (MaskType hoặc SourceType hoặc BlockType).
    """
    # MaskType ưu tiên cao nhất (TL blocks)
    mask_node = block.find("P[@Name='MaskType']")
    if mask_node is not None and mask_node.text and mask_node.text.strip():
        return mask_node.text.strip()

    # SourceType cho Reference blocks
    if block.get("BlockType") == "Reference":
        source_node = block.find("P[@Name='SourceType']")
        if source_node is not None and source_node.text and source_node.text.strip():
            return source_node.text.strip()

    # Fallback: BlockType
    return block.get("BlockType", "Unknown")


def list_all_block_types(root: etree._Element) -> dict[str, int]:
    """Đếm tất cả block types trong 1 system XML root.

    Dùng identity thật (MaskType > SourceType > BlockType).
    Hữu ích cho rules "không được dùng block X" — biết model có những gì.

    Args:
        root: Root element của 1 system_*.xml file.

    Returns:
        Dict {identity: count}. VD: {"Gain": 1, "Compare To Constant": 2}
    """
    counts: dict[str, int] = {}
    for block in root.findall("Block"):
        identity = get_block_identity(block)
        counts[identity] = counts.get(identity, 0) + 1
    return counts


def find_blocks_with_config(
    root: etree._Element,
    config_name: str,
) -> list[etree._Element]:
    """Tìm TẤT CẢ blocks có chứa config cụ thể (explicit trong XML).

    Reverse lookup: không cần biết block type, chỉ cần biết config name.
    Dùng khi rule chỉ nói về config mà không nói rõ block nào.

    Tìm ở 3 vị trí:
      1. Direct <P Name="config_name">
      2. <InstanceData>/<P Name="config_name">
      3. Block attribute (hiếm, nhưng có thể xảy ra)

    Args:
        root: Root element của 1 system_*.xml file.
        config_name: Tên config cần tìm. VD: "SaturateOnIntegerOverflow"

    Returns:
        List các <Block> elements có chứa config đó.
    """
    results: list[etree._Element] = []

    for block in root.findall("Block"):
        # Direct <P>
        node = block.find(f"P[@Name='{config_name}']")
        if node is not None:
            results.append(block)
            continue

        # InstanceData/<P>
        instance = block.find("InstanceData")
        if instance is not None:
            node = instance.find(f"P[@Name='{config_name}']")
            if node is not None:
                results.append(block)

    return results


def get_block_config(
    block: etree._Element,
    config_name: str,
    default_value: str | None = None,
) -> str | None:
    """Đọc config value từ block — check cả 3 vị trí.

    Thứ tự tìm:
      1. Direct <P Name="config_name"> (child trực tiếp của Block)
      2. <InstanceData>/<P Name="config_name"> (Reference blocks)
      3. Fallback về default_value nếu không tìm thấy

    Args:
        block: <Block> element.
        config_name: Tên config cần đọc. VD: "SaturateOnIntegerOverflow"
        default_value: Giá trị trả về nếu không tìm thấy ở cả 2 nơi.

    Returns:
        Config value (str) hoặc default_value nếu không tìm thấy.
    """
    # 1. Direct <P>
    node = block.find(f"P[@Name='{config_name}']")
    if node is not None and node.text is not None:
        return node.text.strip()

    # 2. InstanceData/<P>
    instance = block.find("InstanceData")
    if instance is not None:
        node = instance.find(f"P[@Name='{config_name}']")
        if node is not None and node.text is not None:
            return node.text.strip()

    # 3. Fallback
    return default_value
