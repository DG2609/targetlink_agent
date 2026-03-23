"""
Hierarchy-aware block finding for generated check scripts.

Generated check scripts run as standalone Python via subprocess. They can
import `utils.block_finder` for single-file block finding, but lack hierarchy
awareness (traversing SubSystem levels, resolving full paths, tracing
connections across subsystem boundaries).

This module provides pure-function utilities that walk the entire SLX model
tree and return enriched block data with full hierarchy paths — without
requiring ModelIndex (which is designed for agent tools, not standalone scripts).

Usage in generated scripts::

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from utils.hierarchy_utils import walk_blocks, build_subsystem_map

    def check_rule(model_dir: str) -> dict:
        blocks = walk_blocks(model_dir, "Gain")
        for b in blocks:
            print(b["block_path"])  # "Root/Lowpass Filter/s(1)"

Relationship to block_finder.py:
    This module imports and reuses `find_blocks()`, `find_all_blocks()`,
    `get_block_identity()`, and `get_block_config()` from block_finder
    for correct 3-way matching (BlockType / MaskType / SourceType).
    It adds hierarchy traversal on top.

SLX model structure (after unzip)::

    model_dir/
      simulink/
        systems/
          system_root.xml    <- Root level
          system_6.xml       <- SubSystem SID=6 content
          system_32.xml      <- SubSystem SID=32 content
        bddefaults.xml       <- Default values
        blockdiagram.xml     <- Metadata only (NOT block data)

SubSystem blocks contain ``<System Ref="system_N"/>`` pointing to child files.
Blocks are direct children of the root ``<System>`` element in each system file.
Line elements: ``<P Name="Src">SID#out:N</P>``, ``<P Name="Dst">SID#in:N</P>``.
"""

from __future__ import annotations

import os
from pathlib import Path

from lxml import etree

from utils.block_finder import (
    find_all_blocks,
    find_blocks,
    get_block_config,
    get_block_identity,
)


# ──────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────

def _parse_xml(
    model_dir: str,
    xml_file: str,
    cache: dict[str, etree._Element],
) -> etree._Element | None:
    """Parse an XML file and return its root element, using *cache* to avoid re-parsing.

    Args:
        model_dir: Absolute path to the unzipped model directory.
        xml_file:  Relative path within model_dir (e.g. ``simulink/systems/system_root.xml``).
        cache:     Mutable dict ``{xml_file: root_element}`` — shared within one
                   top-level function call so each file is parsed at most once.

    Returns:
        Root ``<System>`` element, or ``None`` if the file does not exist or
        cannot be parsed.
    """
    if xml_file in cache:
        return cache[xml_file]

    full_path = os.path.join(model_dir, xml_file)
    if not os.path.isfile(full_path):
        return None

    try:
        tree = etree.parse(full_path)
        root = tree.getroot()
        cache[xml_file] = root
        return root
    except etree.XMLSyntaxError:
        return None


def _get_p_text(element: etree._Element, name: str) -> str:
    """Extract text of ``<P Name="...">`` child, or empty string."""
    for p in element.findall("P"):
        if p.get("Name") == name:
            return (p.text or "").strip()
    return ""


# ──────────────────────────────────────────────────────────────────────
# 1. build_subsystem_map
# ──────────────────────────────────────────────────────────────────────

