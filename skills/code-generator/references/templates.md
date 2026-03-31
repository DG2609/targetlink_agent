# Code Templates

3 templates cho 3 loại rule khác nhau. Chọn template phù hợp nhất rồi thay thế placeholders.

## Quy tắc bắt buộc cho MỌI template

1. **Luôn gọi `extract_slx(model_dir)` ở đầu `check_rule()`** — xử lý cả `.slx` file lẫn thư mục đã extract.
2. **Dùng `defaults_parser.get_default_value()`** — không tự parse bddefaults.xml bằng tay.
3. **Safe SID lookup** — KHÔNG dùng `root.xpath(f".//Block[@SID='{sid}']")` (XPath injection nếu SID chứa ký tự đặc biệt). Dùng `_find_block_by_sid()` helper bên dưới.
4. **XML caching** — declare `xml_cache: dict = {}` trong `check_rule()`, share giữa các blocks để tránh re-parse cùng 1 file.
5. **Proper error handling** — `except etree.XMLSyntaxError as e: print(warning, file=sys.stderr)`, KHÔNG `except Exception: pass`.
6. **Check `systems_dir` exists** trước khi glob.
7. **Argv bounds check** — `if len(sys.argv) < 2: sys.exit(1)`.

### Helper function (copy vào MỌI script dùng walk_blocks)

```python
def _find_block_by_sid(root, sid: str):
    """Safe SID lookup — attribute comparison, không XPath f-string."""
    for block in root.iter("Block"):
        if block.get("SID") == sid:
            return block
    return None
```

---

## Template — Config Check Rule (Level 1-2)

Dùng khi rule check 1 property cụ thể trên 1 block type, flat scan (không cần hierarchy):

```python
"""
Auto-generated rule check: {rule_id}
Rule: {rule_description}
"""
import json
import sys
import os
from pathlib import Path
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.block_finder import find_blocks, get_block_config
from utils.defaults_parser import get_default_value
from utils.slx_extractor import extract_slx


def check_rule(model_dir: str) -> dict:
    # Auto-extract .slx nếu được truyền file path (xử lý cả 2 trường hợp)
    model_dir = extract_slx(model_dir)
    systems_dir = os.path.join(model_dir, "simulink", "systems")
    results = {"pass": [], "fail": []}

    if not os.path.isdir(systems_dir):
        print(f"[{rule_id}] Warning: systems dir not found: {systems_dir}", file=sys.stderr)
        return {"rule_id": "{rule_id}", "total_blocks": 0, "pass_count": 0, "fail_count": 0, "details": results}

    # Lấy default value từ bddefaults.xml (cached sau lần đầu)
    default_val = get_default_value(model_dir, "{BLOCK_TYPE}", "{CONFIG_NAME}") or "{DEFAULT_VALUE}"

    for xml_file in sorted(Path(systems_dir).glob("system_*.xml")):
        try:
            tree = etree.parse(str(xml_file))
            root = tree.getroot()
        except etree.XMLSyntaxError as e:
            print(f"[{rule_id}] Warning: failed to parse {xml_file.name}: {e}", file=sys.stderr)
            continue

        for block in find_blocks(root, "{BLOCK_IDENTIFIER}"):
            name = block.get("Name", "Unknown")
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
    if len(sys.argv) < 2:
        print("Usage: python check_rule_{rule_id}.py <model_dir_or_slx>")
        sys.exit(1)
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

---

## Template — Forbidden Block Rule

Dùng khi rule cấm dùng 1 số block types:

```python
"""
Auto-generated rule check: {rule_id}
Forbidden blocks: {FORBIDDEN_LIST}
"""
import json
import sys
import os
from pathlib import Path
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.block_finder import find_all_blocks, get_block_identity
from utils.slx_extractor import extract_slx


FORBIDDEN_TYPES = {FORBIDDEN_SET}  # VD: {"Buffer", "Product", "Logic"}


