# Agent Input/Output Specification

Mỗi agent có **input**, **output**, và **example** cụ thể.
Document này là nguồn chính thức — code PHẢI tuân thủ spec này.

---

## Tổng quan luồng dữ liệu

```
rules.json ─────────────────────────────────────────────────────────────┐
                                                                        │
  rule.description (str)                                                │
        │                                                               │
        ▼                                                               │
  ┌──────────────┐    ParsedRule                                        │
  │   Agent 0    │──────────────┐                                       │
  │ Rule Analyzer│              │                                       │
  └──────────────┘              │                                       │
                                ▼                                       │
blocks.json ───────────▶ ┌──────────────┐    BlockMappingData           │
                         │   Agent 1    │──────────────┐                │
                         │ Data Reader  │              │                │
                         └──────────────┘              │                │
                                                       ▼                │
model_before.slx ──────▶ ┌──────────────┐    ConfigDiscovery (opt)     │
  (optional)             │  Agent 1.5   │──────────────┐               │
                         │Diff Analyzer │              │               │
                         └──────────────┘              │               │
                                                       ▼               │
model.slx ─────────────▶ ┌──────────────┐    check_rule_RXXX.py       │
                         │   Agent 2    │──────────────┐               │
                         │Code Generator│              │               │
                         └──────────────┘              │               │
                                                       ▼               │
expected_results.json ──▶ ┌──────────────┐    ValidationResult     ◄───┘
                         │   Agent 3    │──────────────┐
                         │  Validator   │              │
                         └──────────────┘              │
                                                       ▼
                                              ┌─── PASS ──── DONE
                                              │
                                              ├─── CODE_ERROR ──▶ Agent 4 ──▶ Agent 3 (re-validate)
                                              │
                                              └─── WRONG_RESULT / PARTIAL_PASS ──▶ Agent 5 ──▶ Agent 3
```

---

## Agent 0: Rule Analyzer

**Nhiệm vụ**: Parse mô tả luật ngôn ngữ tự nhiên thành dữ liệu cấu trúc.

### Input

| Field | Type | Source | Mô tả |
|-------|------|--------|--------|
| `message` | `str` | `rule.description` từ rules.json | Mô tả luật bằng tiếng Việt/Anh |

**Example input** (string gửi vào `agent0.arun()`):
```
Tất cả Gain block phải có SaturateOnIntegerOverflow bằng 'on'
```

### Output: `ParsedRule`

| Field | Type | Mô tả |
|-------|------|--------|
| `rule_id` | `str` | Pipeline gán sau (LLM không biết) |
| `block_keyword` | `str` | Keyword tìm block, lowercase |
| `rule_alias` | `str` | Tên gốc của block trong rule text |
| `config_name` | `str` | Tên config cần check |
| `condition` | `RuleCondition` | Loại so sánh |
| `expected_value` | `str` | Giá trị mong đợi |
| `additional_configs` | `list[AdditionalConfig]` | Configs phụ (compound rule) |
| `compound_logic` | `"SINGLE" \| "AND" \| "OR"` | Logic ghép |
| `target_block_types` | `list[str]` | Explicit block types (rỗng = auto) |
| `scope` | `"all_instances" \| "specific_path" \| "subsystem"` | Phạm vi |
| `scope_filter` | `str` | Pattern lọc |

**Example output** (cho rule R001):
```json
{
  "rule_id": "",
  "block_keyword": "gain",
  "rule_alias": "Gain block",
  "config_name": "SaturateOnIntegerOverflow",
  "condition": "equal",
  "expected_value": "on",
  "additional_configs": [],
  "compound_logic": "SINGLE",
  "target_block_types": [],
  "scope": "all_instances",
  "scope_filter": ""
}
```

**Example output** (cho rule phức tạp hơn — compound):
```json
{
  "rule_id": "",
  "block_keyword": "inport",
  "rule_alias": "inport(targetlink)",
  "config_name": "OutDataTypeStr",
  "condition": "not_equal",
  "expected_value": "Inherit: auto",
  "additional_configs": [
    {
      "config_name": "PortDimensions",
      "condition": "not_empty",
      "expected_value": ""
    }
  ],
  "compound_logic": "AND",
  "target_block_types": ["TL_Inport"],
  "scope": "all_instances",
  "scope_filter": ""
}
```

