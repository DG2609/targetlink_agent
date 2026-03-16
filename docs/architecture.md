# Kiến trúc Hệ Thống Multi-Agent: TargetLink Rule Checking

Tài liệu này mô tả chi tiết công nghệ, khái niệm Agent Skill, thiết kế pipeline, luồng dữ liệu, và chính sách xử lý lỗi.

---

## 0. Công Nghệ Sử Dụng (Tech Stack)

| Thành phần | Công nghệ | Lý do chọn |
|-----------|-----------|------------|
| **Agent Framework** | **Agno** (formerly Phidata) | Tốc độ khởi tạo agent cực nhanh (3μs), cực nhẹ (~5 KiB RAM/agent). Hỗ trợ mô hình làm việc nhóm (Team & Delegation) rất khớp với luồng xử lý 6 bước của chúng ta. |
| **Data Validation** | **Pydantic** | Đảm bảo định dạng dữ liệu (Data Contract) truyền giữa các Agent luôn chính xác (Type-safe). |
| **LLM Backend** | **Gemini 2.0 Flash via Vertex AI** | Đóng vai trò là "bộ não" cho các Agent. Sử dụng Google Cloud Vertex AI (không dùng API key trực tiếp). Agno hỗ trợ 23+ LLMs nhưng dự án này chuẩn hóa trên Vertex AI. |
| **Ngôn ngữ xử lý Core** | **Python 3.11+** | Hệ sinh thái AI tốt nhất. |
| **XML Parser** | **lxml** | Xử lý file XML của TargetLink cực kỳ nhanh và hỗ trợ truy vấn XPath mạnh mẽ. |
| **Search Engine (Local)** | **rapidfuzz** | Fuzzy matching để tìm kiếm nhanh Block tương ứng trong hàng ngàn JSON blocks mà không tốn token LLM. |

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
        self.model_dir = model_dir              # Thư mục gốc XML tree
        self.register(self.list_xml_files)       # Đăng ký tool
        self.register(self.read_xml_structure)
        self.register(self.test_xpath_query)

    def list_xml_files(self) -> str:
        """Liệt kê tất cả file XML trong model tree. GỌI ĐẦU TIÊN."""
        ...

    def read_xml_structure(self, xml_file: str, xpath: str) -> str:
        """Đọc cấu trúc XML nodes tại XPath trong 1 file XML cụ thể. READ-ONLY."""
        # ↑ LLM đọc docstring này để biết tool làm gì
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

### Gắn Tool vào Agent (dùng Vertex AI)
```python
from agno.agent import Agent
from agno.models.google import Gemini

agent = Agent(
    model=Gemini(
        id="gemini-2.0-flash-001",
        vertexai=True,                          # ← BẮT BUỘC: dùng Vertex AI
        project_id="your-gcp-project-id",       # ← Từ .env: GOOGLE_CLOUD_PROJECT
        location="us-central1",                  # ← Từ .env: GOOGLE_CLOUD_LOCATION
    ),
    tools=[XmlToolkit(model_dir="/path/to/extracted_slx/")],  # Cấp skill cho agent
    instructions=["Bạn là Python Developer..."],
)
```

