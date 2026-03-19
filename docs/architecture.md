# Kiến trúc Hệ Thống Multi-Agent: TargetLink Rule Checking

Tài liệu này mô tả chi tiết công nghệ, khái niệm Agent Skill, thiết kế pipeline, luồng dữ liệu, và chính sách xử lý lỗi.

---

## 0. Công Nghệ Sử Dụng (Tech Stack)

| Thành phần | Công nghệ | Lý do chọn |
|-----------|-----------|------------|
| **Agent Framework** | **Agno** (formerly Phidata) | Tốc độ khởi tạo agent cực nhanh (3μs), cực nhẹ (~5 KiB RAM/agent). Hỗ trợ mô hình làm việc nhóm (Team & Delegation). |
| **Data Validation** | **Pydantic** | Đảm bảo Data Contract truyền giữa các Agent luôn type-safe. |
| **LLM Backend** | **Gemini (Vertex AI)** hoặc **Ollama (local)** | Dual provider — chuyển đổi qua `LLM_PROVIDER` trong `.env`. Model factory pattern (`utils/model_factory.py`) trả về đúng instance. |
| **Ngôn ngữ Core** | **Python 3.11+** | Hệ sinh thái AI tốt nhất. |
| **XML Parser** | **lxml** | Xử lý file XML cực nhanh, hỗ trợ XPath mạnh mẽ. |
| **Search Engine** | **rapidfuzz** | Fuzzy matching tìm block trong JSON — không tốn token LLM. |

### LLM Provider — Model Factory

Tất cả agents sử dụng `utils/model_factory.py` để tạo LLM model, **không import trực tiếp** Gemini hay Ollama:

```python
from utils.model_factory import create_model

# Agent 2, 4, 5 — model chính (cần tool calling mạnh)
model = create_model()

# Agent 0, 1, 1.5 — model nhỏ (tiết kiệm RAM khi dùng Ollama)
model = create_model(small=True)
```

| Provider | Model chính | Model nhỏ | Auth |
|----------|------------|-----------|------|
| **Gemini** | `GEMINI_MODEL` (VD: gemini-2.0-flash-001) | Cùng model | Vertex AI (gcloud ADC / Service Account) |
| **Ollama** | `OLLAMA_MODEL` (VD: qwen2.5:14b) | `OLLAMA_SMALL_MODEL` (VD: qwen2.5:7b) | Không cần — local server |

---

## 0.5 Khái niệm "Agent Skill" (Tool) trong Agno là gì?

Trong **Agno framework**, "Skill" chính là **Tool** — một hàm Python được đăng ký với Agent, cho phép Agent thực thi hành động cụ thể thay vì chỉ trả lời text.

### Cách hoạt động trong Agno

```
User prompt → LLM suy nghĩ → LLM chọn gọi Tool → Tool chạy code thật → Kết quả trả về LLM → LLM trả lời
```

LLM **đọc docstring** của Tool để quyết định khi nào gọi Tool nào. Docstring chính là "bản mô tả skill" cho AI.

### 2 cách tạo Tool trong Agno

**Cách 1: Toolkit class** — Dùng khi nhiều tools cần shared state (VD: cùng dùng model_dir)
```python
from agno.tools import Toolkit

class XmlToolkit(Toolkit):
    def __init__(self, model_dir: str):
        super().__init__(name="xml_tools")
        self.model_dir = model_dir
        self.register(self.list_xml_files)
        self.register(self.read_xml_structure)

    def list_xml_files(self) -> str:
        """Liệt kê tất cả file XML trong model tree. GỌI ĐẦU TIÊN."""
        ...
```

**Cách 2: Function tool** — Dùng khi tool đơn giản, không cần state
```python
from agno.tools import tool

@tool
def fuzzy_search_json(keyword: str, json_path: str) -> str:
    """Tìm block trong file JSON bằng fuzzy matching."""
    ...
```

### Gắn Tool vào Agent (qua model factory)
```python
from agno.agent import Agent
from utils.model_factory import create_model

agent = Agent(
    model=create_model(),                                       # Gemini hoặc Ollama tuỳ config
    tools=[XmlToolkit(model_dir="/path/to/extracted_slx/")],
    instructions=load_skill("code-generator"),
)
```

### 4 nhóm Skill trong hệ thống

