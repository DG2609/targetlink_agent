# Code Templates

3 templates cho 3 loại rule khác nhau. Chọn template phù hợp nhất rồi thay thế placeholders.

## Template code — Config Check Rule

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

# BẮT BUỘC import — tìm block đúng cách bất kể dạng XML
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.block_finder import find_blocks, get_block_config


def check_rule(model_dir: str) -> dict:
    systems_dir = os.path.join(model_dir, "simulink", "systems")
    results = {"pass": [], "fail": []}

    # (Optional) Get default value from bddefaults.xml
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

        # find_blocks tự search cả BlockType, MaskType, SourceType
        blocks = find_blocks(root, "{BLOCK_IDENTIFIER}")

        for block in blocks:
            name = block.get("Name", "Unknown")
            sid = block.get("SID", "")
            path = f"{xml_file.stem}/{name}"

            # get_block_config tự check cả direct <P> lẫn <InstanceData>/<P>
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

## Template code — Forbidden Block Rule

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

## Template code — Config-Only Rule (không nói rõ block type)

Dùng khi rule chỉ nói config mà KHÔNG nói block nào (VD: "SaturateOnIntegerOverflow phải on").
Code phải dùng `find_blocks_with_config` để tìm TẤT CẢ blocks có config đó:

```python
"""
Auto-generated rule check: {rule_id}
Config: {CONFIG_NAME} — check trên TẤT CẢ block types có config này
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

        # Tìm TẤT CẢ blocks có config này (bất kể block type)
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
