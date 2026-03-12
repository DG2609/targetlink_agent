# TargetLink Model Rule Checking System

Hệ thống Multi-Agent AI (6 Agents) sử dụng framework **Agno**, **Pydantic**, và **LLM (Gemini via Google Cloud Vertex AI)** để tự động đọc, hiểu, và kiểm tra các modeling rules của dSpace TargetLink trên file model `.slx` (không cần cài đặt MATLAB).

## 🌟 Điểm nổi bật
- **Không cần MATLAB**: Đọc trực tiếp file `.slx` qua việc unzip cấu trúc XML.
- **Agentic Workflow**: Các agents (Code Generator, Validator, Bug Fixer, Inspector) hoạt động tự trị như GitHub Copilot — biết đọc code, hiểu XML, tự tìm phương án sửa lỗi.
- **READ-ONLY Model**: Tuyệt đối không can thiệp, không ghi đè, không làm hỏng model gốc.
- **Dynamic Config Handling**: Xử lý linh hoạt việc TargetLink ẩn/hiện/đổi vị trí config tùy thuộc vào Mode (Standard vs AUTOSAR) hoặc giá trị của các thuộc tính khác.

## 📂 Cấu trúc Thư mục

```
targetlink/
├── main.py                      # Entry point — khởi tạo pipeline 6 agents
├── requirements.txt             # Dependencies
├── config.py                    # Pydantic Settings — đọc .env
├── .env                         # Vertex AI credentials (không commit lên git)
│
├── agents/                      # Định nghĩa từng Agent
│   ├── agent0_rule_analyzer.py
│   ├── agent1_data_reader.py
│   ├── agent2_code_generator.py
│   ├── agent3_validator.py
│   ├── agent4_bug_fixer.py
│   └── agent5_inspector.py
│
├── tools/                       # Tools (Skills) cấp phát cho Agents
│   ├── xml_tools.py             # read_xml_structure, test_xpath_query, deep_search_xml_text, read_parent_nodes
│   ├── search_tools.py          # fuzzy_search_json, read_dictionary
│   ├── code_tools.py            # write_python_file, read_python_file, patch_python_file, rewrite_advanced_code
│   └── sandbox_tools.py         # sandbox_execute_python, compare_json_result
│
├── schemas/                     # Pydantic models (Data Contracts giữa các Agent)
│   └── models.py
│
├── data/                        # Dữ liệu đầu vào từ User
│   ├── model.slx                # File model TargetLink (READ-ONLY)
│   ├── blocks.json              # Từ điển block (1000+ blocks)
│   ├── rules.json               # Luật cần kiểm tra
│   └── expected_results.json    # Test case kết quả mong đợi
│
├── generated_checks/            # Code Python sinh ra bởi Agent 2/4/5 (auto-generated)
│   └── check_rule_001.py
│
├── reports/                     # Báo cáo kết quả (auto-generated)
│   └── report_2024xxxx.json
│
└── docs/                        # Tài liệu
    ├── architecture.md
    └── agents_detail.md
```

## 📂 Kiến trúc Hệ thống

Hệ thống gồm 6 Agents hoạt động theo pipeline:
1. **Agent 0 (Rule Analyzer)**: Đọc file luật (text) → Trích xuất block cần tìm, config cần check, và điều kiện.
2. **Agent 1 (Data Reader)**: Tìm kiếm block tương ứng trong File Từ Điển (JSON 1000+ blocks), phân tích Description để hiểu config nằm ở đâu.
3. **Agent 2 (Code Generator)**: Đọc cấu trúc XML thực tế của block → Sinh Python code để check rule.
4. **Agent 3 (Validator)**: Chạy code sinh ra trên Model XML → So sánh kết quả với Test Case User cung cấp.
5. **Agent 4 (Bug Fixer)**: Nếu code có lỗi Runtime/Syntax → Sửa code.
6. **Agent 5 (Inspector)**: Nếu kết quả check sai lệch với Test Case → Search sâu vào XML tìm nguyên nhân (config bị ẩn, do khác mode...) → Viết lại code chính xác hơn.

*Chi tiết kiến trúc có tại `docs/architecture.md`.*

## 🚀 Setup & Cài đặt

Yêu cầu: Python 3.11+