def build_subsystem_map(model_dir: str) -> dict[str, dict]:
    """Build a flat map of ``{system_file: metadata}`` by traversing the hierarchy.

    Starts from ``system_root.xml``, finds SubSystem blocks with
    ``<System Ref="system_N"/>``, and recurses into each child file.

    Args:
        model_dir: Absolute path to the unzipped SLX model directory.

    Returns:
        Dict keyed by relative system file path. Each value is::

            {
                "name":        str,   # Subsystem name (e.g. "Lowpass Filter")
                "depth":       int,   # 0 for root, 1 for direct children, ...
                "parent_path": str,   # Full path of parent ("" for root)
                "full_path":   str,   # Human-readable path ("Root/Lowpass Filter")
                "sid":         str,   # SID of the SubSystem block ("" for root)
            }

    Example::

        {
            "simulink/systems/system_root.xml": {
                "name": "Root", "depth": 0, "parent_path": "", "full_path": "Root", "sid": ""
            },
            "simulink/systems/system_6.xml": {
                "name": "Lowpass Filter", "depth": 1,
                "parent_path": "Root", "full_path": "Root/Lowpass Filter", "sid": "6"
            },
        }
    """
    cache: dict[str, etree._Element] = {}
    result: dict[str, dict] = {}

    root_file = "simulink/systems/system_root.xml"
    _build_map_recursive(model_dir, root_file, "Root", "", 0, "", cache, result)

    return result


def _build_map_recursive(
    model_dir: str,
    system_file: str,
    name: str,
    parent_path: str,
    depth: int,
    sid: str,
    cache: dict[str, etree._Element],
    result: dict[str, dict],
) -> None:
    """Recursively populate *result* with subsystem metadata."""
    full_path = f"{parent_path}/{name}" if parent_path else name

    result[system_file] = {
        "name": name,
        "depth": depth,
        "parent_path": parent_path,
        "full_path": full_path,
        "sid": sid,
    }

    root = _parse_xml(model_dir, system_file, cache)
    if root is None:
        return

    # Find SubSystem blocks that reference child system files
    for block in root.findall("Block[@BlockType='SubSystem']"):
        sub_name = block.get("Name", "Unknown")
        sub_sid = block.get("SID", "")
        system_ref = block.find("System")
        if system_ref is not None:
            ref = system_ref.get("Ref", "")
            if ref:
                child_file = f"simulink/systems/{ref}.xml"
                _build_map_recursive(
                    model_dir, child_file, sub_name, full_path,
                    depth + 1, sub_sid, cache, result,
                )


# ──────────────────────────────────────────────────────────────────────
# 2. walk_blocks
# ──────────────────────────────────────────────────────────────────────

def walk_blocks(model_dir: str, block_identifier: str) -> list[dict]:
    """Find ALL blocks matching *block_identifier* across ALL subsystem levels.

    Uses ``block_finder.find_blocks()`` internally for correct 3-way matching
    (BlockType / MaskType / SourceType).

    Args:
        model_dir:        Absolute path to the unzipped SLX model directory.
        block_identifier: Block type to search for — can be a BlockType
                          (``"Gain"``), MaskType (``"TL_Gain"``), or SourceType
                          (``"Compare To Constant"``).

    Returns:
        List of dicts, one per matching block::

            {
                "name":             str,  # Block name in XML
                "sid":              str,  # Block SID
                "block_type":       str,  # True identity (via get_block_identity)
                "block_path":       str,  # Full hierarchy path: "Root/Lowpass Filter/s(1)"
                "system_file":      str,  # Relative path to the system XML file
                "depth":            int,  # Subsystem depth (0 = root)
                "parent_subsystem": str,  # Name of the containing subsystem
            }
    """
    cache: dict[str, etree._Element] = {}
    subsystem_map = build_subsystem_map(model_dir)
    results: list[dict] = []

    for system_file, meta in subsystem_map.items():
        root = _parse_xml(model_dir, system_file, cache)
        if root is None:
            continue

        blocks = find_blocks(root, block_identifier)
        for block in blocks:
            block_name = block.get("Name", "Unknown")
            block_sid = block.get("SID", "")
            identity = get_block_identity(block)
            block_path = f"{meta['full_path']}/{block_name}"

            results.append({
                "name": block_name,
                "sid": block_sid,
                "block_type": identity,
                "block_path": block_path,
                "system_file": system_file,
                "depth": meta["depth"],
                "parent_subsystem": meta["name"],
            })

    return results


# ──────────────────────────────────────────────────────────────────────
# 3. walk_all_blocks
# ──────────────────────────────────────────────────────────────────────