> **Vertex AI vs Gemini API Key**: Dự án này dùng Vertex AI (IAM-based auth) thay vì Gemini API key.
> Xác thực qua `gcloud auth application-default login` hoặc Service Account JSON key.
> Biến `.env`: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_VERTEXAI=true`.

### 4 nhóm Skill trong hệ thống của chúng ta

| Nhóm Skill | Tools | Agents sử dụng | Mô tả |
|------------|-------|----------------|-------|
| **Đọc XML (file-level)** | `list_xml_files`, `read_xml_structure`, `test_xpath_query`, `deep_search_xml_text`, `read_parent_nodes` | Agent 2, 5 | Khám phá XML tree (nhiều file XML) từng phần — KHÔNG đọc toàn bộ (READ-ONLY) |
| **Đọc XML (model-level)** | `build_model_hierarchy`, `find_blocks_recursive`, `query_config`, `trace_connections`, `read_raw_block_config` | Agent 2, 5 | Cross-file, hierarchy-aware, default fallback |
| **Tìm kiếm** | `fuzzy_search_json`, `read_dictionary` | Agent 1 | Tra cứu block trong từ điển JSON |
| **Lập trình** | `write_python_file`, `read_python_file`, `patch_python_file`, `rewrite_advanced_code` | Agent 2, 4, 5 | Sinh/sửa code Python |
| **Thực thi** | (Pure Python — subprocess.run + JSON compare) | Agent 3 | Chạy code sandbox + so sánh kết quả. KHÔNG dùng LLM. |

> **Tham khảo**: Pattern tách Tool thành Toolkit class lấy cảm hứng từ `agentic/agent/tools/*.py` (LangGraph), chuyển đổi sang API của Agno.
> Chi tiết implementation xem tại `docs/coding_guide.md`.

---

## 1. Dữ liệu Đầu Vào (User Inputs)

### 1.1 Từ điển Block (`blocks.json`)
Tạo ra từ File Bảng (Excel/Sheet) gồm 3 cột chính. File này là "bản đồ" để AI biết TargetLink giấu config ở đâu.
- **Name UI**: Tên hiển thị với User (VD: `Inport`, `Main Targetlink Data`)
- **Name XML**: Tên lưu trong XML (VD: `TL_Inport`, `TL_MAIN_DATA`)
- **Description**: Mô tả CỰC KỲ QUAN TRỌNG. Định nghĩa cách TargetLink ẩn/hiện config.
  - *Ví dụ*: "CodeGenerateMode: ẩn ở Standard mode, chỉ hiện khi AUTOSAR mode (thêm option 2)".

**Schema ví dụ:**
```json
[
  {
    "name_ui": "Inport",
    "name_xml": "TL_Inport",
    "description": "Block nhận tín hiệu đầu vào. Config 'OutDataTypeStr' nằm ở thẻ <P Name='OutDataTypeStr'>. Giá trị mặc định: 'Inherit: auto'."
  }
]
```

### 1.2 Luật Kiểm Tra (`rules.json`)
Mỗi luật có `rule_id` duy nhất và `description` dạng text tự nhiên.
```json
[
  {
    "rule_id": "R001",
    "description": "Tất cả inport(targetlink) phải set DataType cụ thể, không được để Inherited"
  }
]
```

### 1.3 Expected Results (`expected_results.json`)
Test case của User để Agent 3 và 5 làm cơ sở đánh giá đúng/sai.
```json
[
  {
    "rule_id": "R001",
    "expected_total_blocks": 5,
    "expected_pass": 3,
    "expected_fail": 2,
    "fail_details": [
      {"block_path": "SubSystem1/Inport2", "actual_value": "Inherit: auto"}
    ]
  }
]
```

---

## 2. Sơ đồ Luồng Dữ Liệu (Data Flow)

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                          USER INPUTS                                    │
 │  rules.json    blocks.json    model.slx    expected_results.json        │
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
           ▼                       ▼                  │
 ┌──────────────────────────────────────┐             │
 │  AGENT 2                             │             │
 │  Code Generator (Copilot 1)         │             │
 │  Reads XML → Writes Python script    │             │
 └─────────────┬────────────────────────┘             │
               │                                      │
               │ generated_checks/check_rule_XYZ.py   │
               ▼                                      ▼
 ┌──────────────────────────────────────────────────────────┐
 │  AGENT 3 — Validator (Reviewer)                          │
 │  Sandbox Execute → Compare with Expected Results         │
 │                                                          │
 │  ┌─────────────────────────────────────────────────┐     │
 │  │ Kết quả:                                        │     │
 │  │                                                  │     │
 │  │  ✅ PASS (khớp expected)  → Báo cáo PASS        │     │
 │  │                                                  │     │
 │  │  ❌ CODE ERROR (stderr)   → Gọi Agent 4 ──┐    │     │
 │  │                                              │    │     │
 │  │  ⚠️ WRONG RESULT          → Gọi Agent 5 ──┼─┐  │     │
 │  └──────────────────────────────────────────────┼─┼──┘     │
 └─────────────────────────────────────────────────┼─┼────────┘
                                                   │ │
                    ┌──────────────────────────────┘ │
                    ▼                                │
 ┌──────────────────────────┐                        │
 │  AGENT 4                 │                        │
 │  Bug Fixer               │                        │
 │  Read traceback → Patch  │                        │
 │  Max 3 retries           │──── Fixed code ──→ Agent 3 (re-validate)
 └──────────────────────────┘
                                                     │
                    ┌────────────────────────────────┘
                    ▼
 ┌──────────────────────────┐
 │  AGENT 5                 │
 │  Model Inspector         │
 │  Deep XML search         │
 │  Rewrite XPath logic     │
 │  Max 3 retries           │──── New code ──→ Agent 3 (re-validate)
 └──────────────────────────┘

                    │
                    ▼
 ┌──────────────────────────────────────────┐
 │  OUTPUT                                  │
 │  reports/report_YYYYMMDD.json            │
 │  generated_checks/check_rule_*.py        │
 └──────────────────────────────────────────┘
```

---

## 3. Giao tiếp giữa các Agent (Inter-Agent Communication)

Các Agent không giao tiếp tự do mà truyền dữ liệu qua **Pydantic Data Contracts** theo chiều pipeline.

| Từ → Đến | Dữ liệu truyền | Pydantic Model |
|-----------|----------------|----------------|
| Agent 0 → Agent 1 | keyword, config name, condition | `ParsedRule` |
| Agent 1 → Agent 2 | tên XML block, mô tả vị trí config | `BlockMappingData` |
| Agent 2 → Agent 3 | file Python đã sinh (ghi qua tool) | Pipeline verify file tồn tại |
| Agent 3 → Agent 4 | error traceback + đường dẫn file code | `ValidationResult` (status=CODE_ERROR) |
| Agent 3 → Agent 5 | actual result + expected result + file code | `ValidationResult` (status=WRONG_RESULT) |
| Agent 4 → Agent 3 | file code đã sửa (ghi qua tool) | Pipeline re-validate |
| Agent 5 → Agent 3 | file code mới (ghi qua tool) | Pipeline re-validate |

**Nguyên tắc**: Output của Agent A luôn được Pydantic validate trước khi đưa vào Agent B. Nếu validation thất bại → Pipeline dừng ngay và báo lỗi schema.

---

## 4. Thiết kế 6 Agents (Pipeline)

### Agent 0: Rule Analyzer
- **Vai trò**: Tách Rule Text thành Dữ liệu cấu trúc.
- **Hành động**: Đọc `rules.json` → Trích xuất `block_keyword` (VD: "inport"), `config_name` (VD: "DataType"), `condition`.

### Agent 1: Data Reader (Search Engine)
- **Vai trò**: Truy xuất Từ điển Block để cung cấp thông tin cho AI.
- **Hành động**: Nhận `block_keyword` → Search trong File JSON chứa hàng ngàn block (dùng thuật toán text search chữ không dùng AI) để lấy đúng 1 Block Object duy nhất.
- **Output (cho Agent 2)**: Tên XML của block + Phân tích cấu trúc từ Description (config ẩn/hiện ở mode nào).

### Agent 2: Code Generator (Copilot 1)
- **Vai trò**: Sinh code Python kiểm tra cấu trúc XML thực tế.
- **Hành động**: Đọc thông tin từ Agent 1 → Khám phá XML tree (nhiều file XML sau khi unzip .slx) → list_xml_files → read_xml_structure → test_xpath_query → Viết code check XPath tương ứng. Agent agentic, không có memory..

### Agent 3: Validator (Reviewer)
- **Vai trò**: Chạy code và thẩm định kết quả, đối chiếu với Test Case.
- **Hành động**: Load file Python do Agent 2 sinh ra → Chạy trên XML Model → So sánh actual_result với expected_result.
  - Nếu Code Lỗi (Syntax / Runtime) → Gọi **Agent 4**.
  - Nếu Code Chạy Đủ, nhưng kết quả KHÁC test case → Gọi **Agent 5**.

### Agent 4: Bug Fixer
- **Vai trò**: Sửa lỗi Code do Agent 2 sinh ra.
- **Hành động**: Đọc Error Traceback (VD: AttributeError) → Nhìn lại XML Model gốc → Update code → Trả lại Agent 3 (Tối đa retry 3 lần).

### Agent 5: Model Inspector (Copilot 2)
- **Vai trò**: Điều tra nguyên nhân kết quả sai (do TargetLink giấu config hoặc version model thay đổi).
- **Hành động**: Đọc Description của Agent 1 → Khám phá XML Model bằng các kịch bản search linh hoạt (Fuzzy search name, search tree node) → Phát hiện config bị hidden ở nhánh khác → Viết lại Rule Logic Code → Trả về Agent 3 (Tối đa retry 3 lần).

---

## 5. Chính sách Xử lý Lỗi & Retry (Error Handling Policy)

### 5.1 Bảng tổng hợp

| Tình huống | Agent xử lý | Retry tối đa | Hành động khi vượt retry |
|-----------|-------------|-------------|--------------------------|
| Code sinh ra bị Syntax Error | Agent 4 (Bug Fixer) | 3 lần | Dừng pipeline cho rule đó, ghi `status: "FAILED_CODE_ERROR"` vào report |
| Code sinh ra bị Runtime Error (AttributeError, IndexError...) | Agent 4 (Bug Fixer) | 3 lần | Dừng pipeline cho rule đó, ghi `status: "FAILED_RUNTIME_ERROR"` vào report |
| Code chạy OK nhưng kết quả sai (khác expected) | Agent 5 (Inspector) | 3 lần | Dừng pipeline cho rule đó, ghi `status: "FAILED_WRONG_RESULT"` vào report kèm actual vs expected |
| Pydantic validation thất bại giữa 2 Agent | Pipeline Controller | 0 (dừng ngay) | Ghi `status: "SCHEMA_ERROR"` + chi tiết field nào sai |
| Vertex AI quota hết / LLM timeout | Pipeline Controller | 2 lần (exponential backoff) | Dừng toàn bộ pipeline, báo lỗi API |

### 5.2 Luồng retry chi tiết

```
Agent 3 phát hiện lỗi
    │
    ├── CODE ERROR ──→ Agent 4 fix ──→ Agent 3 chạy lại
    │                     │                  │
    │                     │    Vẫn lỗi?      │
    │                     │◄─────────────────┘
    │                     │ (lặp tối đa 3 lần)
    │                     │
    │                     └── Quá 3 lần → FAILED_CODE_ERROR
    │
    └── WRONG RESULT ──→ Agent 5 inspect ──→ Agent 3 chạy lại
                              │                    │
                              │    Vẫn sai?        │
                              │◄───────────────────┘
                              │ (lặp tối đa 3 lần)
                              │
                              └── Quá 3 lần → FAILED_WRONG_RESULT
```

### 5.3 Escalation path khi retry thất bại

Khi Agent 4 hoặc Agent 5 vượt quá retry limit:
1. **Ghi report chi tiết**: Lưu toàn bộ error trace, actual result, expected result, và các lần sửa code trước đó vào report.
2. **Tiếp tục rule tiếp theo**: Pipeline KHÔNG dừng hoàn toàn. Nó đánh dấu rule đó là FAILED và chuyển sang rule tiếp theo trong `rules.json`.
3. **Tổng kết cuối cùng**: Report cuối cùng sẽ hiện rõ bao nhiêu rule PASS, bao nhiêu FAILED, và lý do thất bại từng cái.
4. **Human Intervention flag**: Các rule FAILED được đánh dấu `"needs_human_review": true` để người dùng biết cần xem lại thủ công.

---

## 6. Ràng Buộc Kỹ Thuật (Constraints)

- **Model TargetLink (SLX) là Dữ liệu CHỈ ĐỌC (READ-ONLY)**.
- Agents chỉ được khai thác thông tin từ file XML, không có quyền `write` hay `modify` bất kỳ thẻ XML nào trong model.
- Pydantic được sử dụng làm cầu nối (Data Contract) đảm bảo output của Agent A luôn khớp với định dạng đầu vào của Agent B.
- Sandbox execution: Code do Agent 2/4/5 sinh ra được chạy trong subprocess cách ly, không ảnh hưởng main process.
- Tất cả XML access đều qua `lxml` in-memory parse, không bao giờ ghi ngược lại file `.slx`.

---

## 7. Giới hạn & Edge Cases

| Giới hạn | Mô tả | Workaround |
|----------|-------|------------|
| **SLX > 500MB** | `lxml` parse in-memory có thể chậm/thiếu RAM | Tăng RAM hoặc split model trước khi check |
| **SubSystem lồng > 10 cấp** | Agent 5 có thể cần nhiều vòng inspect, tốn thời gian | Tăng retry limit hoặc cung cấp Description chi tiết hơn |
| **Block không có trong từ điển** | Agent 1 fuzzy search trả về kết quả sai | Bổ sung block vào `blocks.json` |
| **Description mô tả sai** | Agent 2 sinh code check sai config | Cập nhật Description chính xác hơn |
| **LLM hallucination** | Agent 2 sinh XPath không tồn tại | Agent 3 + 4 sẽ bắt lỗi và retry |
| **Multi-model compare** | Chưa hỗ trợ so sánh 2 version model | Chạy riêng từng model rồi diff report |