---

## Agent 1: Data Reader

**Nhiệm vụ**: Tìm block trong từ điển (blocks.json) và phân tích vị trí config trong XML.

### Input

| Field | Type | Source | Mô tả |
|-------|------|--------|--------|
| `message` | `str` | Ghép từ `ParsedRule` | `block_keyword` + `config_name` |

**Example input** (string gửi vào `agent1.arun()`):
```
block_keyword: gain
config_name: SaturateOnIntegerOverflow
```

### Tools sử dụng

| Tool | Khi nào dùng |
|------|-------------|
| `fuzzy_search_json(keyword)` | Tìm block name gần nhất trong blocks.json |
| `read_dictionary(name_xml)` | Đọc mô tả đầy đủ của block |

### Output: `BlockMappingData`

| Field | Type | Mô tả |
|-------|------|--------|
| `name_ui` | `str` | Tên hiển thị (UI) |
| `name_xml` | `str` | Tên trong XML (`BlockType` attribute) |
| `config_map_analysis` | `str` | LLM phân tích: config nằm ở đâu, lưu ý |

**Example output** (cho rule R001):
```json
{
  "name_ui": "Gain",
  "name_xml": "Gain",
  "config_map_analysis": "SaturateOnIntegerOverflow nằm trong <P Name='SaturateOnIntegerOverflow'> là child trực tiếp của <Block BlockType='Gain'>. Giá trị: 'on' hoặc 'off'. Default: 'off' (từ bddefaults.xml). Blocks nằm trong simulink/systems/system_*.xml, KHÔNG nằm trong blockdiagram.xml."
}
```

---

## Agent 1.5: Diff Analyzer (Optional)

**Nhiệm vụ**: Phân tích diff giữa 2 model versions, xác định chính xác config nằm ở đâu trong XML.

**Điều kiện chạy**: Chỉ khi user cung cấp `--model-before`.

### Input

| Field | Type | Source | Mô tả |
|-------|------|--------|--------|
| `message` | `str` | Ghép từ nhiều nguồn | block_type + config_name + block_mapping + diff JSON |

**Example input** (string gửi vào `agent1_5.arun()`):
```
block_type: Gain
config_name: SaturateOnIntegerOverflow
block_mapping: name_ui=Gain, config_map_analysis=SaturateOnIntegerOverflow nằm trong <P>...

RAW DIFF (JSON):
{
  "config_changes": [
    {
      "block_sid": "41",
      "block_name": "Gain3",
      "block_type": "Gain",
      "config_name": "SaturateOnIntegerOverflow",
      "old_value": "off",
      "new_value": "on",
      "location_type": "direct_P",
      "xpath": ".//Block[@SID='41']/P[@Name='SaturateOnIntegerOverflow']"
    }
  ]
}

BDDEFAULTS cho Gain:
{
  "SaturateOnIntegerOverflow": "off",
  "Gain": "1",
  ...
}
```

### Output: `ConfigDiscovery`

| Field | Type | Mô tả |
|-------|------|--------|
| `block_type` | `str` | BlockType trong XML |
| `mask_type` | `str` | MaskType nếu TL block |
| `config_name` | `str` | Tên config |
| `location_type` | `str` | `"direct_P"` \| `"InstanceData"` \| `"MaskValueString"` \| `"attribute"` |
| `xpath_pattern` | `str` | XPath tổng quát cho tất cả blocks cùng type |
| `default_value` | `str` | Default khi config vắng |
| `value_format` | `str` | Format giá trị |
| `notes` | `str` | Ghi chú đặc biệt |

**Example output**:
```json
{
  "block_type": "Gain",
  "mask_type": "",
  "config_name": "SaturateOnIntegerOverflow",
  "location_type": "direct_P",
  "xpath_pattern": ".//Block[@BlockType='Gain']/P[@Name='SaturateOnIntegerOverflow']",
  "default_value": "off",
  "value_format": "on/off",
  "notes": "Config là direct child <P>. Khi vắng trong XML, giá trị = 'off' (từ bddefaults.xml)."
}
```