def walk_all_blocks(model_dir: str) -> list[dict]:
    """Find ALL blocks across all subsystem levels.

    Useful for forbidden-block rules where every block must be inspected
    regardless of type.

    Args:
        model_dir: Absolute path to the unzipped SLX model directory.

    Returns:
        List of dicts with the same format as :func:`walk_blocks`.
    """
    cache: dict[str, etree._Element] = {}
    subsystem_map = build_subsystem_map(model_dir)
    results: list[dict] = []

    for system_file, meta in subsystem_map.items():
        root = _parse_xml(model_dir, system_file, cache)
        if root is None:
            continue

        blocks = find_all_blocks(root)
        for block in blocks:
            block_name = block.get("Name", "Unknown")
            block_sid = block.get("SID", "")
            identity = get_block_identity(block)
            block_path = f"{meta['full_path']}/{block_name}"

            results.append({
                "name": block_name,
                "sid": block_sid,
                "block_type": identity,
                "block_path": block_path,
                "system_file": system_file,
                "depth": meta["depth"],
                "parent_subsystem": meta["name"],
            })

    return results


# ──────────────────────────────────────────────────────────────────────
# 4. get_block_full_path
# ──────────────────────────────────────────────────────────────────────

def get_block_full_path(
    subsystem_map: dict[str, dict],
    system_file: str,
    block_name: str,
) -> str:
    """Resolve the full hierarchy path for a block given its system file and name.

    Args:
        subsystem_map: Map returned by :func:`build_subsystem_map`.
        system_file:   Relative system file path (e.g. ``simulink/systems/system_6.xml``).
        block_name:    Block ``Name`` attribute from XML.

    Returns:
        Full path string like ``"Root/Lowpass Filter/s(1)"``.
        If the system file is not found in the map, returns ``"<unknown>/<block_name>"``.
    """
    meta = subsystem_map.get(system_file)
    if meta is None:
        return f"<unknown>/{block_name}"
    return f"{meta['full_path']}/{block_name}"


# ──────────────────────────────────────────────────────────────────────
# 5. get_connections
# ──────────────────────────────────────────────────────────────────────

def get_connections(
    model_dir: str,
    system_file: str,
    block_sid: str,
) -> dict[str, list[dict]]:
    """Get incoming and outgoing connections for a block within its system file.

    Parses ``<Line>`` elements in the system file. Each line has a ``Src``
    (``SID#out:N``) and one or more ``Dst`` endpoints (direct or via
    ``<Branch>`` elements for fan-out).

    Args:
        model_dir:   Absolute path to the unzipped SLX model directory.
        system_file: Relative system file path (e.g. ``simulink/systems/system_6.xml``).
        block_sid:   SID of the block to query connections for.

    Returns:
        Dict with two keys::

            {
                "incoming": [{"sid": str, "name": str, "type": str, "port": str}, ...],
                "outgoing": [{"sid": str, "name": str, "type": str, "port": str}, ...],
            }

        Returns empty lists if the file cannot be parsed or the block has no
        connections.
    """
    cache: dict[str, etree._Element] = {}
    root = _parse_xml(model_dir, system_file, cache)

    if root is None:
        return {"incoming": [], "outgoing": []}

    # Build SID -> block info map for this system file
    sid_map: dict[str, dict] = {}
    for block in root.findall("Block"):
        b_sid = block.get("SID", "")
        if b_sid:
            sid_map[b_sid] = {
                "sid": b_sid,
                "name": block.get("Name", "Unknown"),
                "type": get_block_identity(block),
            }

    incoming: list[dict] = []
    outgoing: list[dict] = []

    for line in root.findall("Line"):
        src_text = _get_p_text(line, "Src")
        destinations = _collect_destinations(line)

        src_sid, src_port = _parse_endpoint(src_text)

        # Block is the source -> outgoing connections
        if src_sid == block_sid:
            for dst_text in destinations:
                dst_sid, dst_port = _parse_endpoint(dst_text)
                dst_info = sid_map.get(dst_sid, {
                    "sid": dst_sid, "name": "?", "type": "?",
                })
                outgoing.append({**dst_info, "port": dst_port})

        # Block is a destination -> incoming connection
        for dst_text in destinations:
            dst_sid, _ = _parse_endpoint(dst_text)
            if dst_sid == block_sid:
                src_info = sid_map.get(src_sid, {
                    "sid": src_sid, "name": "?", "type": "?",
                })
                incoming.append({**src_info, "port": src_port})

    # Resolve Goto/From implicit connections
    block_elem = None
    for b in root.findall("Block"):
        if b.get("SID") == block_sid:
            block_elem = b
            break
    if block_elem is not None:
        bt = block_elem.get("BlockType", "")
        goto_from = _resolve_goto_from(root, block_sid, bt)
        if bt == "Goto":
            outgoing.extend(goto_from)
        elif bt == "From":
            incoming.extend(goto_from)

    return {"incoming": incoming, "outgoing": outgoing}


