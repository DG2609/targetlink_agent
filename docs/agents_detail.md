# Chi tiết Kỹ thuật 7 Agents: TargetLink Rule Checking

Tài liệu này mô tả chuyên sâu về **Agent Skills** (Tools), định dạng Input/Output (Pydantic), Prompt instructions, và cơ chế giao tiếp giữa các Agent.

Tất cả các Agent (trừ Agent 1 và Agent 3) sử dụng LLM Backend thông qua **model factory** (`utils/model_factory.py`) — hỗ trợ **Gemini (Vertex AI)** hoặc **Ollama (local)**.

---

## Tổng quan Pydantic Schemas

Schemas được tách thành nhiều file theo domain trong `schemas/`:

```python
# ── schemas/rule_schemas.py ──
class ParsedRule(BaseModel):           # Agent 0 Output
    rule_id: str = ""
    block_keyword: str          # VD: "gain"
    rule_alias: str             # VD: "Gain"
    config_name: str            # VD: "SaturateOnIntegerOverflow"
    condition: RuleCondition    # Enum: equal, not_equal, not_empty, contains, in_list
    expected_value: str         # VD: "on"

# ── schemas/block_schemas.py ──
class BlockMappingData(BaseModel):     # Agent 1 Output
    name_ui: str                # VD: "Gain"
    name_xml: str               # VD: "Gain"
    xml_representation: str     # "native", "masked", "reference", "unknown"
    search_confidence: int      # 0-100
    source_type_pattern: str    # VD: "Compare To Constant" (for Reference blocks)
    config_map_analysis: str    # LLM summary: XPath hints, mode, special notes

# ── schemas/diff_schemas.py ──
class ConfigDiscovery(BaseModel):      # Agent 1.5 Output
    location_type: str          # VD: "direct_parameter"
    xpath_pattern: str          # VD: ".//Block[@BlockType='Gain']/P[@Name='...']"
    default_value: str          # VD: "off"
    notes: str                  # Additional context

# ── schemas/validation_schemas.py ──
class ValidationResult(BaseModel):     # Agent 3 Output
    rule_id: str
    status: ValidationStatus    # PASS, CODE_ERROR, WRONG_RESULT, FAILED_*
    stdout: Optional[str]
    stderr: Optional[str]
    actual_result: Optional[dict]
    expected_result: Optional[dict]
    code_file_path: str

# ── schemas/agent_inputs.py ──
class Agent2Input(BaseModel):          # Structured input for Agent 2
    parsed_rule: ParsedRule
    block_data: BlockMappingData
    config_discovery: Optional[ConfigDiscovery]
    exploration_cache_hint: Optional[str]

class Agent5Input(BaseModel):          # Structured input for Agent 5
    validation_result: ValidationResult
    block_data: BlockMappingData
    exploration_summary: Optional[str]
    previous_findings: Optional[str]
    config_discovery: Optional[ConfigDiscovery]

# ── schemas/report_schemas.py ──
class RuleReport(BaseModel):           # Kết quả 1 rule
    rule_id: str
    status: ValidationStatus
    match_expected: bool
    generated_script: str
    needs_human_review: bool
    pipeline_trace: list[TraceEntry]  # TraceEntry(agent, attempt)
    rule_duration_seconds: Optional[float]

class FinalReport(BaseModel):          # Báo cáo tổng hợp
    timestamp: str
    model_file: str
    total_rules: int
    results: list[RuleReport]
    total_duration_seconds: float
```

---

## Agent 0: Rule Analyzer
*Chuyên đọc hiểu ngôn ngữ tự nhiên.*

- **Vai trò**: Đọc rule text → Trích xuất `block_keyword`, `config_name`, `condition`, `expected_value`.
- **LLM Model**: `create_model(small=True)` — task đơn giản, không cần model lớn.
- **Skill (Tools)**: Structured output (không gọi tools).
- **Input**: Rule description (text).
- **Output**: `ParsedRule`
- **Instructions**: `skills/rule-analyzer/SKILL.md`

---

## Agent 1: Data Reader & Search Engine
*Thủ thư — tra cứu từ điển.*

- **Vai trò**: Tìm block trong JSON bằng fuzzy search → Phân tích description.
- **LLM Model**: `create_model(small=True)` — chỉ dùng LLM cho phân tích description, search dùng rapidfuzz.
- **Skill (Tools)**: `fuzzy_search_json`, `read_dictionary`
- **Input**: `ParsedRule.block_keyword`
- **Output**: `BlockMappingData`
- **Instructions**: `skills/data-reader/SKILL.md`

---

## Agent 1.5: Diff Analyzer (tuỳ chọn)
*So sánh 2 model để phát hiện config thay đổi.*

- **Vai trò**: Nhận raw diff từ `utils/model_differ.py` → Interpret thành `ConfigDiscovery`.
- **LLM Model**: `create_model(small=True)`
- **Khi nào chạy**: Chỉ khi user cung cấp `--model-before`.
- **Input**: `ModelDiff` (raw diff: block_changes + config_changes).
- **Output**: `ConfigDiscovery` (location_type, xpath_pattern, default_value, notes).
- **Instructions**: `skills/diff-analyzer/SKILL.md`
- **Backward compatible**: Không có `--model-before` → pipeline chạy 6 agents như bình thường.