def check_rule(model_dir: str) -> dict:
    model_dir = extract_slx(model_dir)
    systems_dir = os.path.join(model_dir, "simulink", "systems")
    results = {"pass": [], "fail": []}

    if not os.path.isdir(systems_dir):
        print(f"[{rule_id}] Warning: systems dir not found: {systems_dir}", file=sys.stderr)
        return {"rule_id": "{rule_id}", "total_blocks": 0, "pass_count": 0, "fail_count": 0, "details": results}

    for xml_file in sorted(Path(systems_dir).glob("system_*.xml")):
        try:
            tree = etree.parse(str(xml_file))
            root = tree.getroot()
        except etree.XMLSyntaxError as e:
            print(f"[{rule_id}] Warning: failed to parse {xml_file.name}: {e}", file=sys.stderr)
            continue

        for block in find_all_blocks(root):
            identity = get_block_identity(block)
            name = block.get("Name", "Unknown")
            path = f"{xml_file.stem}/{name}"

            if identity in FORBIDDEN_TYPES:
                results["fail"].append({"block_name": name, "block_path": path, "value": f"forbidden block type: {identity}"})
            else:
                results["pass"].append({"block_name": name, "block_path": path, "value": identity})

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_rule_{rule_id}.py <model_dir_or_slx>")
        sys.exit(1)
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

---

## Template — Config-Only Rule (không nói rõ block type)

```python
"""
Auto-generated rule check: {rule_id}
Config: {CONFIG_NAME} — check trên tất cả block types có config này
"""
import json
import sys
import os
from pathlib import Path
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.block_finder import find_blocks_with_config, get_block_identity, get_block_config
from utils.defaults_parser import get_default_value
from utils.slx_extractor import extract_slx


def check_rule(model_dir: str) -> dict:
    model_dir = extract_slx(model_dir)
    systems_dir = os.path.join(model_dir, "simulink", "systems")
    results = {"pass": [], "fail": []}

    if not os.path.isdir(systems_dir):
        print(f"[{rule_id}] Warning: systems dir not found: {systems_dir}", file=sys.stderr)
        return {"rule_id": "{rule_id}", "total_blocks": 0, "pass_count": 0, "fail_count": 0, "details": results}

    for xml_file in sorted(Path(systems_dir).glob("system_*.xml")):
        try:
            tree = etree.parse(str(xml_file))
            root = tree.getroot()
        except etree.XMLSyntaxError as e:
            print(f"[{rule_id}] Warning: failed to parse {xml_file.name}: {e}", file=sys.stderr)
            continue

        for block in find_blocks_with_config(root, "{CONFIG_NAME}"):
            identity = get_block_identity(block)
            name = block.get("Name", "Unknown")
            path = f"{xml_file.stem}/{name}"
            # Lấy default theo block type thực tế
            # Use true identity (MaskType > SourceType > BlockType) for correct defaults lookup
            default_val = get_default_value(model_dir, identity, "{CONFIG_NAME}")
            value = get_block_config(block, "{CONFIG_NAME}", default_val)

            if {DIEU_KIEN_CHECK}:
                results["pass"].append({"block_name": name, "block_path": path, "value": value, "block_type": identity})
            else:
                results["fail"].append({"block_name": name, "block_path": path, "value": value, "block_type": identity})

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_rule_{rule_id}.py <model_dir_or_slx>")
        sys.exit(1)
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

---

## Template — Hierarchy-Aware Rule (Level 3)

Dùng khi rule cần check blocks xuyên mọi subsystem levels:

```python
"""
Auto-generated rule check: {rule_id}
Level 3: Hierarchy-aware — full subsystem path in output
"""
import json
import sys
import os
from pathlib import Path
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.hierarchy_utils import walk_blocks
from utils.block_finder import get_block_config
from utils.defaults_parser import get_default_value
from utils.slx_extractor import extract_slx


def _find_block_by_sid(root, sid: str):
    """Safe SID lookup — attribute comparison, không XPath f-string."""
    for block in root.iter("Block"):
        if block.get("SID") == sid:
            return block
    return None