def _resolve_goto_from(
    root: etree._Element,
    block_sid: str,
    block_type: str,
) -> list[dict]:
    """Resolve Goto/From implicit connections within a system file.

    If block is a Goto, find all From blocks with matching GotoTag.
    If block is a From, find the Goto block with matching GotoTag.
    """
    if block_type not in ("Goto", "From"):
        return []

    block = None
    for b in root.findall("Block"):
        if b.get("SID") == block_sid:
            block = b
            break
    if block is None:
        return []

    goto_tag_node = block.find("P[@Name='GotoTag']")
    if goto_tag_node is None or not goto_tag_node.text:
        return []
    goto_tag = goto_tag_node.text.strip()

    target_type = "From" if block_type == "Goto" else "Goto"
    results: list[dict] = []
    for b in root.findall(f"Block[@BlockType='{target_type}']"):
        tag_node = b.find("P[@Name='GotoTag']")
        if tag_node is not None and tag_node.text and tag_node.text.strip() == goto_tag:
            results.append({
                "sid": b.get("SID", ""),
                "name": b.get("Name", ""),
                "type": target_type,
                "port": "1",
            })

    return results


def _parse_endpoint(endpoint: str) -> tuple[str, str]:
    """Parse ``"SID#out:N"`` or ``"SID#in:N"`` into ``(sid, port_spec)``.

    Returns:
        Tuple of (sid, port_string). If no ``#`` is present, port is empty.
    """
    if not endpoint:
        return ("", "")
    if "#" in endpoint:
        parts = endpoint.split("#", 1)
        return (parts[0], parts[1])
    return (endpoint, "")


def _collect_destinations(line: etree._Element) -> list[str]:
    """Collect all destination endpoint strings from a Line element.

    Handles both direct ``<P Name="Dst">`` and ``<Branch>`` fan-out.

    Args:
        line: A ``<Line>`` element.

    Returns:
        List of destination strings (e.g. ``["8#in:1", "9#in:2"]``).
    """
    dsts: list[str] = []

    # Direct Dst on the Line element
    for p in line.findall("P"):
        if p.get("Name") == "Dst":
            text = (p.text or "").strip()
            if text:
                dsts.append(text)

    # Branch destinations (fan-out) — .iter finds nested branches too
    for branch in line.iter("Branch"):
        for p in branch.findall("P"):
            if p.get("Name") == "Dst":
                text = (p.text or "").strip()
                if text:
                    dsts.append(text)

    return dsts


# ──────────────────────────────────────────────────────────────────────
# 6. get_parent_subsystem_info
# ──────────────────────────────────────────────────────────────────────

