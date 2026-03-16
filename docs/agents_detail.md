# Chi tiết Kỹ thuật 6 Agents: TargetLink Rule Checking

Tài liệu này mô tả chuyên sâu về **Agent Skills** (Khả năng của Agent) thông qua các **Tools** được cấp phát, định dạng Input/Output bằng Pydantic, Prompt (hướng dẫn tư duy), và cơ chế giao tiếp giữa các Agent.

Tất cả các Agent (trừ Agent 1) đều là **Agno Agents** được nạp LLM Backend (**Gemini via Google Cloud Vertex AI**) để có khả năng duy lý (Reasoning) và lập trình (Agentic Coding).

---

## Tổng quan Pydantic Schemas

Schemas được tách thành nhiều file theo domain trong `schemas/`:

```python
# ── schemas/rule_schemas.py ──
from enum import Enum
from pydantic import BaseModel, Field

class RuleInput(BaseModel):
    rule_id: str                # VD: "R001"
    description: str            # Mô tả luật bằng ngôn ngữ tự nhiên

class RuleCondition(str, Enum):
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    NOT_EMPTY = "not_empty"
    CONTAINS = "contains"
    IN_LIST = "in_list"

class ParsedRule(BaseModel):           # Agent 0 Output
    rule_id: str = ""           # Pipeline gán sau, LLM không biết rule_id
    block_keyword: str          # VD: "inport"
    rule_alias: str             # VD: "inport(targetlink)"
    config_name: str            # VD: "DataType"
    condition: RuleCondition    # Enum — chặn giá trị không hợp lệ
    expected_value: str         # VD: "Inherit: auto"

# ── schemas/block_schemas.py ──
class BlockMappingData(BaseModel):     # Agent 1 Output
    name_ui: str                # VD: "Inport"
    name_xml: str               # VD: "TL_Inport"
    config_map_analysis: str    # LLM summary: XPath hints, mode, special notes

# ── schemas/validation_schemas.py ──
class ValidationStatus(str, Enum):     # Agent 3 Output
    PASS = "PASS"                           # Code chạy OK + khớp expected
    CODE_ERROR = "CODE_ERROR"               # Code bị Syntax/Runtime Error
    WRONG_RESULT = "WRONG_RESULT"           # Code chạy OK nhưng kết quả sai
    FAILED_CODE_ERROR = "FAILED_CODE_ERROR" # Quá retry limit cho code error
    FAILED_WRONG_RESULT = "FAILED_WRONG_RESULT"  # Quá retry limit cho wrong result
    SCHEMA_ERROR = "SCHEMA_ERROR"           # Pydantic validation fail

class ValidationResult(BaseModel):
    rule_id: str
    status: ValidationStatus
    stdout: Optional[str] = None            # Output từ sandbox
    stderr: Optional[str] = None            # Error từ sandbox
    actual_result: Optional[dict] = None    # Kết quả thực tế
    expected_result: Optional[dict] = None  # Kết quả mong đợi
    failed_test_case: Optional[str] = None  # model_path của test case bị fail
    test_cases_passed: int = 0
    test_cases_total: int = 0
    code_file_path: str                     # Path tới file code hiện tại

# ── schemas/report_schemas.py ──
class RuleReport(BaseModel):           # Kết quả 1 rule qua pipeline
    rule_id: str
    status: ValidationStatus
    match_expected: bool = False
    actual: Optional[dict] = None
    expected: Optional[dict] = None
    generated_script: str = ""
    needs_human_review: bool = False
    pipeline_trace: list[dict] = []
    error_detail: Optional[str] = None

class FinalReport(BaseModel):          # Báo cáo tổng hợp
    timestamp: str
    model_file: str
    total_rules: int
    results: list[RuleReport]
```

---

## 🤖 Agent 0: Rule Analyzer
*Đứa trẻ học vỡ lòng — Chuyên đọc hiểu ngôn ngữ tự nhiên.*