| Nhóm Skill | Tools | Agents sử dụng | Mô tả |
|------------|-------|----------------|-------|
| **Đọc XML (file-level)** | `list_xml_files`, `read_xml_structure`, `test_xpath_query`, `deep_search_xml_text`, `read_parent_nodes` | Agent 2, 5 | Khám phá XML tree từng phần (READ-ONLY) |
| **Đọc XML (model-level)** | `build_model_hierarchy`, `find_blocks_recursive`, `query_config`, `list_all_configs`, `trace_connections`, `read_raw_block_config`, `trace_cross_subsystem`, `list_all_block_types`, `find_config_locations`, `auto_discover_blocks` | Agent 2, 5 | Cross-file, hierarchy-aware, default fallback |
| **Tìm kiếm** | `fuzzy_search_json`, `read_dictionary` | Agent 1 | Tra cứu block trong từ điển JSON |
| **Lập trình** | `write_python_file`, `read_python_file`, `read_error_traceback`, `patch_python_file`, `rewrite_advanced_code` | Agent 2, 4, 5 | Sinh/sửa code Python |
| **Thực thi** | (Pure Python — subprocess.run + JSON compare) | Agent 3 | Chạy code sandbox + so sánh kết quả. KHÔNG dùng LLM. |

---

## 1. Dữ liệu Đầu Vào (User Inputs)

### 1.1 Từ điển Block (`blocks.json`)
File "bản đồ" để AI biết TargetLink giấu config ở đâu.
- **Name UI**: Tên hiển thị với User (VD: `Gain`)
- **Name XML**: Tên lưu trong XML (VD: `Gain`)
- **Description**: Mô tả vị trí config, giá trị mặc định, mode-dependent behavior.

### 1.2 Luật Kiểm Tra (`rules.json`)
Mỗi luật có `rule_id` duy nhất và `description` dạng text tự nhiên.

### 1.3 Expected Results (`expected_results.json`)
Test case để Agent 3 và 5 làm cơ sở đánh giá đúng/sai.

---

## 2. Sơ đồ Luồng Dữ Liệu (Data Flow)

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                          USER INPUTS                                    │
 │  rules.json    blocks.json    model.slx    expected_results.json        │
 │                               model_before.slx (tuỳ chọn)              │
 └─────┬──────────────┬────────────┬──────────────────┬────────────────────┘
       │              │            │                  │
       ▼              │            │                  │
 ┌─────────────┐      │            │                  │
 │  AGENT 0    │      │            │                  │
 │  Rule       │      │            │                  │
 │  Analyzer   │      │            │                  │
 └─────┬───────┘      │            │                  │
       │              │            │                  │
       │ ParsedRule   │            │                  │
       ▼              ▼            │                  │
 ┌─────────────────────────┐       │                  │
 │  AGENT 1                │       │                  │
 │  Data Reader            │       │                  │
 │  (Fuzzy Search JSON)    │       │                  │
 └─────────┬───────────────┘       │                  │
           │                       │                  │
           │ BlockMappingData      │                  │
           │                       ▼                  │
           │            ┌──────────────────────┐      │
           │            │  AGENT 1.5 (tuỳ chọn)│      │
           │            │  Diff Analyzer       │      │
           │            │  (XML diff 2 models) │      │
           │            └──────────┬───────────┘      │
           │                       │                  │
           │                       │ ConfigDiscovery  │
           ▼                       ▼                  │
 ┌──────────────────────────────────────┐             │
 │  AGENT 2                             │             │
 │  Code Generator (Copilot 1)         │             │
 │  Reads XML → Writes Python script    │             │
 │  [exploration_summary → Agent 5]     │             │
 │  [cross-rule cache → next rules]     │             │
 └─────────────┬────────────────────────┘             │
               │                                      │
               │ generated_checks/check_rule_XYZ.py   │
               ▼                                      ▼
 ┌──────────────────────────────────────────────────────────┐
 │  AGENT 3 — Validator (Pure Python, no LLM)               │
 │  Sandbox Execute → Compare with Expected Results         │
 │                                                          │
 │  ┌─────────────────────────────────────────────────┐     │
 │  │ Kết quả:                                        │     │
 │  │  PASS (khớp expected)  → Báo cáo PASS           │     │
 │  │  CODE ERROR (stderr)   → Gọi Agent 4            │     │
 │  │  WRONG RESULT          → Gọi Agent 5            │     │
 │  └─────────────────────────────────────────────────┘     │
 └──────────────────────────────────────────────────────────┘
                                                   │ │
                    ┌──────────────────────────────┘ │
                    ▼                                │
 ┌──────────────────────────┐                        │
 │  AGENT 4                 │                        │
 │  Bug Fixer               │                        │
 │  Read traceback → Patch  │                        │
 │  Max 3 retries           │── Fixed code ──→ Agent 3 (re-validate)
 │  tool_call_limit=10      │
 └──────────────────────────┘
                                                     │
                    ┌────────────────────────────────┘
                    ▼
 ┌──────────────────────────────────────┐
 │  AGENT 5                             │
 │  Model Inspector (Copilot 2)         │
 │  Deep XML search + rewrite           │
 │  [receives exploration_summary]      │
 │  [previous_findings carry forward]   │
 │  Max 3 retries, tool_call_limit=20   │
 └──────────────────────────────────────┘
               │── New code ──→ Agent 3 (re-validate)
               ▼
 ┌──────────────────────────────────────────┐
 │  OUTPUT                                  │
 │  reports/report_YYYYMMDD.json            │
 │  generated_checks/check_rule_*.py        │
 └──────────────────────────────────────────┘