def get_parent_subsystem_info(
    model_dir: str,
    system_file: str,
    subsystem_map: dict[str, dict] | None = None,
) -> dict | None:
    """Get info about the parent SubSystem block that contains this system file.

    Traverses the subsystem map to find which SubSystem block references the
    given system file via ``<System Ref="..."/>``.

    Args:
        model_dir:      Absolute path to the unzipped SLX model directory.
        system_file:    Relative system file path (e.g. ``simulink/systems/system_6.xml``).
        subsystem_map:  Pre-built map from :func:`build_subsystem_map`. If ``None``,
                        builds it automatically. Pass a pre-built map when calling
                        in a loop to avoid redundant XML parsing.

    Returns:
        Dict with parent SubSystem info::

            {
                "name":       str,   # SubSystem block name
                "sid":        str,   # SubSystem block SID
                "properties": dict,  # All <P> values on the SubSystem block
                "depth":      int,   # Depth of the parent subsystem (0 = root contains it)
            }

        Returns ``None`` for the root system file (``system_root.xml``) or if
        the parent cannot be determined.
    """
    if subsystem_map is None:
        subsystem_map = build_subsystem_map(model_dir)

    # Root has no parent
    meta = subsystem_map.get(system_file)
    if meta is None or meta["depth"] == 0:
        return None

    # Find the parent system file — the one whose full_path == this file's parent_path
    parent_file: str | None = None
    for sf, sf_meta in subsystem_map.items():
        if sf_meta["full_path"] == meta["parent_path"]:
            parent_file = sf
            break

    if parent_file is None:
        return None

    # Parse parent file and find the SubSystem block that references system_file
    cache: dict[str, etree._Element] = {}
    parent_root = _parse_xml(model_dir, parent_file, cache)
    if parent_root is None:
        return None

    # The system_file is "simulink/systems/system_N.xml" -> Ref is "system_N"
    expected_ref = Path(system_file).stem  # "system_6" from "simulink/systems/system_6.xml"

    for block in parent_root.findall("Block[@BlockType='SubSystem']"):
        system_elem = block.find("System")
        if system_elem is not None:
            ref = system_elem.get("Ref", "")
            if ref == expected_ref:
                # Extract all <P> properties
                properties: dict[str, str] = {}
                for p in block.findall("P"):
                    p_name = p.get("Name")
                    if p_name:
                        p_ref = p.get("Ref")
                        properties[p_name] = p_ref if p_ref else (p.text or "").strip()

                parent_meta = subsystem_map.get(parent_file, {})
                return {
                    "name": block.get("Name", "Unknown"),
                    "sid": block.get("SID", ""),
                    "properties": properties,
                    "depth": parent_meta.get("depth", 0),
                }

    return None


# ──────────────────────────────────────────────────────────────────────
# 7. trace_cross_subsystem
# ──────────────────────────────────────────────────────────────────────

def trace_cross_subsystem(
    model_dir: str,
    start_system_file: str,
    start_block_sid: str,
    direction: str = "both",
    max_depth: int = 10,
) -> list[dict]:
    """Trace signal connections across subsystem boundaries.

    Follows signals through Inport/Outport port-mapping and SubSystem
    boundaries, recursively traversing the hierarchy.

    Port mapping rules (Simulink standard):
      - Parent line ``Src=X#out:1 → Dst=SubSID#in:N`` maps to child
        ``Inport`` block with ``Port=N``.
      - Child ``Outport`` block with ``Port=M`` maps to parent line
        ``Src=SubSID#out:M → Dst=Y#in:1``.

    Args:
        model_dir:         Absolute path to the unzipped SLX model directory.
        start_system_file: System file containing the start block.
        start_block_sid:   SID of the block to start tracing from.
        direction:         ``"outgoing"``, ``"incoming"``, or ``"both"``.
        max_depth:         Maximum subsystem boundary crossings (prevents
                           infinite loops in circular models).

    Returns:
        List of trace steps, each a dict::

            {
                "block_name": str,       # Connected block name
                "block_sid":  str,       # Connected block SID
                "block_type": str,       # Block identity
                "block_path": str,       # Full hierarchy path
                "system_file": str,      # System file containing this block
                "depth":      int,       # Subsystem depth
                "direction":  str,       # "incoming" or "outgoing"
                "crossing":   str,       # "none", "into_subsystem", "out_to_parent"
            }

    Example::

        # Find all blocks downstream of Bus Creator at root
        trace = trace_cross_subsystem(
            model_dir, "simulink/systems/system_root.xml", "42", "outgoing"
        )
        for step in trace:
            print(f"{step['block_path']} ({step['block_type']}) [{step['crossing']}]")
    """
    cache: dict[str, etree._Element] = {}
    subsystem_map = build_subsystem_map(model_dir)
    visited: set[tuple[str, str]] = set()  # (system_file, sid) pairs
    results: list[dict] = []

    if direction in ("outgoing", "both"):
        _trace_recursive(
            model_dir, start_system_file, start_block_sid, "outgoing",
            max_depth, subsystem_map, cache, visited, results,
        )
    if direction in ("incoming", "both"):
        _trace_recursive(
            model_dir, start_system_file, start_block_sid, "incoming",
            max_depth, subsystem_map, cache, visited, results,
        )

    return results