---

## Agent 2: Code Generator

**Nhiệm vụ**: Khảo sát XML model, viết Python script kiểm tra rule.

### Input

| Field | Type | Source | Mô tả |
|-------|------|--------|--------|
| `message` | `str` | Ghép từ nhiều agents | rule_id + block info + config + condition + [config_discovery] |

**Example input** (string gửi vào `agent2.arun()`):
```
rule_id: R001
block: name_xml=Gain, name_ui=Gain
config_name: SaturateOnIntegerOverflow
condition: RuleCondition.equal
expected_value: on
config_map_analysis: SaturateOnIntegerOverflow nằm trong <P Name='SaturateOnIntegerOverflow'>...
output_filename: check_rule_R001.py

CONFIG DISCOVERY (ground truth from model diff — Agent 1.5):
  block_type: Gain
  mask_type:
  config_name: SaturateOnIntegerOverflow
  location_type: direct_P
  xpath_pattern: .//Block[@BlockType='Gain']/P[@Name='SaturateOnIntegerOverflow']
  default_value: off
  value_format: on/off
  notes: Config là direct child <P>.
```

### Tools sử dụng

| Tool | Khi nào dùng |
|------|-------------|
| `build_model_hierarchy()` | Đầu tiên — xem cấu trúc subsystem |
| `find_blocks_recursive(block_type)` | Tìm tất cả blocks cùng type |
| `query_config(block_type, config_name)` | Extract config + defaults merged |
| `test_xpath_query(xml_file, xpath)` | Verify XPath trước khi code |
| `write_python_file(filename, code)` | Ghi file Python cuối cùng |

### Output: File Python trên disk

**Không có Pydantic output** — Agent 2 ghi file qua tool `write_python_file()`.

Pipeline xác nhận file tồn tại: `generated_checks/check_rule_{rule_id}.py`

**Example output** (`generated_checks/check_rule_R001.py`):
```python
from lxml import etree
import json, sys, os, glob

def check_rule(model_dir: str) -> dict:
    results = {"pass": [], "fail": []}

    # 1. Get default value
    default_val = "off"
    bd_defaults_path = os.path.join(model_dir, "simulink", "bddefaults.xml")
    if os.path.exists(bd_defaults_path):
        tree = etree.parse(bd_defaults_path)
        nodes = tree.getroot().xpath(
            ".//BlockParameterDefaults/Block[@BlockType='Gain']"
            "/P[@Name='SaturateOnIntegerOverflow']"
        )
        if nodes:
            default_val = nodes[0].text or "off"

    # 2. Scan all system files
    systems_dir = os.path.join(model_dir, "simulink", "systems")
    for xml_path in glob.glob(os.path.join(systems_dir, "system_*.xml")):
        tree = etree.parse(xml_path)
        for block in tree.getroot().xpath(".//Block[@BlockType='Gain']"):
            name = block.get("Name", "Unknown")
            sid = block.get("SID", "Unknown")
            node = block.find("./P[@Name='SaturateOnIntegerOverflow']")
            value = node.text if node is not None else default_val

            entry = {"block_name": name, "block_path": f"SID:{sid}", "value": value}
            if value == "on":
                results["pass"].append(entry)
            else:
                results["fail"].append(entry)

    return {
        "rule_id": "R001",
        "total_blocks": len(results["pass"]) + len(results["fail"]),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results,
    }

if __name__ == "__main__":
    print(json.dumps(check_rule(sys.argv[1]), indent=2))
```

**Stdout khi chạy** (`python check_rule_R001.py data/model4_CcodeGeneration/`):
```json
{
  "rule_id": "R001",
  "total_blocks": 19,
  "pass_count": 18,
  "fail_count": 1,
  "details": {
    "pass": [
      {"block_name": "Gain1", "block_path": "SID:5", "value": "on"},
      {"block_name": "Gain2", "block_path": "SID:12", "value": "on"}
    ],
    "fail": [
      {"block_name": "Gain3", "block_path": "SID:41", "value": "off"}
    ]
  }
}
```

---