- **Vai trò**: Đọc text của người dùng (từ file `rules.json`) và bóc tách thành các tham số kỹ thuật.
- **Skill (Tools)**: `parse_natural_language`
- **Input**: Chuỗi text (VD: *"Tất cả khối inport(targetlink) phải set DataType là int16"*).
- **Output**: `ParsedRule`

### Prompt Template
```
Bạn là Rule Analyzer. Nhiệm vụ: đọc mô tả luật bằng tiếng Việt hoặc tiếng Anh,
trích xuất thành cấu trúc dữ liệu.

Rule text: "{rule_description}"

Hãy trích xuất:
1. block_keyword: Tên block cần kiểm tra (viết thường, VD: "inport", "outport", "main data")
2. rule_alias: Tên đầy đủ như user viết (VD: "inport(targetlink)")
3. config_name: Tên config/property cần check (VD: "DataType", "StorageClass")
4. condition: Loại điều kiện ("equal", "not_equal", "contains", "not_empty", "in_list")
5. expected_value: Giá trị kỳ vọng hoặc giá trị cấm (VD: "int16", "Inherit: auto")

Trả về JSON theo đúng schema ParsedRule.
```

### Ví dụ Input/Output
```
Input:  "Tất cả inport(targetlink) phải set DataType cụ thể, không được để Inherited"
Output: {
    "rule_id": "R001",
    "block_keyword": "inport",
    "rule_alias": "inport(targetlink)",
    "config_name": "DataType",
    "condition": "not_equal",
    "expected_value": "Inherit: auto"
}
```

---

## 🔎 Agent 1: Data Reader & Search Engine
*Thủ thư — Chuyên gia tra cứu từ điển tốc độ cao.*

- **Vai trò**: TÌM đúng Block đang cần kiểm tra giữa hàng ngàn blocks trong File Từ Điển (`blocks.json`). Sau đó, đọc phần "Description" để lập bản đồ vị trí config.
- **Skill (Tools)**: `fuzzy_search_json`, `read_dictionary`
- **Input**: `ParsedRule.block_keyword`
- **Output**: `BlockMappingData`
- **Đặc biệt**: Agent 1 **KHÔNG dùng LLM** cho bước search. Dùng `rapidfuzz.fuzz.token_sort_ratio` để match keyword với `name_ui` trong JSON. Chỉ dùng LLM để phân tích `description` thành `config_map_analysis`.

### Thuật toán Search
```python
from rapidfuzz import fuzz

def fuzzy_search(keyword: str, blocks: list[dict], threshold: int = 70) -> dict | None:
    best_match = None
    best_score = 0
    for block in blocks:
        score = fuzz.token_sort_ratio(keyword.lower(), block["name_ui"].lower())
        if score > best_score and score >= threshold:
            best_score = score
            best_match = block
    return best_match
```

### Prompt Template (cho phần phân tích Description)
```
Bạn là Data Analyst. Đọc Description của block "{name_ui}" (XML name: {name_xml})
và cho biết:
1. Config "{config_name}" nằm ở thẻ XML nào? (XPath gợi ý)
2. Config này có bị ẩn/thay đổi theo Mode (Standard vs AUTOSAR) không?
3. Có lưu ý đặc biệt nào về tên XML khác tên UI không?

Description: "{description}"
```

---

## 💻 Agent 2: Code Generator (Copilot 1)
*Senior Python Developer — Chuyên gia viết test script.*