```bash
# 1. Clone repository & tạo virtual environment
python -m venv venv
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

# 2. Cài đặt dependencies
pip install -r requirements.txt

# 3. Cấu hình Vertex AI — tạo file .env tại thư mục gốc
# 4. Xác thực Google Cloud (chạy 1 lần)
gcloud auth application-default login
```

**File `.env`:**
```env
# ── Google Cloud Vertex AI (BẮT BUỘC) ──
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=true

# ── Model config ──
GEMINI_MODEL=gemini-2.0-flash-001

# ── Xác thực (chọn 1 trong 2 cách) ──
# Cách 1: ADC (Application Default Credentials) — chạy lệnh trước:
#   gcloud auth application-default login
#
# Cách 2: Service Account — set path tới file JSON key:
# GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account-key.json
```

> **Lưu ý**: Hệ thống dùng **Vertex AI**, KHÔNG dùng Gemini API key (`GOOGLE_API_KEY`).
> Vertex AI yêu cầu GCP project có bật API `aiplatform.googleapis.com`.

**File `requirements.txt`:**
```
agno>=1.0.0
google-genai>=1.0.0
pydantic>=2.0
pydantic-settings>=2.0
lxml>=5.0
rapidfuzz>=3.0
python-dotenv>=1.0
```

## 📋 Hướng dẫn sử dụng

Hệ thống cần 4 file đầu vào từ User:
1. `--model`: File model TargetLink (VD: `data/model.slx`)
2. `--blocks`: File từ điển định nghĩa Block UI/XML & mô tả sự khác biệt config (VD: `data/blocks.json`)
3. `--rules`: File định nghĩa luật cần kiểm tra (VD: `data/rules.json`)
4. `--expected`: File Test case kết quả mong đợi (VD: `data/expected_results.json`)

**Chạy hệ thống:**
```bash
python main.py --model data/model.slx --blocks data/blocks.json --rules data/rules.json --expected data/expected_results.json
```

## 📥 Định dạng File Đầu Vào

### `blocks.json` — Từ điển Block
```json
[
  {
    "name_ui": "Inport",
    "name_xml": "TL_Inport",
    "description": "Block nhận tín hiệu đầu vào. Config 'OutDataTypeStr' nằm ở thẻ <P Name='OutDataTypeStr'>. Giá trị mặc định: 'Inherit: auto'. Ở mode AUTOSAR, thêm thẻ <P Name='BusObject'> với option AutosarDataType."
  },
  {
    "name_ui": "Main Targetlink Data",
    "name_xml": "TL_MAIN_DATA",
    "description": "Block cấu hình chính. Config 'CodeGenerateMode' ẩn ở Standard mode (giá trị mặc định = 0), chỉ hiện khi AUTOSAR mode (option thêm giá trị 2). Nằm trong thẻ <P Name='CodeGenerateMode'>."
  },
  {
    "name_ui": "Outport",
    "name_xml": "TL_Outport",
    "description": "Block xuất tín hiệu đầu ra. Config 'OutDataTypeStr' tương tự Inport. Config 'StorageClass' nằm ở thẻ <P Name='RTWStorageClass'> (lưu ý: tên XML khác tên UI)."
  }
]
```

### `rules.json` — Luật kiểm tra
```json
[
  {
    "rule_id": "R001",
    "description": "Tất cả khối inport(targetlink) phải set DataType cụ thể, không được để Inherited"
  },
  {
    "rule_id": "R002",
    "description": "Tất cả Outport phải có StorageClass khác 'Auto'"
  },
  {
    "rule_id": "R003",
    "description": "Main TargetLink Data block phải set CodeGenerateMode = 0 (Standard mode)"
  }
]
```

### `expected_results.json` — Test case kết quả mong đợi
```json
[
  {
    "rule_id": "R001",
    "expected_total_blocks": 5,
    "expected_pass": 3,
    "expected_fail": 2,
    "fail_details": [
      {"block_path": "SubSystem1/Inport2", "actual_value": "Inherit: auto"},
      {"block_path": "SubSystem3/Inport1", "actual_value": "Inherit: auto"}
    ]
  },
  {
    "rule_id": "R002",
    "expected_total_blocks": 4,
    "expected_pass": 4,
    "expected_fail": 0,
    "fail_details": []
  }
]
```

## 📤 Định dạng Kết quả Đầu Ra