def check_rule(model_dir: str) -> dict:
    model_dir = extract_slx(model_dir)
    results = {"pass": [], "fail": []}

    default_val = get_default_value(model_dir, "{BLOCK_TYPE}", "{CONFIG_NAME}") or "{DEFAULT_VALUE}"

    blocks = walk_blocks(model_dir, "{BLOCK_IDENTIFIER}")
    if not blocks:
        return {"rule_id": "{rule_id}", "total_blocks": 0, "pass_count": 0, "fail_count": 0, "details": results}

    # XML cache — tránh re-parse cùng 1 file cho nhiều blocks
    xml_cache: dict[str, etree._Element] = {}

    for block_info in blocks:
        name = block_info["name"]
        block_path = block_info["block_path"]  # "Root/Lowpass Filter/s(1)"
        sid = block_info["sid"]
        depth = block_info["depth"]
        system_file = block_info["system_file"]

        try:
            if system_file not in xml_cache:
                xml_cache[system_file] = etree.parse(os.path.join(model_dir, system_file)).getroot()
            root = xml_cache[system_file]

            block_elem = _find_block_by_sid(root, sid)
            if block_elem is None:
                print(f"[{rule_id}] Warning: block SID={sid} not found in {system_file}", file=sys.stderr)
                continue

            value = get_block_config(block_elem, "{CONFIG_NAME}", default_val)
            entry = {"block_name": name, "block_path": block_path, "block_sid": sid, "depth": depth, "value": value}

            if {DIEU_KIEN_CHECK}:
                results["pass"].append(entry)
            else:
                results["fail"].append(entry)

        except etree.XMLSyntaxError as e:
            print(f"[{rule_id}] Warning: failed to parse {system_file}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[{rule_id}] Warning: error processing block {name} (SID={sid}): {e}", file=sys.stderr)

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_rule_{rule_id}.py <model_dir_or_slx>")
        sys.exit(1)
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

---

## Template — Connection-Based Rule (Level 4)

Dùng khi rule phụ thuộc signal flow:

```python
"""
Auto-generated rule check: {rule_id}
Level 4: Connection-based — checks blocks based on signal connections
"""
import json
import sys
import os
from pathlib import Path
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.hierarchy_utils import walk_blocks, get_connections
from utils.block_finder import get_block_config
from utils.defaults_parser import get_default_value
from utils.slx_extractor import extract_slx


def _find_block_by_sid(root, sid: str):
    """Safe SID lookup — attribute comparison, không XPath f-string."""
    for block in root.iter("Block"):
        if block.get("SID") == sid:
            return block
    return None


def check_rule(model_dir: str) -> dict:
    model_dir = extract_slx(model_dir)
    results = {"pass": [], "fail": []}

    default_val = get_default_value(model_dir, "{BLOCK_TYPE}", "{CONFIG_NAME}") or "{DEFAULT_VALUE}"

    blocks = walk_blocks(model_dir, "{BLOCK_IDENTIFIER}")
    if not blocks:
        return {"rule_id": "{rule_id}", "total_blocks": 0, "pass_count": 0, "fail_count": 0, "details": results}

    # XML cache — shared across blocks
    xml_cache: dict[str, etree._Element] = {}

    for block_info in blocks:
        name = block_info["name"]
        block_path = block_info["block_path"]
        sid = block_info["sid"]
        system_file = block_info["system_file"]

        try:
            conns = get_connections(model_dir, system_file, sid)
            connected_types = [c.get("type", "") for c in conns.get("{DIRECTION}", [])]

            if "{TARGET_BLOCK_TYPE}" not in connected_types:
                continue  # Rule only applies when block connects to target

            if system_file not in xml_cache:
                xml_cache[system_file] = etree.parse(os.path.join(model_dir, system_file)).getroot()
            root = xml_cache[system_file]

            block_elem = _find_block_by_sid(root, sid)
            if block_elem is None:
                continue

            value = get_block_config(block_elem, "{CONFIG_NAME}", default_val)
            # Numeric comparison (use float() for greater_than/less_than etc.)
            try:
                numeric_val = float(value) if value is not None else None
            except (ValueError, TypeError):
                numeric_val = None

            entry = {
                "block_name": name,
                "block_path": block_path,
                "block_sid": sid,
                "value": value,
                "connected_to": ", ".join(f"{c.get('name','?')} ({c.get('type','?')})" for c in conns.get("{DIRECTION}", [])),
            }

            if {DIEU_KIEN_CHECK}:
                results["pass"].append(entry)
            else:
                results["fail"].append(entry)

        except etree.XMLSyntaxError as e:
            print(f"[{rule_id}] Warning: failed to parse {system_file}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[{rule_id}] Warning: error processing block {name} (SID={sid}): {e}", file=sys.stderr)

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_rule_{rule_id}.py <model_dir_or_slx>")
        sys.exit(1)
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

---

## Template — Cross-Subsystem Connection Rule (Level 4 variant)

```python
"""
Auto-generated rule check: {rule_id}
Level 4: Cross-subsystem connection
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.hierarchy_utils import walk_blocks, trace_cross_subsystem
from utils.block_finder import get_block_config
from utils.slx_extractor import extract_slx


def check_rule(model_dir: str) -> dict:
    model_dir = extract_slx(model_dir)
    results = {"pass": [], "fail": []}

    source_blocks = walk_blocks(model_dir, "{SOURCE_BLOCK_TYPE}")
    if not source_blocks:
        return {"rule_id": "{rule_id}", "total_blocks": 0, "pass_count": 0, "fail_count": 0, "details": results}

    for block_info in source_blocks:
        name = block_info["name"]
        block_path = block_info["block_path"]
        sid = block_info["sid"]
        depth = block_info["depth"]
        system_file = block_info["system_file"]

        try:
            trace = trace_cross_subsystem(model_dir, system_file, sid, "{DIRECTION}", max_depth=10)
            target_steps = [s for s in trace if s["block_type"] == "{TARGET_BLOCK_TYPE}"]

            if not target_steps:
                continue

            for target in target_steps:
                entry = {
                    "block_name": name, "block_path": block_path, "block_sid": sid,
                    "source_depth": depth, "target_name": target["block_name"],
                    "target_path": target["block_path"], "target_depth": target["depth"],
                    "value": f"connected via {target['crossing']}",
                }
                if {DIEU_KIEN_CHECK}:
                    results["pass"].append(entry)
                else:
                    results["fail"].append(entry)

        except Exception as e:
            print(f"[{rule_id}] Warning: error processing block {name} (SID={sid}): {e}", file=sys.stderr)

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_rule_{rule_id}.py <model_dir_or_slx>")
        sys.exit(1)
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

---

## Template — Contextual Rule (Level 5)

```python
"""
Auto-generated rule check: {rule_id}
Level 5: Contextual — rule depends on parent subsystem properties
"""
import json
import sys
import os
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.hierarchy_utils import walk_blocks, build_subsystem_map, get_parent_subsystem_info
from utils.block_finder import get_block_config
from utils.defaults_parser import get_default_value
from utils.slx_extractor import extract_slx


def _find_block_by_sid(root, sid: str):
    """Safe SID lookup — attribute comparison, không XPath f-string."""
    for block in root.iter("Block"):
        if block.get("SID") == sid:
            return block
    return None


def check_rule(model_dir: str) -> dict:
    model_dir = extract_slx(model_dir)
    results = {"pass": [], "fail": []}

    default_val = get_default_value(model_dir, "{BLOCK_TYPE}", "{CONFIG_NAME}") or "{DEFAULT_VALUE}"

    blocks = walk_blocks(model_dir, "{BLOCK_IDENTIFIER}")
    if not blocks:
        return {"rule_id": "{rule_id}", "total_blocks": 0, "pass_count": 0, "fail_count": 0, "details": results}

    # Build subsystem map ONCE — avoid O(N×M) re-parses
    sub_map = build_subsystem_map(model_dir)
    # XML cache — shared across blocks
    xml_cache: dict[str, etree._Element] = {}

    for block_info in blocks:
        name = block_info["name"]
        block_path = block_info["block_path"]
        sid = block_info["sid"]
        depth = block_info["depth"]
        system_file = block_info["system_file"]
        parent_sub = block_info.get("parent_subsystem", "")

        # Get parent context (reuses pre-built sub_map)
        parent_info = get_parent_subsystem_info(model_dir, system_file, sub_map)

        if parent_info is not None:
            parent_name = parent_info.get("name", "")
            if not {PARENT_FILTER_CONDITION}:
                continue
        else:
            # Root level — skip (rule only applies inside subsystems)
            {ROOT_LEVEL_HANDLING}

        try:
            if system_file not in xml_cache:
                xml_cache[system_file] = etree.parse(os.path.join(model_dir, system_file)).getroot()
            root = xml_cache[system_file]

            block_elem = _find_block_by_sid(root, sid)
            if block_elem is None:
                print(f"[{rule_id}] Warning: block SID={sid} not found in {system_file}", file=sys.stderr)
                continue

            value = get_block_config(block_elem, "{CONFIG_NAME}", default_val)
            entry = {
                "block_name": name, "block_path": block_path, "block_sid": sid,
                "depth": depth, "value": value, "parent_subsystem": parent_sub,
            }

            if {DIEU_KIEN_CHECK}:
                results["pass"].append(entry)
            else:
                results["fail"].append(entry)

        except etree.XMLSyntaxError as e:
            print(f"[{rule_id}] Warning: failed to parse {system_file}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[{rule_id}] Warning: error processing block {name} (SID={sid}): {e}", file=sys.stderr)

    return {
        "rule_id": "{rule_id}",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_rule_{rule_id}.py <model_dir_or_slx>")
        sys.exit(1)
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```


## Template — Model-Level Rule (Solver / CodeGen settings)

Dùng khi: `rule_type = "model_level"` — kiểm tra model settings (solver, code gen, optimization). KHÔNG tìm blocks, không import block_finder.

```python
"""
Auto-generated rule check: {rule_id}
Model-level rule: {CONFIG_CLASS}.{SETTING_NAME} phai bang '{EXPECTED_VALUE}'
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.slx_extractor import extract_slx
from utils.config_reader import read_config_setting, list_config_components