- **Vai trò**: Dựa trên vị trí config do Agent 1 chỉ ra, Agent 2 tự khám phá XML tree (nhiều file XML) từng bước qua tools, verify XPath, rồi viết 1 file Python script hoàn chỉnh để test Rule đó.
- **Tính chất**: Agent agentic (multi-step, tự chủ dùng tools) — KHÔNG có memory (mỗi lần chạy bắt đầu từ đầu).
- **Skill (Tools) cấp phát**:
  - **Model-level (ưu tiên dùng trước)**:
    - `build_model_hierarchy() -> str`: Xem cây subsystem Root → SubSystem → children. **GỌI ĐẦU TIÊN**.
    - `find_blocks_recursive(block_type) -> str`: Tìm TẤT CẢ blocks of type xuyên mọi subsystem layers.
    - `query_config(block_type, config_name) -> str`: Rút CHỈ 1 config cụ thể + default fallback.
    - `trace_connections(block_sid) -> str`: Trace incoming/outgoing signal connections.
  - **XML chi tiết (khi cần xem cấu trúc thô)**:
    - `list_xml_files() -> str`: Liệt kê tất cả file XML trong model tree.
    - `read_xml_structure(xml_file, xpath) -> str`: Đọc cấu trúc XML nodes (max 10 nodes).
    - `test_xpath_query(xml_file, xpath) -> str`: Verify XPath trên 1 file XML (max 20 kết quả).
    - `deep_search_xml_text(xml_file, regex_pattern) -> str`: Regex search trong 1 file XML (max 50 kết quả).
    - `read_parent_nodes(xml_file, xpath) -> str`: Đọc ancestry chain từ root → target node.
  - **Sinh code**:
    - `write_python_file(filename, content) -> str`: Sinh script Python lưu vào `generated_checks/`.
- **Input**: `ParsedRule` + `BlockMappingData` + đường dẫn tới thư mục model (XML tree)
- **Output**: Agents 2/4/5 ghi file trực tiếp qua tools (write_python_file, patch_python_file, rewrite_advanced_code). Pipeline verify file tồn tại sau mỗi agent.
- **Lưu ý**: SLX sau khi unzip là MỘT TREE GỒM NHIỀU FILE XML. Agent 2 KHÔNG có tool đọc toàn bộ XML — phải explore từng phần.

### Prompt Template
```
Bạn là Python Developer chuyên viết rule checking script cho TargetLink models.

THÔNG TIN:
- Block cần check: "{name_xml}" (UI name: "{name_ui}")
- Config cần check: "{config_name}"
- Điều kiện: "{condition}" với giá trị: "{expected_value}"
- Phân tích cấu trúc: {config_map_analysis}

BƯỚC LÀM VIỆC:
1. Dùng tool `read_xml_structure` để xem cấu trúc thực tế của block "{name_xml}" trong model
2. Dùng tool `test_xpath_query` để thử XPath truy cập config "{config_name}"
3. Viết Python script hoàn chỉnh (dùng lxml) kiểm tra rule này trên toàn bộ model

YÊU CẦU CODE:
- Import: `from lxml import etree` và `import json, sys, os`
- Function `check_rule(model_dir: str) -> dict` nhận thư mục XML tree
- Blocks nằm ở `simulink/systems/system_*.xml` — KHÔNG phải `blockdiagram.xml`
- Dùng `glob("system_*.xml")` để scan tất cả subsystem files
- Config vắng trong block XML = default value (tra từ `bddefaults.xml`)
- Return dict keys: rule_id, total_blocks, pass_count, fail_count, details
- Bọc tất cả XML access trong `try-except` để tránh crash khi node=None
- Script có `if __name__ == "__main__"` để chạy standalone
- stdout CHỈ có 1 `print(json.dumps(...))` duy nhất

TUYỆT ĐỐI KHÔNG ghi/sửa file XML.
```

### Hành vi Agentic
Agent 2 là agentic — tự chủ khám phá XML tree qua nhiều bước, KHÔNG có memory. Quy trình:
1. Gọi `build_model_hierarchy()` → Xem cây subsystem, biết model structure
2. Gọi `find_blocks_recursive("{name_xml}")` → Tìm tất cả blocks xuyên layers
3. Gọi `query_config("{name_xml}", "{config_name}")` → Rút config targeted
4. Gọi `test_xpath_query("simulink/systems/system_root.xml", ...)` → Verify XPath trước khi viết code
5. Nếu XPath không match → Thử biến thể khác, search ở file XML khác
6. Viết code dựa trên kết quả thực tế, không phải đoán

---

## 🕵️ Agent 3: Validator (Reviewer)
*QA Tester — Máy kiểm thử tàn nhẫn.*