def _trace_recursive(
    model_dir: str,
    system_file: str,
    block_sid: str,
    direction: str,
    remaining_depth: int,
    subsystem_map: dict[str, dict],
    cache: dict[str, etree._Element],
    visited: set[tuple[str, str]],
    results: list[dict],
) -> None:
    """Recursive cross-subsystem signal tracing."""
    if remaining_depth <= 0:
        return

    key = (system_file, block_sid)
    if key in visited:
        return
    visited.add(key)

    conns = get_connections(model_dir, system_file, block_sid)
    conn_list = conns.get(direction, [])
    meta = subsystem_map.get(system_file, {"full_path": "?", "depth": 0})

    root = _parse_xml(model_dir, system_file, cache)
    if root is None:
        return

    for conn in conn_list:
        conn_sid = conn["sid"]
        conn_type = conn["type"]
        conn_name = conn["name"]
        crossing = "none"

        step = {
            "block_name": conn_name,
            "block_sid": conn_sid,
            "block_type": conn_type,
            "block_path": f"{meta['full_path']}/{conn_name}",
            "system_file": system_file,
            "depth": meta["depth"],
            "direction": direction,
            "crossing": crossing,
        }

        if conn_type == "SubSystem" and direction == "outgoing":
            # Signal going INTO a subsystem -> find the child's Inport
            child_file = _find_child_system_file(root, conn_sid)
            if child_file:
                step["crossing"] = "into_subsystem"
                results.append(step)
                port_num = _find_port_number(root, block_sid, conn_sid, direction)
                inport_sid = _find_port_block(
                    model_dir, child_file, "Inport", port_num, cache,
                )
                if inport_sid:
                    _trace_recursive(
                        model_dir, child_file, inport_sid, direction,
                        remaining_depth - 1, subsystem_map, cache, visited, results,
                    )
                continue

        elif conn_type == "SubSystem" and direction == "incoming":
            # Signal coming FROM a subsystem -> find the child's Outport
            child_file = _find_child_system_file(root, conn_sid)
            if child_file:
                step["crossing"] = "into_subsystem"
                results.append(step)
                port_num = _find_port_number(root, conn_sid, block_sid, "outgoing")
                outport_sid = _find_port_block(
                    model_dir, child_file, "Outport", port_num, cache,
                )
                if outport_sid:
                    _trace_recursive(
                        model_dir, child_file, outport_sid, direction,
                        remaining_depth - 1, subsystem_map, cache, visited, results,
                    )
                continue

        elif conn_type == "Outport" and direction == "outgoing":
            # Signal leaving through Outport -> follow out to parent
            step["crossing"] = "out_to_parent"
            results.append(step)
            parent_info = _resolve_parent(
                model_dir, system_file, subsystem_map, cache,
            )
            if parent_info:
                parent_file = parent_info["parent_file"]
                sub_sid = parent_info["subsystem_sid"]
                if sub_sid:
                    _trace_recursive(
                        model_dir, parent_file, sub_sid, direction,
                        remaining_depth - 1, subsystem_map, cache, visited, results,
                    )
            continue

        elif conn_type == "Inport" and direction == "incoming":
            # Signal entering through Inport -> follow back to parent
            step["crossing"] = "out_to_parent"
            results.append(step)
            parent_info = _resolve_parent(
                model_dir, system_file, subsystem_map, cache,
            )
            if parent_info:
                parent_file = parent_info["parent_file"]
                sub_sid = parent_info["subsystem_sid"]
                if sub_sid:
                    _trace_recursive(
                        model_dir, parent_file, sub_sid, direction,
                        remaining_depth - 1, subsystem_map, cache, visited, results,
                    )
            continue

        # Normal same-level connection
        results.append(step)
        _trace_recursive(
            model_dir, system_file, conn_sid, direction,
            remaining_depth - 1, subsystem_map, cache, visited, results,
        )