---

## Agent 2: Code Generator (Copilot 1)
*Senior Python Developer — Agentic tool calling.*

- **Vai trò**: Khám phá XML tree → Sinh Python code check rule.
- **LLM Model**: `create_model()` — full model, cần tool calling mạnh.
- **tool_call_limit**: 20 (~7 explore + ~3 verify + ~1 write + buffer cho compound rules)
- **Tính chất**: Agentic (multi-step, tự chủ dùng tools). Không có memory (mỗi lần bắt đầu từ đầu), nhưng nhận cross-rule cache từ rules trước.
- **Skill (Tools) cấp phát**:
  - **Model-level**: `build_model_hierarchy`, `find_blocks_recursive`, `query_config`, `list_all_configs`, `trace_connections`, `trace_cross_subsystem`, `list_all_block_types`, `find_config_locations`, `auto_discover_blocks`
  - **XML chi tiết**: `list_xml_files`, `read_xml_structure`, `test_xpath_query`, `deep_search_xml_text`, `read_parent_nodes`
  - **Sinh code**: `write_python_file`
- **Input**: `ParsedRule` + `BlockMappingData` + (tuỳ chọn) `ConfigDiscovery` + (tuỳ chọn) cross-rule cache hint
- **Output**: File Python ghi qua `write_python_file` tool
- **Instructions**: `skills/code-generator/SKILL.md`

### Hành vi Agentic
```
1. build_model_hierarchy() → Xem cây subsystem
2. find_blocks_recursive("Gain") → Tìm tất cả blocks
3. query_config("Gain", "SaturateOnIntegerOverflow") → Rút config + defaults
4. test_xpath_query("simulink/systems/system_root.xml", ...) → Verify XPath
5. Nếu XPath không match → thử biến thể, search file khác
6. write_python_file("check_rule_R001.py", code) → Lưu script
```

---

## Agent 3: Validator (Reviewer)
*QA Tester — Pure Python, không LLM.*

- **Vai trò**: Chạy code sandbox → So sánh kết quả với expected.
- **Tính chất**: **Pure Python** — subprocess.run + JSON compare. Không dùng LLM.
- **Input**: code_file path + list[TestCase] + rule_id
- **Output**: `ValidationResult`
- **Instructions**: `skills/validator/SKILL.md`

### Routing Decision
```
PASS           → Ghi report, chuyển rule tiếp theo
CODE_ERROR     → Chuyển Agent 4 (nếu chưa hết retry)
WRONG_RESULT   → Chuyển Agent 5 (nếu chưa hết retry)
```

---

## Agent 4: Bug Fixer
*Kỹ sư sửa lỗi code.*

- **Vai trò**: Đọc error traceback → Sửa code.
- **LLM Model**: `create_model()` — full model.
- **tool_call_limit**: 10 (~2 read + ~1-2 rewrites, ít hơn Agent 2/5 vì không cần explore XML)
- **Skill (Tools)**: `read_error_traceback`, `read_python_file`, `patch_python_file`
- **Input**: `ValidationResult` (status=CODE_ERROR)
- **Output**: File code đã sửa (ghi qua `patch_python_file`)
- **Instructions**: `skills/bug-fixer/SKILL.md`

---

## Agent 5: Model Inspector (Copilot 2)
*Data Detective — Agentic investigation.*

- **Vai trò**: Điều tra nguyên nhân kết quả sai → Viết lại code.
- **LLM Model**: `create_model()` — full model, cần tool calling mạnh.
- **tool_call_limit**: 20 (~5 read + ~8 investigate + ~2 verify + 1 write + buffer)
- **Tính chất**: Agentic (multi-step). Nhận exploration_summary từ Agent 2 và previous_findings từ retry trước.
- **Skill (Tools) cấp phát**:
  - **Model-level**: `build_model_hierarchy`, `find_blocks_recursive`, `query_config`, `list_all_configs`, `trace_connections`, `read_raw_block_config`, `trace_cross_subsystem`, `list_all_block_types`, `find_config_locations`, `auto_discover_blocks`
  - **XML chi tiết**: `list_xml_files`, `deep_search_xml_text`, `read_xml_structure`, `read_parent_nodes`, `test_xpath_query`
  - **Sinh code**: `read_python_file`, `rewrite_advanced_code`
- **Input**: `ValidationResult` + `BlockMappingData` + exploration_summary + previous_findings + (tuỳ chọn) ConfigDiscovery
- **Output**: File code mới (ghi qua `rewrite_advanced_code`)
- **Instructions**: `skills/model-inspector/SKILL.md`