- **Vai trò**: Chạy code trong subprocess sandbox, so kết quả với Test Case `expected_results.json`.
- **Tính chất**: **Pure Python — KHÔNG dùng LLM**. Chạy subprocess trực tiếp, parse JSON stdout, so sánh 3 fields (total_blocks, pass_count, fail_count).
- **Input**: code_file path + list[TestCase] + rule_id
- **Output**: `ValidationResult`

### Quy trình Validate
```
Với mỗi test case:
1. Extract .slx → thư mục XML tree (dùng slx_extractor)
2. subprocess.run(code_file, model_dir) — timeout configurable
3. Nếu exit_code != 0 → status = CODE_ERROR (trả về stderr)
4. Nếu exit_code == 0 → json.loads(stdout), so sánh:
   - total_blocks, pass_count, fail_count khớp expected → PASS
   - Không khớp → WRONG_RESULT (trả về actual vs expected)
5. Dừng ở test case đầu tiên FAIL
```

### Quyết định Routing
```
ValidationResult.status == PASS           → Ghi report, chuyển rule tiếp theo
ValidationResult.status == CODE_ERROR     → Chuyển cho Agent 4 (nếu chưa hết retry)
ValidationResult.status == WRONG_RESULT   → Chuyển cho Agent 5 (nếu chưa hết retry)
RetryManager hết quota (3 lần/agent)      → Đánh dấu FAILED, chuyển rule tiếp theo
```

---

## 🚑 Agent 4: Bug Fixer
*Kỹ sư bảo trì — Fix bug dựa trên Traceback.*

- **Vai trò**: Nhận Error Message (từ lệnh chạy lỗi của Agent 3), đọc lại Code của Agent 2 và sửa lỗi.
- **Skill (Tools) cấp phát**:
  - `read_python_file(file_path) -> str`: Đọc toàn bộ nội dung file code bị lỗi.
  - `read_error_traceback(stderr) -> dict`: Phân tích chuỗi error, trả về `{error_type, error_message, line_number, context}`.
  - `patch_python_file(file_path, new_content) -> str`: Ghi đè file code với bản sửa mới.
- **Input**: `ValidationResult` (status=CODE_ERROR)
- **Output**: File code đã sửa (ghi qua `patch_python_file`)

### Prompt Template
```
Bạn là Bug Fixer. Code do AI sinh ra bị lỗi khi chạy. Nhiệm vụ: sửa code.

ERROR INFO:
- File: {file_path}
- Error type: {error_type}
- Error message: {error_message}
- Line: {line_number}

BƯỚC LÀM VIỆC:
1. Dùng tool `read_python_file` đọc code hiện tại
2. Dùng tool `read_error_traceback` phân tích lỗi chi tiết
3. Xác định nguyên nhân lỗi:
   - NoneType? → Thêm if-check `node is not None`
   - IndexError? → Thêm len() check trước khi access
   - AttributeError? → Kiểm tra lại tên method/property
   - XPath syntax? → Sửa cú pháp XPath
4. Dùng tool `patch_python_file` ghi bản sửa

CHÚ Ý: Chỉ sửa phần bị lỗi, giữ nguyên logic tổng thể.
Đây là lần retry thứ {attempt}/3.
```

### Hành vi Agentic
Tư duy y hệt lập trình viên khi gỡ rối:
- `NoneType has no attribute 'text'` → XML node trả về `None` → Fix: `if node is not None: node.text`
- `IndexError: list index out of range` → XPath trả về list rỗng → Fix: `if len(results) > 0`
- `SyntaxError` → Lỗi cú pháp Python cơ bản → Fix trực tiếp

Tối đa thử lại **3 vòng**. Nếu không được → trả `ValidationResult(status=FAILED_CODE_ERROR)` kèm toàn bộ history sửa code.

---

## 🔬 Agent 5: Model Inspector (Copilot 2)
*Data Detective — Cảnh sát rà soát XML Node level.*