## Agent 3: Validator

**Nhiệm vụ**: Chạy generated code trên từng test case, so sánh kết quả với expected.

**Đặc biệt**: Không dùng LLM — pure Python logic.

### Input

| Field | Type | Source | Mô tả |
|-------|------|--------|--------|
| `code_file` | `str` | Path từ Agent 2 | `generated_checks/check_rule_R001.py` |
| `test_cases` | `list[TestCase]` | expected_results.json | Danh sách model + expected counts |
| `rule_id` | `str` | rules.json | ID rule |

**Example `TestCase`**:
```json
{
  "model_path": "data/model4_CcodeGeneration.slx",
  "expected_total_blocks": 19,
  "expected_pass": 18,
  "expected_fail": 1
}
```

### Quy trình xử lý

1. **Static check** — file có `check_rule()`, `sys.argv[1]`, `json.dumps`, không có `eval/exec/os.system`
2. **Extract model** — `extract_slx(model_path)` → model_dir
3. **Subprocess** — `python check_rule_R001.py <model_dir>` (timeout 30s)
4. **Parse stdout** — JSON → `actual_result`
5. **Compare** — `actual.total_blocks == expected_total_blocks`, `actual.pass_count == expected_pass`, `actual.fail_count == expected_fail`

### Output: `ValidationResult`

| Field | Type | Mô tả |
|-------|------|--------|
| `rule_id` | `str` | ID rule |
| `status` | `ValidationStatus` | Trạng thái kết quả |
| `stdout` | `str \| None` | Stdout từ subprocess (khi fail) |
| `stderr` | `str \| None` | Stderr từ subprocess (khi crash) |
| `actual_result` | `dict \| None` | `{total_blocks, pass_count, fail_count}` thực tế |
| `expected_result` | `dict \| None` | `{total_blocks, pass, fail}` mong đợi |
| `failed_test_case` | `str \| None` | model_path của test case fail đầu tiên |
| `test_cases_passed` | `int` | Số test cases pass |
| `test_cases_total` | `int` | Tổng test cases |
| `code_file_path` | `str` | Path file code |

### Các trạng thái `ValidationStatus`

| Status | Nghĩa | Retry? | Agent tiếp |
|--------|--------|--------|-----------|
| `PASS` | Tất cả test cases đúng | Dừng | Không |
| `CODE_ERROR` | Code crash (syntax, runtime) | Agent 4 | Bug Fixer |
| `WRONG_RESULT` | Code chạy, tất cả test cases sai | Agent 5 | Inspector |
| `PARTIAL_PASS` | Code chạy, một số pass một số fail | Agent 5 | Inspector |
| `SCHEMA_ERROR` | Lỗi pipeline (không phải code) | Dừng | Không |
| `FAILED_CODE_ERROR` | Hết retry, vẫn crash | Dừng | Human review |
| `FAILED_WRONG_RESULT` | Hết retry, vẫn sai | Dừng | Human review |
| `FAILED_PARTIAL_PASS` | Hết retry, vẫn partial | Dừng | Human review |

**Example output — PASS**:
```json
{
  "rule_id": "R001",
  "status": "PASS",
  "stdout": null,
  "stderr": null,
  "actual_result": null,
  "expected_result": null,
  "failed_test_case": null,
  "test_cases_passed": 1,
  "test_cases_total": 1,
  "code_file_path": "generated_checks/check_rule_R001.py"
}
```

**Example output — CODE_ERROR**:
```json
{
  "rule_id": "R001",
  "status": "CODE_ERROR",
  "stdout": "",
  "stderr": "Traceback (most recent call last):\n  File \"check_rule_R001.py\", line 15\n    blocks = root.xpath(\".//Block[@BlockType='Gain']\"\n                       ^\nSyntaxError: unexpected EOF while parsing",
  "actual_result": null,
  "expected_result": null,
  "failed_test_case": "data/model4_CcodeGeneration.slx",
  "test_cases_passed": 0,
  "test_cases_total": 1,
  "code_file_path": "generated_checks/check_rule_R001.py"
}
```