### Hành vi Agentic
```
1. Đọc exploration_summary (từ Agent 2) → biết Agent 2 đã khám phá gì
2. Đọc previous_findings (từ retry trước) → tránh lặp lại
3. Đặt giả thuyết → Dùng tools kiểm chứng:
   - find_blocks_recursive → blocks có MaskType khác?
   - query_config → config ẩn do mode?
   - deep_search_xml_text → regex search tên config
   - read_raw_block_config → đọc toàn bộ raw config (escalation)
   - trace_cross_subsystem → trace signal xuyên subsystem
4. Khi tìm ra nguyên nhân → rewrite_advanced_code
```

### Last-retry Escalation
Retry cuối cùng, Agent 5 được hướng dẫn escalate:
1. `read_raw_block_config` — dump toàn bộ raw config
2. `deep_search_xml_text` — regex rộng
3. `trace_cross_subsystem` — trace xuyên subsystem
4. Check bddefaults.xml cho default values
5. Dump toàn bộ InstanceData nếu cần

---

## Quy tắc Thép

1. **XML MODEL LÀ BẤT KHẢ XÂM PHẠM**: Tất cả tools XML đều READ-ONLY.
2. **SANDBOX**: Agent 3 chạy code trong subprocess isolation.
3. **PYDANTIC VALIDATION**: Dữ liệu giữa agents luôn qua `.model_validate()`.
4. **RETRY LIMIT**: Tối đa 3 lần retry cho Agent 4 và Agent 5.
5. **TOOL CALL LIMIT**: Agent 2 (20), Agent 4 (10), Agent 5 (20).
6. **MODEL FACTORY**: Tất cả agents dùng `create_model()` — KHÔNG import trực tiếp Gemini/Ollama.

---

## Bảng tổng hợp Tools theo Agent

| Agent | Tool | Chức năng | Read/Write |
|-------|------|-----------|------------|
| 0 | (LLM structured output) | Parse rule text → ParsedRule | Read-only |
| 1 | `fuzzy_search_json` | Tìm block trong JSON (rapidfuzz) | Read-only |
| 1 | `read_dictionary` | Đọc description block | Read-only |
| 1.5 | (LLM structured output) | Interpret diff → ConfigDiscovery | Read-only |
| 2 | `build_model_hierarchy` | Xem cây subsystem | Read-only |
| 2 | `find_blocks_recursive` | Tìm blocks xuyên layers | Read-only |
| 2 | `list_all_block_types` | Liệt kê tất cả block types + identity | Read-only |
| 2 | `find_config_locations` | Reverse lookup: config → block types | Read-only |
| 2 | `auto_discover_blocks` | Scan model tìm blocks matching keyword | Read-only |
| 2 | `query_config` | Rút config + default fallback | Read-only |
| 2 | `list_all_configs` | Liệt kê tất cả configs cho 1 block | Read-only |
| 2 | `trace_connections` | Trace signal connections | Read-only |
| 2 | `trace_cross_subsystem` | Trace xuyên subsystem | Read-only |
| 2 | `list_xml_files` | Liệt kê file XML | Read-only |
| 2 | `read_xml_structure` | Xem cấu trúc file XML | Read-only |
| 2 | `test_xpath_query` | Verify XPath | Read-only |
| 2 | `deep_search_xml_text` | Regex search trong XML | Read-only |
| 2 | `read_parent_nodes` | Đọc ancestry chain | Read-only |
| 2 | `write_python_file` | Sinh file script | Write |
| 3 | (Pure Python) | subprocess.run + JSON compare | Execute |
| 4 | `read_error_traceback` | Phân tích traceback lỗi | Read-only |
| 4 | `read_python_file` | Đọc code bị lỗi | Read-only |
| 4 | `patch_python_file` | Sửa file code | Write |
| 5 | `build_model_hierarchy` | Xem cây subsystem | Read-only |
| 5 | `find_blocks_recursive` | Tìm blocks xuyên layers | Read-only |
| 5 | `list_all_block_types` | Liệt kê tất cả block types + identity | Read-only |
| 5 | `find_config_locations` | Reverse lookup: config → block types | Read-only |
| 5 | `auto_discover_blocks` | Scan model tìm blocks matching keyword | Read-only |
| 5 | `query_config` | Rút config + default | Read-only |
| 5 | `list_all_configs` | Liệt kê tất cả configs cho 1 block | Read-only |
| 5 | `trace_connections` | Trace connections | Read-only |
| 5 | `read_raw_block_config` | Đọc raw config (escalation) | Read-only |
| 5 | `trace_cross_subsystem` | Trace xuyên subsystem | Read-only |
| 5 | `list_xml_files` | Liệt kê file XML | Read-only |
| 5 | `deep_search_xml_text` | Regex search | Read-only |
| 5 | `read_xml_structure` | Xem cấu trúc XML | Read-only |
| 5 | `read_parent_nodes` | Đọc ancestry chain | Read-only |
| 5 | `test_xpath_query` | Verify XPath | Read-only |
| 5 | `read_python_file` | Đọc code hiện tại | Read-only |
| 5 | `rewrite_advanced_code` | Viết lại code mới | Write |