### `generated_checks/check_rule_R001.py` — Code sinh ra
```python
"""
Auto-generated rule check script
Rule: R001 - Tất cả inport(targetlink) phải set DataType cụ thể
Generated by: Agent 2 (Code Generator)
"""
from lxml import etree
import os

def check_rule(model_dir: str) -> dict:
    xml_path = os.path.join(model_dir, "simulink", "blockdiagram.xml")
    tree = etree.parse(xml_path)
    root = tree.getroot()

    results = {"pass": [], "fail": []}
    blocks = root.xpath(".//Block[@BlockType='TL_Inport']")

    for block in blocks:
        name = block.get("Name", "Unknown")
        dtype_node = block.find("P[@Name='OutDataTypeStr']")
        dtype_value = dtype_node.text if dtype_node is not None else "NOT_FOUND"

        if dtype_value not in ("Inherit: auto", "NOT_FOUND"):
            results["pass"].append({"block": name, "value": dtype_value})
        else:
            results["fail"].append({"block": name, "value": dtype_value})

    return {
        "rule_id": "R001",
        "total_blocks": len(blocks),
        "pass_count": len(results["pass"]),
        "fail_count": len(results["fail"]),
        "details": results
    }

if __name__ == "__main__":
    import json, sys
    result = check_rule(sys.argv[1])
    print(json.dumps(result, indent=2))
```

### `reports/report_20240315.json` — Báo cáo tổng hợp
```json
{
  "timestamp": "2024-03-15T14:30:00Z",
  "model_file": "data/model.slx",
  "total_rules_checked": 3,
  "summary": {
    "all_pass": 1,
    "has_failures": 2,
    "code_error": 0
  },
  "results": [
    {
      "rule_id": "R001",
      "status": "COMPLETED",
      "match_expected": true,
      "actual": {"total_blocks": 5, "pass": 3, "fail": 2},
      "expected": {"total_blocks": 5, "pass": 3, "fail": 2},
      "generated_script": "generated_checks/check_rule_R001.py",
      "pipeline_trace": {
        "agent_2_attempts": 1,
        "agent_4_fixes": 0,
        "agent_5_inspections": 0
      }
    },
    {
      "rule_id": "R002",
      "status": "COMPLETED",
      "match_expected": true,
      "actual": {"total_blocks": 4, "pass": 4, "fail": 0},
      "expected": {"total_blocks": 4, "pass": 4, "fail": 0},
      "generated_script": "generated_checks/check_rule_R002.py",
      "pipeline_trace": {
        "agent_2_attempts": 1,
        "agent_4_fixes": 1,
        "agent_5_inspections": 0
      }
    },
    {
      "rule_id": "R003",
      "status": "COMPLETED",
      "match_expected": false,
      "actual": {"total_blocks": 1, "pass": 0, "fail": 1},
      "expected": {"total_blocks": 1, "pass": 1, "fail": 0},
      "generated_script": "generated_checks/check_rule_R003.py",
      "pipeline_trace": {
        "agent_2_attempts": 1,
        "agent_4_fixes": 0,
        "agent_5_inspections": 2
      },
      "note": "Agent 5 phát hiện config 'CodeGenerateMode' bị ẩn trong AUTOSAR mode"
    }
  ]
}
```

## ⚠️ Giới hạn đã biết (Known Limitations)

| Giới hạn | Mô tả |
|----------|-------|
| **Kích thước SLX** | File model > 500MB có thể gây chậm khi parse XML in-memory |
| **Retry tối đa** | Agent 4 và Agent 5 mỗi agent chỉ retry tối đa 3 lần. Nếu vượt quá → dừng và báo cần Human Intervention |
| **LLM hallucination** | Code sinh ra có thể dùng sai XPath nếu Description trong `blocks.json` mô tả không chính xác |
| **Multi-model version** | Chưa hỗ trợ so sánh giữa 2 phiên bản model cùng lúc |
| **Nested SubSystem** | Model có SubSystem lồng > 10 cấp có thể cần Agent 5 nhiều vòng inspect hơn |

## 📚 Tài liệu chi tiết

- [Kiến trúc hệ thống](docs/architecture.md) — Tech stack, data flow, error handling
- [Chi tiết kỹ thuật Agents](docs/agents_detail.md) — Pydantic schemas, tools, prompts cho từng Agent
- [Coding Guide](docs/coding_guide.md) — Quy tắc viết code, tách file, patterns (tham khảo từ agentic coder)