```

---

## 3. Context & Memory Design

### 3.1 Knowledge Handoff (Agent 2 → Agent 5)

Agent 2 khám phá XML model qua nhiều tool calls. Kết quả khám phá (exploration_summary) được trích xuất từ response và truyền cho Agent 5 khi cần investigate. Agent 5 không cần lặp lại công việc Agent 2 đã làm.

```
Agent 2 response.tools → extract exploration_summary:
  - build_model_hierarchy → hierarchy structure
  - find_blocks_recursive → block list
  - query_config → config values + defaults
  - trace_cross_subsystem → cross-subsystem traces
```

### 3.2 Retry Carry-Forward (Agent 5 across retries)

Mỗi vòng retry, Agent 5 nhận `previous_findings` tích lũy từ các vòng trước — tránh lặp lại giả thuyết đã thất bại. Capped ở 3 vòng.

### 3.3 Cross-Rule Cache

`ExplorationCache` lưu hierarchy, blocks, configs từ rule đầu tiên. Các rules sau sử dụng cache này → bỏ qua bước explore, tiết kiệm token và thời gian.

### 3.4 Config Discovery Injection

Khi có Agent 1.5 (diff-based), `ConfigDiscovery` (location_type, xpath_pattern, default_value) được inject vào context của cả Agent 2 và Agent 5 như ground truth.

### 3.5 Loop Detection

`utils/loop_detector.py` phát hiện 5 loại doom loop:
- **Tool oscillation**: Agent gọi lặp đi lặp lại cùng 1 tool
- **XPath cycling**: Agent thử đi thử lại các XPath
- **Read-without-write**: Agent đọc nhiều nhưng không viết code
- **Identical rewrites**: Agent viết lại code giống hệt lần trước
- **Empty results**: Agent liên tục nhận kết quả rỗng

Mỗi loại kèm targeted recovery hint trong skill instructions.

---

## 4. Giao tiếp giữa các Agent (Inter-Agent Communication)

Các Agent truyền dữ liệu qua **Pydantic Data Contracts** theo chiều pipeline.

| Từ → Đến | Dữ liệu truyền | Pydantic Model |
|-----------|----------------|----------------|
| Agent 0 → Agent 1 | keyword, config name, condition | `ParsedRule` |
| Agent 1 → Agent 2 | tên XML block, mô tả vị trí config | `BlockMappingData` |
| Agent 1.5 → Agent 2, 5 | location_type, xpath_pattern, default_value | `ConfigDiscovery` |
| Agent 2 → Agent 3 | file Python đã sinh (ghi qua tool) | Pipeline verify file tồn tại |
| Agent 2 → Agent 5 | exploration_summary (tool call results) | Text (extracted from response) |
| Agent 3 → Agent 4 | error traceback + đường dẫn file code | `ValidationResult` (status=CODE_ERROR) |
| Agent 3 → Agent 5 | actual result + expected result + file code | `ValidationResult` (status=WRONG_RESULT) |
| Agent 5 retry N → N+1 | previous_findings (accumulated) | Text (capped at 3 retries) |
| Rule N → Rule N+1 | hierarchy, blocks, configs cache | `ExplorationCache` |

---

## 5. Thiết kế 7 Agents (Pipeline)

### Agent 0: Rule Analyzer
- **Vai trò**: Tách Rule Text thành dữ liệu cấu trúc.
- **LLM Model**: `create_model(small=True)`
- **tool_call_limit**: N/A (structured output)

### Agent 1: Data Reader (Search Engine)
- **Vai trò**: Search block trong JSON (rapidfuzz, no LLM cho search).
- **LLM Model**: `create_model(small=True)`

### Agent 1.5: Diff Analyzer (tuỳ chọn)
- **Vai trò**: Interpret raw XML diff → ConfigDiscovery.
- **LLM Model**: `create_model(small=True)`
- **Khi nào chạy**: Chỉ khi có `--model-before` arg.

### Agent 2: Code Generator (Copilot 1)
- **Vai trò**: Khám phá XML → sinh Python code check rule.
- **LLM Model**: `create_model()` (full model)
- **tool_call_limit**: 20
- **Agentic**: Tự gọi build_model_hierarchy → find_blocks_recursive → query_config → test_xpath_query → write_python_file

### Agent 3: Validator (Reviewer)
- **Vai trò**: Chạy code sandbox, so sánh kết quả.
- **Pure Python** — KHÔNG dùng LLM.

### Agent 4: Bug Fixer
- **Vai trò**: Sửa lỗi code (syntax/runtime).
- **LLM Model**: `create_model()` (full model)
- **tool_call_limit**: 10

### Agent 5: Model Inspector (Copilot 2)
- **Vai trò**: Điều tra sâu XML, viết lại code.
- **LLM Model**: `create_model()` (full model)
- **tool_call_limit**: 20
- **Agentic**: Tự gọi 8-20 tools — read, investigate, verify, rewrite.

---

## 6. Chính sách Xử lý Lỗi & Retry

### 6.1 Bảng tổng hợp

| Tình huống | Agent xử lý | Retry tối đa | Hành động khi vượt retry |
|-----------|-------------|-------------|--------------------------|
| Code bị Syntax/Runtime Error | Agent 4 (Bug Fixer) | 3 lần | `FAILED_CODE_ERROR` |
| Code chạy OK nhưng kết quả sai | Agent 5 (Inspector) | 3 lần | `FAILED_WRONG_RESULT` |
| Pydantic validation fail | Pipeline Controller | 0 (dừng ngay) | `SCHEMA_ERROR` |
| LLM quota/timeout | Pipeline Controller | 2 lần (exponential backoff) | Dừng pipeline |

### 6.2 Escalation path

Khi retry thất bại:
1. Ghi report chi tiết (error trace, actual/expected, code history)
2. Đánh dấu `needs_human_review: true`
3. Tiếp tục rule tiếp theo (pipeline KHÔNG dừng hoàn toàn)

### 6.3 Last-retry escalation (Agent 5)

Khi Agent 5 ở retry cuối cùng, SKILL.md hướng dẫn 5 chiến thuật escalation:
1. `read_raw_block_config` — đọc toàn bộ raw config
2. `deep_search_xml_text` với regex rộng
3. `trace_cross_subsystem` — trace signal xuyên subsystem
4. Kiểm tra bddefaults.xml cho default values
5. Dump toàn bộ InstanceData nếu vẫn không tìm thấy

---

## 7. Ràng Buộc Kỹ Thuật (Constraints)

- **Model TargetLink (SLX) là READ-ONLY** — agents chỉ đọc, không ghi.
- **Pydantic Data Contract** — output Agent A luôn validate trước khi vào Agent B.
- **Sandbox execution** — code sinh ra chạy trong subprocess cách ly.
- **Tất cả XML access qua lxml** in-memory parse, không ghi ngược file .slx.
- **tool_call_limit** — Agent 2 (20), Agent 4 (10), Agent 5 (20) — ngăn infinite loops.

---

## 8. Giới hạn & Edge Cases

| Giới hạn | Mô tả | Workaround |
|----------|-------|------------|
| **SLX > 500MB** | lxml in-memory có thể chậm | Tăng RAM hoặc split model |
| **SubSystem lồng > 10 cấp** | Agent 5 cần nhiều vòng inspect | Tăng retry limit hoặc cung cấp Description chi tiết |
| **Block không có trong từ điển** | Agent 1 fuzzy search trả về sai | Bổ sung block vào blocks.json |
| **Description mô tả sai** | Agent 2 sinh code check sai | Cập nhật Description chính xác |
| **Ollama tool calling** | Chất lượng phụ thuộc model | Dùng qwen2.5:14b trở lên |
