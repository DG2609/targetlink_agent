# Code Templates

3 templates cho 3 loại rule khác nhau. Chọn template phù hợp nhất rồi thay thế placeholders.

## Template — Config Check Rule

Dùng khi rule check 1 property cụ thể (VD: "Gain phải có SaturateOnIntegerOverflow=on"):

```python
"""
Auto-generated rule check: {rule_id}
"""
from lxml import etree
import json
import sys
import os
from pathlib import Path

# Import block_finder — xử lý cả 3 dạng XML (native/reference/masked)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.block_finder import find_blocks, get_block_config


def check_rule(model_dir: str) -> dict:
    systems_dir = os.path.join(model_dir, "simulink", "systems")
    results = {"pass": [], "fail": []}

    # Get default value from bddefaults.xml
    default_val = "{DEFAULT_VALUE}"
    bd_path = os.path.join(model_dir, "simulink", "bddefaults.xml")
    if os.path.exists(bd_path):
        try:
            bd_tree = etree.parse(bd_path)
            bd_root = bd_tree.getroot()
            node = bd_root.xpath(
                ".//BlockParameterDefaults/Block[@BlockType='{BLOCK_TYPE}']/P[@Name='{CONFIG_NAME}']"
            )
            if node and node[0].text is not None:
                default_val = node[0].text.strip()
        except Exception:
            pass

    for xml_file in sorted(Path(systems_dir).glob("system_*.xml")):
        tree = etree.parse(str(xml_file))
        root = tree.getroot()

        blocks = find_blocks(root, "{BLOCK_IDENTIFIER}")

        for block in blocks:
            name = block.get("Name", "Unknown")
            sid = block.get("SID", "")
            path = f"{xml_file.stem}/{name}"

            value = get_block_config(block, "{CONFIG_NAME}", default_val)

            if {DIEU_KIEN_CHECK}:
                results["pass"].append({"block_name": name, "block_path": path, "value": value})
            else:
                results["fail"].append({"block_name": name, "block_path": path, "value": value})

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

## Template — Forbidden Block Rule

Dùng khi rule cấm dùng 1 số block types (VD: "không được dùng block Buffer, Product"):

```python
"""
Auto-generated rule check: {rule_id}
Forbidden blocks: {FORBIDDEN_LIST}
"""
from lxml import etree
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.block_finder import find_all_blocks, get_block_identity


FORBIDDEN_TYPES = {FORBIDDEN_SET}  # VD: {"Buffer", "Product", "Logic"}


def check_rule(model_dir: str) -> dict:
    systems_dir = os.path.join(model_dir, "simulink", "systems")
    results = {"pass": [], "fail": []}

    for xml_file in sorted(Path(systems_dir).glob("system_*.xml")):
        tree = etree.parse(str(xml_file))
        root = tree.getroot()

        for block in find_all_blocks(root):
            identity = get_block_identity(block)
            name = block.get("Name", "Unknown")
            path = f"{xml_file.stem}/{name}"

            if identity in FORBIDDEN_TYPES:
                results["fail"].append({
                    "block_name": name,
                    "block_path": path,
                    "value": f"forbidden block type: {identity}",
                })
            else:
                results["pass"].append({
                    "block_name": name,
                    "block_path": path,
                    "value": identity,
                })

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

## Template — Config-Only Rule (không nói rõ block type)

Dùng khi rule chỉ nói config mà không nói block nào (VD: "SaturateOnIntegerOverflow phải on").
Code dùng `find_blocks_with_config` để tìm tất cả blocks có config đó:

```python
"""
Auto-generated rule check: {rule_id}
Config: {CONFIG_NAME} — check trên tất cả block types có config này
"""
from lxml import etree
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.block_finder import find_blocks_with_config, get_block_identity, get_block_config


def check_rule(model_dir: str) -> dict:
    systems_dir = os.path.join(model_dir, "simulink", "systems")
    results = {"pass": [], "fail": []}

    # Get defaults per block type from bddefaults.xml
    defaults = {}  # {block_type: default_value}
    bd_path = os.path.join(model_dir, "simulink", "bddefaults.xml")
    if os.path.exists(bd_path):
        try:
            bd_tree = etree.parse(bd_path)
            bd_root = bd_tree.getroot()
            for block_def in bd_root.xpath(".//BlockParameterDefaults/Block"):
                bt = block_def.get("BlockType", "")
                node = block_def.find("P[@Name='{CONFIG_NAME}']")
                if node is not None and node.text is not None:
                    defaults[bt] = node.text.strip()
        except Exception:
            pass

    for xml_file in sorted(Path(systems_dir).glob("system_*.xml")):
        tree = etree.parse(str(xml_file))
        root = tree.getroot()

        for block in find_blocks_with_config(root, "{CONFIG_NAME}"):
            identity = get_block_identity(block)
            name = block.get("Name", "Unknown")
            path = f"{xml_file.stem}/{name}"
            bt = block.get("BlockType", "")
            default_val = defaults.get(bt)

            value = get_block_config(block, "{CONFIG_NAME}", default_val)

            if {DIEU_KIEN_CHECK}:
                results["pass"].append({
                    "block_name": name,
                    "block_path": path,
                    "value": f"{value} ({identity})",
                })
            else:
                results["fail"].append({
                    "block_name": name,
                    "block_path": path,
                    "value": f"{value} ({identity})",
                })

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

## Template — Hierarchy-Aware Rule (Level 3)

Dùng khi rule cần check blocks xuyên mọi subsystem levels với full hierarchy path.
Dùng `utils.hierarchy_utils.walk_blocks()` thay vì iterate files thủ công:

```python
"""
Auto-generated rule check: {rule_id}
Level 3: Hierarchy-aware — full subsystem path in output
"""
from lxml import etree
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.hierarchy_utils import walk_blocks, build_subsystem_map
from utils.block_finder import get_block_config


def check_rule(model_dir: str) -> dict:
    results = {"pass": [], "fail": []}

    # Get default value from bddefaults.xml
    default_val = "{DEFAULT_VALUE}"
    bd_path = os.path.join(model_dir, "simulink", "bddefaults.xml")
    if os.path.exists(bd_path):
        try:
            bd_tree = etree.parse(bd_path)
            bd_root = bd_tree.getroot()
            node = bd_root.xpath(
                ".//BlockParameterDefaults/Block[@BlockType='{BLOCK_TYPE}']/P[@Name='{CONFIG_NAME}']"
            )
            if node and node[0].text is not None:
                default_val = node[0].text.strip()
        except Exception:
            pass

    # walk_blocks tìm tất cả blocks xuyên mọi subsystem levels
    blocks = walk_blocks(model_dir, "{BLOCK_IDENTIFIER}")

    for block_info in blocks:
        name = block_info["name"]
        block_path = block_info["block_path"]  # "Root/Lowpass Filter/s(1)"
        sid = block_info["sid"]
        depth = block_info["depth"]
        system_file = block_info["system_file"]

        # Parse XML to get the actual block element for config reading
        tree = etree.parse(os.path.join(model_dir, system_file))
        root = tree.getroot()
        block_elem = root.xpath(f".//Block[@SID='{sid}']")
        if not block_elem:
            continue
        block = block_elem[0]

        value = get_block_config(block, "{CONFIG_NAME}", default_val)

        entry = {
            "block_name": name,
            "block_path": block_path,
            "block_sid": sid,
            "depth": depth,
            "value": value,
        }

        if {DIEU_KIEN_CHECK}:
            results["pass"].append(entry)
        else:
            results["fail"].append(entry)

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

## Template — Connection-Based Rule (Level 4)

Dùng khi rule phụ thuộc signal flow (VD: "Gain nối với Outport phải có config X"):

```python
"""
Auto-generated rule check: {rule_id}
Level 4: Connection-based — checks blocks based on signal connections
"""
from lxml import etree
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.hierarchy_utils import walk_blocks, get_connections
from utils.block_finder import get_block_config


def check_rule(model_dir: str) -> dict:
    results = {"pass": [], "fail": []}

    blocks = walk_blocks(model_dir, "{BLOCK_IDENTIFIER}")

    for block_info in blocks:
        name = block_info["name"]
        block_path = block_info["block_path"]
        sid = block_info["sid"]
        system_file = block_info["system_file"]

        # Get connections for this block
        conns = get_connections(model_dir, system_file, sid)
        connected_types = [c["type"] for c in conns.get("{DIRECTION}", [])]

        # Rule only applies to blocks connected to target
        if "{TARGET_BLOCK_TYPE}" not in connected_types:
            continue

        # Parse block element for config reading
        tree = etree.parse(os.path.join(model_dir, system_file))
        root = tree.getroot()
        block_elem = root.xpath(f".//Block[@SID='{sid}']")
        if not block_elem:
            continue
        block = block_elem[0]

        value = get_block_config(block, "{CONFIG_NAME}", "{DEFAULT_VALUE}")

        entry = {
            "block_name": name,
            "block_path": block_path,
            "block_sid": sid,
            "value": value,
            "connected_to": ", ".join(f"{c['name']} ({c['type']})" for c in conns.get("{DIRECTION}", [])),
        }

        if {DIEU_KIEN_CHECK}:
            results["pass"].append(entry)
        else:
            results["fail"].append(entry)

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

## Template — Cross-Subsystem Connection Rule (Level 4 variant)

Dùng khi rule check connection xuyên subsystem boundary (VD: "Bus Creator ở root nối Bus Selector ở depth 4-5"):

```python
"""
Auto-generated rule check: {rule_id}
Level 4: Cross-subsystem connection — traces signals across SubSystem boundaries
"""
from lxml import etree
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.hierarchy_utils import walk_blocks, trace_cross_subsystem
from utils.block_finder import get_block_config