- **Vai trò**: Khi code KHÔNG BỊ BUG (chạy mượt) nhưng kết quả Check Rule (True/False) lại ra kết quả VÔ LÝ so với User Test Case (VD: Model đó đáng lẽ có 5 Inport blocks nhưng code đếm ra 0). Agent 5 phải đi tìm trong XML tree xem TargetLink giấu block đó ở Node nào.
- **Tính chất**: Agent agentic (multi-step, tự chủ dùng tools) — KHÔNG có memory (mỗi lần chạy bắt đầu từ đầu).
- **Skill (Tools) cấp phát**:
  - **Model-level (ưu tiên dùng trước)**:
    - `build_model_hierarchy() -> str`: Xem cây subsystem.
    - `find_blocks_recursive(block_type) -> str`: Tìm tất cả blocks xuyên layers.
    - `query_config(block_type, config_name) -> str`: Rút config + default fallback.
    - `trace_connections(block_sid) -> str`: Trace signal connections.
    - `read_raw_block_config(block_sid) -> str`: Đọc TOÀN BỘ raw config (**ESCALATION** — dùng khi retry cuối).
  - **XML chi tiết**:
    - `list_xml_files() -> str`: Liệt kê file XML.
    - `deep_search_xml_text(xml_file, regex_pattern) -> str`: Regex search (max 50 matches).
    - `read_xml_structure(xml_file, xpath) -> str`: Đọc cấu trúc nodes.
    - `read_parent_nodes(xml_file, xpath) -> str`: Ancestry chain.
    - `test_xpath_query(xml_file, xpath) -> str`: Verify XPath mới.
  - **Sinh code**:
    - `rewrite_advanced_code(filename, new_code_content, reason) -> str`: Viết lại toàn bộ code mới.
- **Input**: `ValidationResult` (status=WRONG_RESULT) + `BlockMappingData`
- **Output**: File code mới (ghi qua `rewrite_advanced_code`)
- **Lưu ý**: Agent 5 KHÔNG có tool đọc toàn bộ XML — phải search/explore từng phần. Blocks nằm ở `simulink/systems/system_*.xml`.

### Prompt Template
```
Bạn là Model Inspector. Code chạy không lỗi nhưng kết quả SAI so với test case.

TÌNH HUỐNG:
- Rule: {rule_id}
- Block tìm: {name_xml}
- Actual result: {actual_result}
- Expected result: {expected_result}
- Chênh lệch: {diff}
- Config map analysis từ Agent 1: {config_map_analysis}

CHIẾN LƯỢC ĐIỀU TRA:
1. Đặt giả thuyết tại sao kết quả sai:
   - Giả thuyết 1: Block bị đổi tên BlockType trong XML?
   - Giả thuyết 2: Block nằm trong SubSystem lồng nhau?
   - Giả thuyết 3: Config bị ẩn/đổi vị trí do mode (Standard vs AUTOSAR)?
   - Giả thuyết 4: Block dùng Mask/Reference thay vì trực tiếp?

2. Kiểm chứng từng giả thuyết:
   - Dùng `deep_search_xml_text` search tên block/config bằng regex
   - Dùng `read_parent_nodes` xem block nằm trong cây nào
   - So sánh với config_map_analysis xem Description có đề cập trường hợp này không

3. Khi tìm ra nguyên nhân:
   - Dùng `rewrite_advanced_code` viết lại XPath/logic chính xác hơn

GHI LẠI: Mỗi giả thuyết đã test và kết quả vào field `hypothesis_tested`.
Đây là lần retry thứ {attempt}/3.
```

### Hành vi Agentic
Agent 5 là agentic — tự chủ điều tra qua nhiều bước, KHÔNG có memory. Quy trình tư duy:

```
1. build_model_hierarchy() → Xem cây subsystem, biết model structure
2. Nhận diff: expected 5 blocks, actual 0
   → Giả thuyết: XPath sai, block có tên khác trong XML

3. find_blocks_recursive("TL_Inport") → Tìm thấy 5 blocks (MaskType match)
   → Phát hiện blocks nằm trong SubSystem wrapper, có MaskType = "TL_Inport"

4. read_raw_block_config("{block_sid}") → Xem TOÀN BỘ raw config của 1 block
   → Xác nhận cấu trúc XML chính xác

5. test_xpath_query("simulink/systems/system_root.xml", ".//Block[@MaskType='TL_Inport']") → 5 kết quả ✓

6. rewrite_advanced_code → Trả code mới cho Agent 3
```

