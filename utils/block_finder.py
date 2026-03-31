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


# ──────────────────────────────────────────────────────────────────────
# Internal safe-lookup helpers (no XPath f-string injection risk)
# ──────────────────────────────────────────────────────────────────────

def _find_p(parent: etree._Element, name: str) -> "etree._Element | None":
    """Find first <P Name="..."> child by attribute comparison (injection-safe)."""
    for p in parent.findall("P"):
        if p.get("Name") == name:
            return p
    return None


def _find_mask_param(mask_elem: etree._Element, name: str) -> "etree._Element | None":
    """Find first <MaskParameter Name="..."> child (injection-safe)."""
    for mp in mask_elem.findall("MaskParameter"):
        if mp.get("Name") == name:
            return mp
    return None


def _read_p_value(
    parent: etree._Element,
    name: str,
) -> "str | None":
    """Read text of <P Name="..."> including <Array><D>...</D></Array> form.

    Returns:
        str value, or None if not found.
        Array params are joined with '|': e.g. "0|1|2" for <D>0</D><D>1</D><D>2</D>
    """
    node = _find_p(parent, name)
    if node is None:
        return None
    if node.text is not None:
        return node.text.strip()
    # Array form: <P Name="..."><Array><D>val</D>...</Array></P>
    array_node = node.find("Array")
    if array_node is not None:
        d_values = [(d.text or "").strip() for d in array_node.findall("D") if d.text]
        if d_values:
            return "|".join(d_values)
    return None


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

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
    seen_ids: set[int] = set()  # fallback dedup by object id when SID is empty
    results: list[etree._Element] = []

    def _add(block: etree._Element) -> None:
        sid = block.get("SID", "")
        if sid:
            if sid in seen_sids:
                return
            seen_sids.add(sid)
        else:
            obj_id = id(block)
            if obj_id in seen_ids:
                return
            seen_ids.add(obj_id)
        results.append(block)

    for block in root.findall("Block"):
        # 1. Native BlockType match (safe attribute comparison — avoids XPath injection)
        if block.get("BlockType") == block_identifier:
            _add(block)
            continue

        # 2. MaskType match (TargetLink / custom masked blocks)
        mask_node = _find_p(block, "MaskType")
        if mask_node is not None and mask_node.text is not None:
            if mask_node.text.strip() == block_identifier:
                _add(block)
                continue

        # 3. SourceType match (Reference blocks từ library)
        if block.get("BlockType") == "Reference":
            source_node = _find_p(block, "SourceType")
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
    mask_node = _find_p(block, "MaskType")
    if mask_node is not None and mask_node.text and mask_node.text.strip():
        return mask_node.text.strip()

    if block.get("BlockType") == "Reference":
        source_node = _find_p(block, "SourceType")
        if source_node is not None and source_node.text and source_node.text.strip():
            return source_node.text.strip()

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

    Tìm ở 4 vị trí:
      1. Direct <P Name="config_name">
      2. <InstanceData>/<P Name="config_name">
      3. MaskValueString (pipe-separated, keyed by MaskNames)
      4. Mask/MaskParameter (newer Simulink format: <Mask>/<MaskParameter>)

    Args:
        root: Root element của 1 system_*.xml file.
        config_name: Tên config cần tìm. VD: "SaturateOnIntegerOverflow"

    Returns:
        List các <Block> elements có chứa config đó.
    """
    results: list[etree._Element] = []

    for block in root.findall("Block"):
        # 1. Direct <P>
        if _find_p(block, config_name) is not None:
            results.append(block)
            continue

        # 2. InstanceData/<P>
        instance = block.find("InstanceData")
        if instance is not None and _find_p(instance, config_name) is not None:
            results.append(block)
            continue

        # 3. MaskValueString (pipe-separated, keyed by MaskNames)
        mask_names_node = _find_p(block, "MaskNames")
        if mask_names_node is not None and mask_names_node.text:
            names = mask_names_node.text.split("|")
            if config_name in (n.strip() for n in names):
                results.append(block)
                continue

        # 4. Mask/MaskParameter (newer Simulink format)
        mask_elem = block.find("Mask")
        if mask_elem is not None and _find_mask_param(mask_elem, config_name) is not None:
            results.append(block)
            continue

    return results


def get_block_config(
    block: etree._Element,
    config_name: str,
    default_value: "str | None" = None,
) -> "str | None":
    """Đọc config value từ block — check cả 5 vị trí.

    Thứ tự tìm:
      1. Direct <P Name="config_name"> (child trực tiếp của Block)
      2. <InstanceData>/<P Name="config_name"> (Reference blocks)
      3. MaskValueString (pipe-separated, match by MaskNames index)
      3.5. Mask/MaskParameter (newer Simulink format: <Mask>/<MaskParameter>)
      4. Fallback về default_value nếu không tìm thấy

    Args:
        block: <Block> element.
        config_name: Tên config cần đọc. VD: "SaturateOnIntegerOverflow"
        default_value: Giá trị trả về nếu không tìm thấy.

    Returns:
        Config value (str) hoặc default_value nếu không tìm thấy.
        Với <Array> params: trả về các <D> elements join bằng '|'
        VD: <Array><D>fixdt(1,16,12)</D></Array> → "fixdt(1,16,12)"
        VD: <Array><D>0</D><D>1</D><D>2</D></Array> → "0|1|2"
    """
    # 1. Direct <P> (injection-safe via _read_p_value)
    val = _read_p_value(block, config_name)
    if val is not None:
        return val

    # 2. InstanceData/<P>
    instance = block.find("InstanceData")
    if instance is not None:
        val = _read_p_value(instance, config_name)
        if val is not None:
            return val

    # 3. MaskValueString (pipe-separated values keyed by MaskNames)
    mask_names_node = _find_p(block, "MaskNames")
    mask_values_node = _find_p(block, "MaskValueString")
    if mask_names_node is not None and mask_values_node is not None:
        names = (mask_names_node.text or "").split("|")
        values = (mask_values_node.text or "").split("|")
        for i, name in enumerate(names):
            if name.strip() == config_name:
                if i < len(values):
                    return values[i].strip()
                break  # name matched but index out of range — no value

    # 3.5 Mask/MaskParameter (newer Simulink format)
    mask_elem = block.find("Mask")
    if mask_elem is not None:
        mp = _find_mask_param(mask_elem, config_name)
        if mp is not None:
            val = mp.get("Value", "")
            if val:
                return val

    # 4. Fallback
    return default_value