**Example output — WRONG_RESULT**:
```json
{
  "rule_id": "R001",
  "status": "WRONG_RESULT",
  "stdout": "{\"rule_id\": \"R001\", \"total_blocks\": 5, \"pass_count\": 5, \"fail_count\": 0}",
  "stderr": null,
  "actual_result": {"total_blocks": 5, "pass_count": 5, "fail_count": 0},
  "expected_result": {"total_blocks": 19, "pass": 18, "fail": 1},
  "failed_test_case": "data/model4_CcodeGeneration.slx",
  "test_cases_passed": 0,
  "test_cases_total": 1,
  "code_file_path": "generated_checks/check_rule_R001.py"
}
```

**Example output — PARTIAL_PASS** (khi có 2+ test cases):
```json
{
  "rule_id": "R001",
  "status": "PARTIAL_PASS",
  "stdout": "{\"total_blocks\": 10, \"pass_count\": 10, \"fail_count\": 0}",
  "stderr": null,
  "actual_result": {"total_blocks": 10, "pass_count": 10, "fail_count": 0},
  "expected_result": {"total_blocks": 19, "pass": 18, "fail": 1},
  "failed_test_case": "data/model4_CcodeGeneration.slx",
  "test_cases_passed": 1,
  "test_cases_total": 2,
  "code_file_path": "generated_checks/check_rule_R001.py"
}
```

---

## Agent 4: Bug Fixer

**Nhiệm vụ**: Sửa code bị crash (CODE_ERROR) dựa trên error traceback.

**Khi nào chạy**: `ValidationStatus.CODE_ERROR` + Agent 4 còn budget.

### Input

| Field | Type | Source | Mô tả |
|-------|------|--------|--------|
| `message` | `str` | `RetryStateMachine.build_agent4_context()` | File path + stderr + attempt + error history |

**Example input** (string gửi vào `agent4.arun()`):
```
File bị lỗi: generated_checks/check_rule_R001.py
Test case fail: data/model4_CcodeGeneration.slx
Stderr:
Traceback (most recent call last):
  File "check_rule_R001.py", line 32, in check_rule
    value = config_node.text
AttributeError: 'NoneType' object has no attribute 'text'
Đây là lần fix thứ 1
```

**Example input** (lần fix thứ 2, có error history):
```
File bị lỗi: generated_checks/check_rule_R001.py
Test case fail: data/model4_CcodeGeneration.slx
Stderr:
Traceback (most recent call last):
  File "check_rule_R001.py", line 35, in check_rule
    for block in blocks:
TypeError: 'NoneType' object is not iterable
Đây là lần fix thứ 2

⚠ Lịch sử lỗi TRƯỚC ĐÓ (KHÔNG lặp lại cách fix đã thất bại):
  1. CODE_ERROR(unknown) [test_case=data/model4_CcodeGeneration.slx]: AttributeError: 'NoneType' object has no attribute 'text'
```

### Tools sử dụng

| Tool | Khi nào dùng |
|------|-------------|
| `read_python_file(filename)` | Đọc code hiện tại |
| `read_error_traceback(stderr)` | Parse error type + line number |
| `patch_python_file(filename, new_code)` | Ghi code đã fix |

### Output: File Python đã patch trên disk

**Không có Pydantic output** — Agent 4 sửa file qua tool `patch_python_file()`.

Pipeline re-validate bằng Agent 3 sau khi fix.

**Example**: trước/sau fix

Trước (dòng 32):
```python
value = config_node.text
```

Sau (dòng 32-35):
```python
if config_node is not None:
    value = config_node.text or default_val
else:
    value = default_val
```

---

## Agent 5: Model Inspector

**Nhiệm vụ**: Điều tra XML model tìm nguyên nhân kết quả sai, rewrite code.

**Khi nào chạy**:
  - `ValidationStatus.WRONG_RESULT` (code chạy nhưng sai kết quả)
  - `ValidationStatus.PARTIAL_PASS` (một số test pass, một số fail)
  - Escalation từ Agent 4 (Agent 4 fix không được)

### Input

| Field | Type | Source | Mô tả |
|-------|------|--------|--------|
| `message` | `str` | `RetryStateMachine.build_agent5_context()` | File + actual/expected + block info + [config_discovery] + error history |