---

## Quy tắc Thép cho toàn bộ quá trình

1. **XML MODEL LÀ BẤT KHẢ XÂM PHẠM**: Cả 6 tool `read_xml...` của các AI Agent đều truy vấn bằng thư viện `lxml` với cơ chế in-memory, tuyệt đối không có code nào được cấp quyền `open(file, 'w')` vào file `.slx` gốc.
2. **SANDBOX**: Agent 3 thực thi các thuật toán do LLM (Agent 2, 4, 5) tự do sinh bằng subprocess isolation, tránh làm sập luồng Main Pipeline của Framework Agno.
3. **PYDANTIC VALIDATION**: Mọi dữ liệu truyền giữa Agent đều qua Pydantic `.model_validate()`. Nếu schema sai → dừng ngay, không đoán.
4. **RETRY LIMIT**: Tối đa 3 lần retry cho Agent 4 và Agent 5. Không vòng lặp vô hạn.
5. **LOGGING**: Mọi tool call, LLM response, và agent decision đều được log ra console/file để debug.

---

## Bảng tổng hợp Tools theo Agent

| Agent | Tool | Chức năng | Read/Write |
|-------|------|-----------|------------|
| 0 | (LLM structured output) | Phân tích text rule → ParsedRule | Read-only |
| 1 | `fuzzy_search_json` | Tìm block trong JSON (rapidfuzz, no LLM) | Read-only |
| 1 | `read_dictionary` | Đọc description block | Read-only |
| 2 | `build_model_hierarchy` | Xem cây subsystem của model | Read-only |
| 2 | `find_blocks_recursive` | Tìm tất cả blocks of type xuyên layers | Read-only |
| 2 | `query_config` | Rút 1 config cụ thể + default fallback | Read-only |
| 2 | `list_xml_files` | Liệt kê file XML trong tree | Read-only |
| 2 | `read_xml_structure` | Xem cấu trúc 1 file XML | Read-only |
| 2 | `test_xpath_query` | Thử XPath trên 1 file XML | Read-only |
| 2 | `deep_search_xml_text` | Regex search trong 1 file XML | Read-only |
| 2 | `read_parent_nodes` | Đọc ancestry chain | Read-only |
| 2 | `write_python_file` | Sinh file check script | Write (chỉ thư mục `generated_checks/`) |
| 3 | (Pure Python) | subprocess.run + JSON compare | Execute (isolated subprocess) |
| 4 | `read_python_file` | Đọc code bị lỗi | Read-only |
| 4 | `read_error_traceback` | Phân tích error message | Read-only |
| 4 | `patch_python_file` | Sửa file code | Write (chỉ thư mục `generated_checks/`) |
| 5 | `build_model_hierarchy` | Xem cây subsystem của model | Read-only |
| 5 | `find_blocks_recursive` | Tìm tất cả blocks of type xuyên layers | Read-only |
| 5 | `query_config` | Rút 1 config cụ thể + default fallback | Read-only |
| 5 | `trace_connections` | Trace incoming/outgoing connections | Read-only |
| 5 | `read_raw_block_config` | Đọc TOÀN BỘ raw config (escalation) | Read-only |
| 5 | `list_xml_files` | Liệt kê file XML trong tree | Read-only |
| 5 | `deep_search_xml_text` | Regex search trong 1 file XML | Read-only |
| 5 | `read_xml_structure` | Xem cấu trúc 1 file XML | Read-only |
| 5 | `read_parent_nodes` | Đọc ancestry chain | Read-only |
| 5 | `test_xpath_query` | Verify XPath mới | Read-only |
| 5 | `rewrite_advanced_code` | Viết lại code mới | Write (chỉ thư mục `generated_checks/`) |