def check_rule(model_dir: str) -> dict:
    model_dir = extract_slx(model_dir)

    actual = read_config_setting(model_dir, "{CONFIG_CLASS}", "{SETTING_NAME}")

    if actual is None:
        available = list_config_components(model_dir)
        return {
            "rule_id": "{rule_id}",
            "total_blocks": 1,
            "pass_count": 0,
            "fail_count": 1,
            "details": {
                "pass": [],
                "fail": [{
                    "setting": "{SETTING_NAME}",
                    "class": "{CONFIG_CLASS}",
                    "value": None,
                    "expected": "{EXPECTED_VALUE}",
                    "note": f"Setting not found. Available classes: {available}",
                }],
            },
        }

    passed = actual == "{EXPECTED_VALUE}"
    entry = {
        "setting": "{SETTING_NAME}",
        "class": "{CONFIG_CLASS}",
        "value": actual,
        "expected": "{EXPECTED_VALUE}",
    }

    return {
        "rule_id": "{rule_id}",
        "total_blocks": 1,
        "pass_count": 1 if passed else 0,
        "fail_count": 0 if passed else 1,
        "details": {
            "pass": [entry] if passed else [],
            "fail": [] if passed else [entry],
        },
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_rule_{rule_id}.py <model_dir_or_slx>")
        sys.exit(1)
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

**Notes:** `CONFIG_CLASS`: "Simulink.RTWCC" / "Simulink.SolverCC" / "Simulink.OptimizationCC" / "Simulink.HardwareCC" / "Simulink.DataIOCC". `total_blocks=1` vi model co 1 configSet, khong phai per-block.