**Example input — WRONG_RESULT** (string gửi vào `agent5.arun()`):
```
File code: generated_checks/check_rule_R001.py
Test case fail: data/model4_CcodeGeneration.slx
Actual result: {'total_blocks': 5, 'pass_count': 5, 'fail_count': 0}
Expected result: {'total_blocks': 19, 'pass': 18, 'fail': 1}
Block config analysis: SaturateOnIntegerOverflow nằm trong <P>. Blocks nằm trong system_*.xml...
Đây là lần điều tra thứ 1
```

**Example input — ESCALATION từ Agent 4**:
```
⚠ ESCALATION: Agent 4 đã fix 2 lần nhưng code vẫn lỗi.
Loại lỗi có thể SAI GỐC — cần điều tra lại model XML.

File code: generated_checks/check_rule_R001.py
Test case fail: data/model4_CcodeGeneration.slx
Actual result: None
Expected result: None
Block config analysis: SaturateOnIntegerOverflow nằm trong <P>...
Đây là lần điều tra thứ 1

⚠ Lịch sử lỗi (Agent 4 đã thất bại — cần approach MỚI HOÀN TOÀN):
  1. CODE_ERROR(syntax_error): SyntaxError: unexpected EOF while parsing
  2. CODE_ERROR(xpath_error): lxml.etree.XPathError: Invalid expression

CONFIG DISCOVERY (ground truth from model diff — Agent 1.5):
  location_type: direct_P
  xpath_pattern: .//Block[@BlockType='Gain']/P[@Name='SaturateOnIntegerOverflow']
  default_value: off
  notes: Config là direct child <P>.
```

**Example input — lần retry cuối**:
```
File code: generated_checks/check_rule_R001.py
Test case fail: data/model4_CcodeGeneration.slx
Actual result: {'total_blocks': 15, 'pass_count': 14, 'fail_count': 1}
Expected result: {'total_blocks': 19, 'pass': 18, 'fail': 1}
Block config analysis: ...
Đây là lần điều tra thứ 3

🔴 ĐÂY LÀ LẦN RETRY CUỐI — dùng read_raw_block_config() để đọc TOÀN BỘ raw config của block gây lỗi. Không bỏ sót gì.

⚠ Lịch sử lỗi (KHÔNG lặp lại approach đã thất bại):
  1. WRONG_RESULT(logic_error): actual={"total_blocks": 5}, expected={"total_blocks": 19}
  2. WRONG_RESULT(logic_error): actual={"total_blocks": 15}, expected={"total_blocks": 19}
```

### Tools sử dụng

| Tool | Khi nào dùng |
|------|-------------|
| `build_model_hierarchy()` | Xem cấu trúc subsystem |
| `find_blocks_recursive(block_type)` | Đếm blocks ở tất cả subsystems |
| `query_config(block_type, config_name)` | Extract config + defaults |
| `read_raw_block_config(block_sid)` | Dump toàn bộ block XML (escalation) |
| `test_xpath_query(xml_file, xpath)` | Verify XPath mới |
| `rewrite_advanced_code(filename, code, reason)` | Viết lại toàn bộ code |

### Output: File Python đã rewrite trên disk

**Không có Pydantic output** — Agent 5 ghi file qua tool `rewrite_advanced_code()`.

Pipeline re-validate bằng Agent 3 sau khi rewrite.

---

## Pipeline Output: FinalReport

Sau khi tất cả rules xử lý xong, pipeline trả về `FinalReport`.

### `FinalReport`

| Field | Type | Mô tả |
|-------|------|--------|
| `timestamp` | `str` | ISO 8601 UTC |
| `model_file` | `str` | Path model .slx |
| `total_rules` | `int` | Tổng số rules |
| `results` | `list[RuleReport]` | Kết quả từng rule |
| `total_duration_seconds` | `float` | Thời gian toàn bộ pipeline |

### `RuleReport`