def _find_child_system_file(root: etree._Element, subsystem_sid: str) -> str | None:
    """Find the child system file referenced by a SubSystem block."""
    for block in root.findall("Block[@BlockType='SubSystem']"):
        if block.get("SID") == subsystem_sid:
            system_elem = block.find("System")
            if system_elem is not None:
                ref = system_elem.get("Ref", "")
                if ref:
                    return f"simulink/systems/{ref}.xml"
    return None


def _find_port_block(
    model_dir: str,
    system_file: str,
    port_type: str,
    port_num: str,
    cache: dict[str, etree._Element],
) -> str | None:
    """Find the SID of an Inport/Outport block by its Port number."""
    root = _parse_xml(model_dir, system_file, cache)
    if root is None:
        return None

    for block in root.findall(f"Block[@BlockType='{port_type}']"):
        port_p = block.xpath("P[@Name='Port']")
        block_port = "1"
        if port_p and port_p[0].text:
            block_port = port_p[0].text.strip()
        if block_port == port_num:
            return block.get("SID", "")

    return None


def _find_port_number(
    root: etree._Element,
    src_sid: str,
    dst_sid: str,
    direction: str,
) -> str:
    """Extract port number from Line connecting src to dst."""
    for line in root.findall("Line"):
        src_text = _get_p_text(line, "Src")
        dsts = _collect_destinations(line)

        line_src_sid = src_text.split("#")[0] if "#" in src_text else src_text

        if direction == "outgoing" and line_src_sid == src_sid:
            for dst in dsts:
                dst_parts = dst.split("#")
                if dst_parts[0] == dst_sid and len(dst_parts) > 1:
                    port_spec = dst_parts[1]  # "in:1"
                    if ":" in port_spec:
                        return port_spec.split(":")[1]

    return "1"


def _resolve_parent(
    model_dir: str,
    system_file: str,
    subsystem_map: dict[str, dict],
    cache: dict[str, etree._Element],
) -> dict | None:
    """Find the parent system file and the SubSystem SID that references this file."""
    meta = subsystem_map.get(system_file)
    if meta is None or meta["depth"] == 0:
        return None

    parent_file: str | None = None
    for sf, sf_meta in subsystem_map.items():
        if sf_meta["full_path"] == meta["parent_path"]:
            parent_file = sf
            break

    if parent_file is None:
        return None

    parent_root = _parse_xml(model_dir, parent_file, cache)
    if parent_root is None:
        return None

    expected_ref = Path(system_file).stem
    for block in parent_root.findall("Block[@BlockType='SubSystem']"):
        system_elem = block.find("System")
        if system_elem is not None and system_elem.get("Ref", "") == expected_ref:
            return {
                "parent_file": parent_file,
                "subsystem_sid": block.get("SID", ""),
            }

    return None