def check_rule(model_dir: str) -> dict:
    results = {"pass": [], "fail": []}

    source_blocks = walk_blocks(model_dir, "{SOURCE_BLOCK_TYPE}")

    for block_info in source_blocks:
        name = block_info["name"]
        block_path = block_info["block_path"]
        sid = block_info["sid"]
        depth = block_info["depth"]
        system_file = block_info["system_file"]

        # Trace signal downstream across subsystem boundaries
        trace = trace_cross_subsystem(
            model_dir, system_file, sid, "{DIRECTION}", max_depth=10,
        )

        # Check if target block type appears in the trace
        target_steps = [
            s for s in trace if s["block_type"] == "{TARGET_BLOCK_TYPE}"
        ]

        if not target_steps:
            continue  # Rule only applies when source connects to target

        for target in target_steps:
            entry = {
                "block_name": name,
                "block_path": block_path,
                "block_sid": sid,
                "source_depth": depth,
                "target_name": target["block_name"],
                "target_path": target["block_path"],
                "target_depth": target["depth"],
                "value": f"connected via {target['crossing']}",
            }

            if {DIEU_KIEN_CHECK}:
                results["pass"].append(entry)
            else:
                results["fail"].append(entry)

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

## Template — Contextual Rule (Level 5)

Dùng khi rule phụ thuộc parent subsystem context (VD: "Blocks trong filter subsystem phải config khác"):

```python
"""
Auto-generated rule check: {rule_id}
Level 5: Contextual — rule depends on parent subsystem properties
"""
from lxml import etree
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.hierarchy_utils import walk_blocks, build_subsystem_map, get_parent_subsystem_info
from utils.block_finder import get_block_config


def check_rule(model_dir: str) -> dict:
    results = {"pass": [], "fail": []}

    # Pre-build subsystem map once (avoid rebuilding per block)
    sub_map = build_subsystem_map(model_dir)

    blocks = walk_blocks(model_dir, "{BLOCK_IDENTIFIER}")

    for block_info in blocks:
        name = block_info["name"]
        block_path = block_info["block_path"]
        sid = block_info["sid"]
        depth = block_info["depth"]
        system_file = block_info["system_file"]
        parent_sub = block_info.get("parent_subsystem", "")

        # Get parent subsystem context (reuses pre-built map)
        parent_info = get_parent_subsystem_info(model_dir, system_file, sub_map)

        # Apply context filter: only check blocks matching parent pattern
        if parent_info is not None:
            parent_name = parent_info.get("name", "")
            if not {PARENT_FILTER_CONDITION}:
                continue  # Skip blocks not in target context
        else:
            # Block is at root level — decide based on rule
            {ROOT_LEVEL_HANDLING}

        # Parse block element for config reading
        tree = etree.parse(os.path.join(model_dir, system_file))
        root = tree.getroot()
        block_elem = root.xpath(f".//Block[@SID='{sid}']")
        if not block_elem:
            continue
        block = block_elem[0]

        value = get_block_config(block, "{CONFIG_NAME}", "{DEFAULT_VALUE}")

        entry = {
            "block_name": name,
            "block_path": block_path,
            "block_sid": sid,
            "depth": depth,
            "value": value,
            "parent_subsystem": parent_sub,
        }

        if {DIEU_KIEN_CHECK}:
            results["pass"].append(entry)
        else:
            results["fail"].append(entry)

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```