| Field | Type | Mô tả |
|-------|------|--------|
| `rule_id` | `str` | ID rule |
| `status` | `ValidationStatus` | Trạng thái cuối cùng |
| `match_expected` | `bool` | True nếu PASS |
| `actual` | `dict \| None` | Kết quả thực tế (khi fail) |
| `expected` | `dict \| None` | Kết quả mong đợi (khi fail) |
| `generated_script` | `str` | Path Python file |
| `needs_human_review` | `bool` | True nếu FAILED_* |
| `pipeline_trace` | `list[dict]` | `[{agent, attempt}, ...]` |
| `pipeline_steps` | `list[PipelineStep]` | Chi tiết timing từng bước |
| `rule_duration_seconds` | `float` | Thời gian xử lý rule |
| `error_detail` | `str \| None` | Chi tiết lỗi cuối (khi FAILED_*) |

**Example** (R001 pass lần đầu):
```json
{
  "timestamp": "2026-03-18T10:30:00+00:00",
  "model_file": "data/model4_CcodeGeneration.slx",
  "total_rules": 2,
  "results": [
    {
      "rule_id": "R001",
      "status": "PASS",
      "match_expected": true,
      "actual": null,
      "expected": null,
      "generated_script": "generated_checks/check_rule_R001.py",
      "needs_human_review": false,
      "pipeline_trace": [],
      "pipeline_steps": [
        {"agent_name": "Agent 0 (Rule Analyzer)", "duration_seconds": 1.2, "status": "success", "output_summary": "block_keyword=gain"},
        {"agent_name": "Agent 1 (Data Reader)", "duration_seconds": 2.1, "status": "success", "output_summary": "name_xml=Gain"},
        {"agent_name": "Agent 2 (Code Generator)", "duration_seconds": 8.5, "status": "success", "output_summary": "file=generated_checks/check_rule_R001.py"},
        {"agent_name": "Agent 3 (Validator)", "duration_seconds": 3.0, "status": "success", "output_summary": "status=PASS, passed=1/1"}
      ],
      "rule_duration_seconds": 14.8,
      "error_detail": null
    }
  ],
  "total_duration_seconds": 14.8
}
```

**Example** (R001 fail, retry Agent 4 rồi Agent 5, cuối cùng pass):
```json
{
  "rule_id": "R001",
  "status": "PASS",
  "match_expected": true,
  "pipeline_trace": [
    {"agent": "agent4", "attempt": 1},
    {"agent": "agent5", "attempt": 1}
  ],
  "pipeline_steps": [
    {"agent_name": "Agent 0 (Rule Analyzer)", "duration_seconds": 1.2, "status": "success"},
    {"agent_name": "Agent 1 (Data Reader)", "duration_seconds": 2.1, "status": "success"},
    {"agent_name": "Agent 2 (Code Generator)", "duration_seconds": 8.5, "status": "success"},
    {"agent_name": "Agent 3 (Validator)", "duration_seconds": 3.0, "status": "error", "output_summary": "status=CODE_ERROR"},
    {"agent_name": "Agent 4 (Bug Fixer) #1", "duration_seconds": 4.2, "status": "success"},
    {"agent_name": "Agent 3 (Re-validate)", "duration_seconds": 3.0, "status": "error", "output_summary": "status=WRONG_RESULT"},
    {"agent_name": "Agent 5 (Inspector) #1", "duration_seconds": 12.5, "status": "success"},
    {"agent_name": "Agent 3 (Re-validate)", "duration_seconds": 3.0, "status": "success", "output_summary": "status=PASS"}
  ],
  "rule_duration_seconds": 37.5
}
```

**Example** (FAILED — hết retry):
```json
{
  "rule_id": "R001",
  "status": "FAILED_WRONG_RESULT",
  "match_expected": false,
  "actual": {"total_blocks": 15, "pass_count": 14, "fail_count": 1},
  "expected": {"total_blocks": 19, "pass": 18, "fail": 1},
  "generated_script": "generated_checks/check_rule_R001.py",
  "needs_human_review": true,
  "pipeline_trace": [
    {"agent": "agent5", "attempt": 1},
    {"agent": "agent5", "attempt": 2},
    {"agent": "agent5", "attempt": 3}
  ],
  "rule_duration_seconds": 85.2,
  "error_detail": null
}
```
